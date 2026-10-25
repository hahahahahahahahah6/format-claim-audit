"""Command line interface."""
import argparse
import json
import sys
from . import __version__
from .audit import ALL_RULES, audit


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, "%s: error: %s\n" % (self.prog, message))


def main(argv=None):
    parser = Parser(prog="format-claim-audit", description="Audit documented data formats against Python source.")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on", choices=("HIGH", "MEDIUM"), default="MEDIUM")
    parser.add_argument("--ignore", default="", metavar="RULE,...")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    ignored = set(args.ignore.split(",")) if args.ignore else set()
    if ignored - ALL_RULES:
        parser.error("unknown ignored rule: " + ", ".join(sorted(ignored - ALL_RULES)))
    try:
        result = audit(args.path, args.fail_on, ignored)
    except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
        print("format-claim-audit: input error: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for finding in result["findings"]:
            print("{severity} {rule} {file}:{line} {format}".format(**finding))
        if args.verbose:
            for claim in result["verified_claims"]:
                print("VERIFIED {file}:{line} {format} {direction}".format(**claim))
        print("FAIL" if result["exit"] else "PASS")
    return result["exit"]
