"""Every example in contracts/value-forms.md, run through our parser.

python -m tests.test_values
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from arena.values import parse, canon  # noqa: E402
from arena.verify import same  # noqa: E402

DOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts", "value-forms.md")
ROW = re.compile(r"^\| `([^`]+)` \| `(\{[^`]+\})` \|(.*)$")


def reads(written, value):
    want = dict(value)
    op = want.pop("op", None)
    for v in parse(written):
        if v.get("approx"):
            continue
        if v["kind"] in ("name", "boolean"):
            continue
        units = v.get("alt_units") or [v.get("unit")]
        for u in units:
            vv = dict(v, unit=u) if v["kind"] == "quantity" else v
            hit = canon(vv) == canon(want) if v["kind"] == "date" else same(canon(vv), canon(want))
            if hit and v.get("op") == op:
                return True
    return False


def main():
    section, passed, failed = "", 0, []
    for line in open(DOC, encoding="utf-8"):
        if line.startswith("## "):
            section = line[3:].strip()
        m = ROW.match(line.strip())
        if not m:
            continue
        written, value = m.group(1), json.loads(m.group(2))
        if value["kind"] in ("name", "boolean"):
            continue
        expect = section != "Not read"
        ok = reads(written, value) == expect
        passed += ok
        if not ok:
            failed.append((section, written, value))
    print(f"{passed} of {passed + len(failed)} value-forms examples read as the spec says")
    for f in failed:
        print("  FAIL", f)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
