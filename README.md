# format-claim-audit

An offline static auditor for data-format promises in Python project documentation.
Version 0.1.0 requires Python 3.9 or later and has no runtime dependencies outside
the standard library. It never executes target code or makes network requests.

It compares claims in root README.md and docs/**/*.md (case-insensitive Markdown
extension) with Python source evidence. Prose and inline code count, including
headings; backtick and tilde fenced code blocks do not. Claims must name a format
and a direction or generic word on the same line. The vocabulary is exactly JSON,
JSONL, CSV, YAML, TOML and XML. Markdown and plain text are excluded because their
static evidence would be too fuzzy.

## Installation and usage

Install from the local wheel or source distribution:

```sh
python -m pip install dist/format_claim_audit-0.1.0-py3-none-any.whl
format-claim-audit ./project
python -m format_claim_audit ./project --json
format-claim-audit ./project --fail-on HIGH --verbose
format-claim-audit ./project --ignore documented-format-unsupported,format-only-in-tests
format-claim-audit --version
```

The target defaults to the current directory. Exit codes are **0 PASS**, **2 FAIL**,
and **1 usage/input error**. The default failure threshold is MEDIUM.
With --fail-on HIGH, MEDIUM findings are still printed but do not fail the audit.
--ignore drops the named rules entirely; unknown rule names are usage errors.

Human output has one `SEVERITY rule file:line format` line per finding and a
PASS/FAIL status. --verbose also prints verified claims. --json always includes
`findings`, `verified_claims`, and `exit`; each finding contains `rule`,
`severity`, `file`, `line`, `format`, and `direction`. Verified claims contain
file, line, format and direction.

## Rules

| Rule | Severity | Trigger |
| --- | --- | --- |
| documented-input-format-unsupported | HIGH | An input claim lacks source evidence |
| documented-output-format-unsupported | HIGH | An output claim lacks source evidence |
| documented-format-unsupported | HIGH | A generic claim lacks source evidence |
| format-only-in-tests | MEDIUM | Evidence for a claimed format occurs only under tests/ |

Input words: reads, read, loads, load, parses, parse, accepts, inputs, input,
ingests, imports. Output words: writes, write, outputs, output, exports, dumps,
produces, emits. Generic words: supports, support, handles, format, formats.
Matching is case-insensitive; extension claims such as “accepts .json files”
count. Specific direction words take precedence over generic words on the same
line; a line saying “reads and writes CSV” has both directions.

Findings are deduplicated by rule, format, file and line. Test-only evidence
produces the MEDIUM rule instead of an unsupported HIGH rule. No claims means
PASS. With no source, every claim produces a finding. Undocumented source
formats never produce findings.

## Static evidence

| Format | Evidence |
| --- | --- |
| JSON | json import/from-import, or .json string literal |
| JSONL | .jsonl string literal, or json.loads/json.dumps call inside a for body |
| CSV | csv import/from-import, or .csv string literal |
| YAML | yaml import/from-import, or .yaml/.yml string literal |
| TOML | tomllib/tomli/toml import/from-import, or .toml string literal |
| XML | xml.etree.ElementTree, xml.dom, or lxml import/from-import, or .xml string literal |

The scanner parses Python with ast; comments do not count. It excludes Python
under docs/ and fixtures/ and separates evidence under any tests path segment.
Symlink files and directories are skipped. .env and .env.* contents are never
read. Only selected Markdown and Python files are opened. Unreadable files,
invalid UTF-8 or Python syntax errors produce an input error rather than a
potentially misleading PASS. Python parsing uses the running interpreter.

## Differentiation

| Tool | Focus compared with this project |
| --- | --- |
| schema-claim-audit | Documented field names versus implemented fields |
| readme-claim-audit | Install commands, flags, links and versions; never formats |
| dep-claim-audit | Dependency claims; never formats |
| privacy-claim-audit | Network and telemetry promises; never formats |
| bandit / ruff | Code issues; never documentation promises |
| file command | Actual file types; never documentation claims |

format-claim-audit checks documented format promises against static Python
evidence. It does not validate schemas, actual data files, or successful runtime
round trips.

## Honest limitations

Prose-pattern matching is not semantics: negations, examples outside fences,
and multiple formats with different verbs on one line can be misclassified.
Imports count as evidence even if unused or unreachable; this is weak evidence.
Evidence is per format, not per direction: a reader import can verify a write
claim. Direction only selects the rule name.

The JSONL heuristic is line-oriented and approximate: a json.loads/json.dumps
call inside a for body can count even when the loop does not process lines.
Aliased JSON calls and equivalent comprehensions are not recognized.
YAML evidence is a PyYAML-style yaml import or extension literal; the standard
library has no yaml module. An import does not prove a dependency is installed.
Extension strings can appear in unrelated contexts. Dynamic format selection
(for example a format chosen at runtime), custom parsers and indirect evidence
may be missed. This is a review aid, not proof of format support.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
python -m build
```

The tests include good, bad and test-only fixtures, filesystem exclusions,
symlinks, CLI behavior, fenced prose, and a guarded .env marker check.
MIT licensed.
