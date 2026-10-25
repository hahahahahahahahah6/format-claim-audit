import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from format_claim_audit.audit import audit, claims, evidence
from format_claim_audit.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_good(self):
        result = audit(FIXTURES / "good")
        self.assertEqual(result["exit"], 0)
        self.assertEqual(len(result["verified_claims"]), 3)

    def test_bad(self):
        result = audit(FIXTURES / "bad")
        self.assertEqual(result["exit"], 2)
        self.assertEqual({(f["rule"], f["format"]) for f in result["findings"]}, {
            ("documented-input-format-unsupported", "TOML"),
            ("documented-output-format-unsupported", "XML"),
            ("documented-format-unsupported", "CSV")})

    def test_testonly(self):
        result = audit(FIXTURES / "testonly")
        self.assertEqual(result["exit"], 2)
        self.assertEqual(result["findings"][0]["rule"], "format-only-in-tests")
        self.assertEqual(result["findings"][0]["severity"], "MEDIUM")

    def test_threshold(self):
        result = audit(FIXTURES / "testonly", "HIGH")
        self.assertEqual(result["exit"], 0)
        self.assertEqual(len(result["findings"]), 1)

    def test_no_claims(self):
        self.write("README.md", "A plain project.")
        self.assertEqual(audit(self.root)["exit"], 0)

    def test_no_source(self):
        self.write("README.md", "reads JSON\nwrites CSV\nsupports YAML")
        self.assertEqual(len(audit(self.root)["findings"]), 3)

    def test_ignore(self):
        r = audit(FIXTURES / "bad", ignore={"documented-format-unsupported"})
        self.assertEqual(len(r["findings"]), 2)

    def test_nested_docs_case(self):
        self.write("docs/nested/Guide.MD", "# Accepts .yaml files")
        self.assertEqual(audit(self.root)["findings"][0]["file"], "docs/nested/Guide.MD")

    def test_other_markdown_ignored(self):
        self.write("other.md", "reads CSV")
        self.assertEqual(audit(self.root)["findings"], [])

    def test_nested_readme_ignored(self):
        self.write("src/README.md", "reads CSV")
        self.assertEqual(audit(self.root)["findings"], [])

    def test_production_wins(self):
        self.write("README.md", "reads CSV")
        self.write("tests/a.py", "import csv")
        self.write("src/a.py", "import csv")
        self.assertEqual(audit(self.root)["exit"], 0)

    def test_nested_tests(self):
        self.write("README.md", "reads CSV")
        self.write("pkg/tests/a.py", "import csv")
        self.assertEqual(audit(self.root)["findings"][0]["severity"], "MEDIUM")

    def test_source_symlink(self):
        target = self.write("fixtures/a.py", "import csv")
        (self.root / "linked.py").symlink_to(target)
        self.write("README.md", "reads CSV")
        self.assertEqual(audit(self.root)["exit"], 2)

    def test_doc_symlink(self):
        target = self.write("other.md", "reads CSV")
        (self.root / "README.md").symlink_to(target)
        self.assertEqual(audit(self.root)["findings"], [])

    def test_directory_symlink(self):
        self.write("fixtures/a.py", "import csv")
        (self.root / "linked").symlink_to(self.root / "fixtures", target_is_directory=True)
        self.write("README.md", "reads CSV")
        self.assertEqual(audit(self.root)["exit"], 2)

    def test_env_never_opened(self):
        original = Path.open
        def guarded(path, *args, **kwargs):
            if path.name == ".env":
                raise AssertionError(".env opened")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", guarded):
            code, out, err = self.cli(str(FIXTURES / "bad"), "--json")
        self.assertEqual(code, 2)
        self.assertNotIn("UNIQUE_ENV_MARKER_947183", out + err)

    def test_json_cli(self):
        code, out, _ = self.cli(str(FIXTURES / "bad"), "--json")
        result = json.loads(out)
        self.assertEqual(code, result["exit"])
        self.assertEqual(set(result), {"findings", "verified_claims", "exit"})
        self.assertEqual(set(result["findings"][0]), {"rule", "severity", "file", "line", "format", "direction"})

    def test_verbose(self):
        code, out, _ = self.cli(str(FIXTURES / "good"), "--verbose")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("VERIFIED"), 3)

    def test_human(self):
        code, out, _ = self.cli(str(FIXTURES / "bad"))
        self.assertEqual(code, 2)
        self.assertIn("HIGH documented-input-format-unsupported README.md:1 TOML", out)

    def test_version(self):
        code, out, _ = self.cli("--version")
        self.assertEqual((code, out.strip()), (0, "0.1.0"))

    def test_help(self):
        self.assertEqual(self.cli("--help")[0], 0)

    def test_missing_root(self):
        self.assertEqual(self.cli(str(self.root / "missing"))[0], 1)

    def test_file_root(self):
        self.assertEqual(self.cli(str(self.write("file", "")))[0], 1)

    def test_unknown_option(self):
        self.assertEqual(self.cli("--unknown")[0], 1)

    def test_bad_threshold(self):
        self.assertEqual(self.cli("--fail-on", "LOW")[0], 1)

    def test_bad_ignore(self):
        self.assertEqual(self.cli("--ignore", "unknown")[0], 1)

    def test_cli_ignore(self):
        self.assertEqual(self.cli(str(FIXTURES / "testonly"), "--ignore", "format-only-in-tests")[0], 0)

    def test_syntax_error(self):
        self.write("a.py", "def broken(")
        self.assertEqual(self.cli(str(self.root))[0], 1)

    def test_invalid_utf8(self):
        (self.root / "README.md").write_bytes(b"\xff")
        self.assertEqual(self.cli(str(self.root))[0], 1)

    def test_dedupe(self):
        self.write("README.md", "supports CSV CSV, reads CSV and parses CSV")
        self.assertEqual(len(audit(self.root)["findings"]), 1)

    def test_distinct_locations(self):
        self.write("README.md", "reads CSV\nreads CSV")
        self.assertEqual(len(audit(self.root)["findings"]), 2)

    def test_multiple_directions(self):
        self.write("README.md", "reads and writes CSV")
        self.assertEqual(len(audit(self.root)["findings"]), 2)

    def test_comments_not_evidence(self):
        self.assertEqual(evidence("# import csv\n# .jsonl"), set())

    def test_jsonl_outside_loop(self):
        self.assertNotIn("JSONL", evidence("import json\nx = json.loads(data)"))

    def test_jsonl_else_not_body(self):
        self.assertNotIn("JSONL", evidence("for x in xs:\n pass\nelse:\n json.loads(x)"))

    def test_unrelated_loads(self):
        self.assertNotIn("JSONL", evidence("for x in xs:\n other.loads(x)"))

    def test_doc_line_numbers(self):
        c = list(claims("intro\n```\nreads CSV\n```\nreads JSON", "x"))
        self.assertEqual(c[0]["line"], 5)

    def test_unclosed_fence(self):
        self.assertEqual(list(claims("~~~\nreads CSV", "x")), [])

    def test_short_fence_does_not_close(self):
        self.assertEqual(list(claims("````\n```\nreads CSV", "x")), [])

    def test_no_reverse_rule(self):
        self.write("a.py", "import csv")
        self.assertEqual(audit(self.root)["findings"], [])


def claim_case(text, expected):
    def test(self):
        result = list(claims(text, "README.md"))
        self.assertEqual([(c["format"], c["direction"]) for c in result], expected)
    return test


for i, word in enumerate(("reads", "read", "loads", "load", "parses", "parse",
                           "accepts", "inputs", "input", "ingests", "imports")):
    setattr(AuditTests, "test_input_word_%02d" % i, claim_case(word + " CSV", [("CSV", "input")]))
for i, word in enumerate(("writes", "write", "outputs", "output", "exports", "dumps", "produces", "emits")):
    setattr(AuditTests, "test_output_word_%02d" % i, claim_case(word + " XML", [("XML", "output")]))
for i, word in enumerate(("supports", "support", "handles", "format", "formats")):
    setattr(AuditTests, "test_generic_word_%02d" % i, claim_case(word + " TOML", [("TOML", "generic")]))
for i, (text, expected) in enumerate([
    ("# ACCEPTS .YaMl files", [("YAML", "input")]),
    ("writes .jsonl files", [("JSONL", "output")]),
    ("reads .json", [("JSON", "input")]),
    ("supports `CSV`", [("CSV", "generic")]),
    ("reads JSONL", [("JSONL", "input")]),
    ("reads JSONish", []), ("JSON", []), ("reads Markdown and plain text", []),
    ("```python\nreads CSV\n```", []), ("~~~\nreads CSV\n~~~", []),
    ("supports JSON and CSV", [("JSON", "generic"), ("CSV", "generic")]),
]):
    setattr(AuditTests, "test_claim_edge_%02d" % i, claim_case(text, expected))


def evidence_case(source, fmt):
    def test(self):
        self.assertIn(fmt, evidence(source))
    return test


for i, (source, fmt) in enumerate([
    ("import json", "JSON"), ("from json import loads", "JSON"),
    ("import csv as c", "CSV"), ("from csv import reader", "CSV"),
    ("import yaml", "YAML"), ("from yaml import safe_load", "YAML"),
    ("import tomllib", "TOML"), ("import tomli", "TOML"),
    ("from toml import loads", "TOML"), ("import xml.etree.ElementTree", "XML"),
    ("import xml.dom.minidom", "XML"), ("from xml.etree import ElementTree", "XML"),
    ("from xml import dom", "XML"), ("import lxml", "XML"),
    ("from lxml import etree", "XML"),
    ("for line in lines:\n json.loads(line)", "JSONL"),
    ("for item in items:\n json.dumps(item)", "JSONL"),
] + [('path = "data.' + ext + '"', fmt) for ext, fmt in [
    ("json", "JSON"), ("jsonl", "JSONL"), ("csv", "CSV"), ("yaml", "YAML"),
    ("yml", "YAML"), ("toml", "TOML"), ("xml", "XML")]]):
    setattr(AuditTests, "test_evidence_%02d" % i, evidence_case(source, fmt))

for i, directory in enumerate(("docs", "fixtures", "pkg/docs", "pkg/fixtures")):
    def excluded(self, directory=directory):
        self.write("README.md", "reads CSV")
        self.write(directory + "/a.py", "import csv")
        self.assertEqual(audit(self.root)["findings"][0]["severity"], "HIGH")
    setattr(AuditTests, "test_excluded_%02d" % i, excluded)


if __name__ == "__main__":
    unittest.main()
