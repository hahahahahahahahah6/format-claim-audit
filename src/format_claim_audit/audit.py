"""Static documentation claims and Python evidence collection."""
import ast
import os
import re
from pathlib import Path

FORMATS = ("JSON", "JSONL", "CSV", "YAML", "TOML", "XML")
WORDS = {
    "input": r"reads|read|loads|load|parses|parse|accepts|inputs|input|ingests|imports",
    "output": r"writes|write|outputs|output|exports|dumps|produces|emits",
    "generic": r"supports|support|handles|format|formats",
}
RULES = {
    "input": "documented-input-format-unsupported",
    "output": "documented-output-format-unsupported",
    "generic": "documented-format-unsupported",
}
ALL_RULES = set(RULES.values()) | {"format-only-in-tests"}
EXTENSIONS = {"json": "JSON", "jsonl": "JSONL", "csv": "CSV",
              "yaml": "YAML", "yml": "YAML", "toml": "TOML", "xml": "XML"}


def files(root):
    """Walk without following symlinks, and never select environment files."""
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs
                         if not Path(directory, d).is_symlink() and d != ".git"
                         and d != ".env")
        for name in sorted(names):
            path = Path(directory, name)
            if name == ".env" or name.startswith(".env.") or path.is_symlink():
                continue
            yield path


def claims(text, file):
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        directions = [kind for kind, words in WORDS.items()
                      if re.search(r"\b(?:" + words + r")\b", line, re.I)]
        # Specific directions take precedence over the generic word "format".
        specific = [d for d in directions if d != "generic"]
        directions = specific or directions
        for fmt in FORMATS:
            aliases = [fmt] + (["yml"] if fmt == "YAML" else [])
            if not any(re.search(r"(?<!\w)" + alias + r"(?!\w)", line, re.I)
                       for alias in aliases):
                continue
            for direction in directions:
                yield dict(file=file, line=number, format=fmt, direction=direction)


def evidence(text, filename="<source>"):
    tree = ast.parse(text, filename=filename)
    found = set()
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            modules = [base] + [base + "." + a.name for a in node.names]
        for module in modules:
            if module == "json":
                found.add("JSON")
            if module == "csv":
                found.add("CSV")
            if module == "yaml":
                found.add("YAML")
            if module in {"tomllib", "tomli", "toml"}:
                found.add("TOML")
            if (module == "xml.etree.ElementTree" or module.startswith("xml.etree.ElementTree.")
                    or module == "xml.dom" or module.startswith("xml.dom.")
                    or module == "lxml" or module.startswith("lxml.")):
                found.add("XML")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for extension in re.findall(r"\.(jsonl|json|csv|yaml|yml|toml|xml)(?!\w)", node.value, re.I):
                found.add(EXTENSIONS[extension.lower()])
        if isinstance(node, (ast.For, ast.AsyncFor)):
            for statement in node.body:
                for child in ast.walk(statement):
                    if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                            and isinstance(child.func.value, ast.Name)
                            and child.func.value.id == "json"
                            and child.func.attr in {"loads", "dumps"}):
                        found.add("JSONL")
    return found


def audit(root, fail_on="MEDIUM", ignore=()):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("target must be an existing, non-symlink directory")
    documented = []
    production, test = set(), set()
    for path in files(root):
        relative = path.relative_to(root)
        parts = relative.parts
        is_doc = (relative.as_posix() == "README.md"
                  or (parts[0] == "docs" and path.suffix.lower() == ".md"))
        if is_doc:
            documented.extend(claims(path.read_text(encoding="utf-8"), relative.as_posix()))
        if path.suffix != ".py" or "docs" in parts[:-1] or "fixtures" in parts[:-1]:
            continue
        formats = evidence(path.read_text(encoding="utf-8-sig"), relative.as_posix())
        (test if "tests" in parts[:-1] else production).update(formats)
    findings, verified = [], []
    seen = set()
    for claim in documented:
        fmt = claim["format"]
        if fmt in production:
            verified.append(claim)
            continue
        rule = "format-only-in-tests" if fmt in test else RULES[claim["direction"]]
        key = (rule, fmt, claim["file"], claim["line"])
        if rule in ignore or key in seen:
            continue
        seen.add(key)
        findings.append(dict(claim, rule=rule,
                             severity="MEDIUM" if fmt in test else "HIGH"))
    failed = any(f["severity"] == "HIGH" or fail_on == "MEDIUM" for f in findings)
    return dict(findings=findings, verified_claims=verified, exit=2 if failed else 0)
