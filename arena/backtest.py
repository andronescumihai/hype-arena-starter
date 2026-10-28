"""Back-test the Writer: write claims from 80% of the practice rows, check them against all of it.

python -m arena.backtest  ->  share of claims the held-out evidence confirms, contradicts or cannot tell.
"""
import json
import os
from collections import Counter

from .claims import Knowledge, write_claims, ASOF
from .pipeline import load_practice, ROOT
from .values import canon
from .verify import same


def check(c, full):
    f, t = c["form"], c["type"]
    if t == "fact":
        cur = full.current((f["subject"], f["attribute"]))
        return None if not cur else same(canon(cur[0]), canon(f["value"]))
    if t == "change":
        segs = full.segments((f["subject"], f["attribute"]))
        if not segs:
            return None
        idx = [i for i, s in enumerate(segs) for side in ("from",) if same(canon(s[0]), canon(f[side]))]
        jdx = [i for i, s in enumerate(segs) if same(canon(s[0]), canon(f["to"]))]
        return bool(idx and jdx and min(idx) < max(jdx))
    if t == "at_event":
        segs = full.segments((f["event"], "date"))
        if not segs:
            return None
        from .verify import days
        v = full.value_at((f["subject"], f["attribute"]), days(segs[0][0]["value"]))
        return None if v is None else same(canon(v), canon(f["value"]))
    if t == "compare":
        a = full.current((f["left"]["subject"], f["left"]["attribute"]))
        b = full.current((f["right"]["subject"], f["right"]["attribute"]))
        if not a or not b:
            return None
        x, y = canon(a[0])[-1], canon(b[0])[-1]
        return {"gt": x > y, "lt": x < y, "eq": x == y}[f["op"]]
    if t == "relation":
        segs = full.segments((f["target"], f["attribute"]))
        return None if not segs else any(same(canon(s[0]), canon(f["value"])) for s in segs)
    return None


def main():
    rows = load_practice()
    lex = json.load(open(os.path.join(ROOT, "data", "lexicon.json")))
    full = Knowledge(rows, lex)
    tally = Counter()
    by_type = Counter()
    for fold in range(5):
        part = [r for i, r in enumerate(rows) if i % 5 != fold]
        claims, _, _ = write_claims(Knowledge(part, lex))
        for c in claims:
            ok = check(c, full)
            key = "confirmed" if ok else "contradicted" if ok is False else "unknown"
            tally[key] += 1
            by_type[(c["type"], key)] += 1
    n = sum(tally.values())
    print({k: f"{v} ({v / n:.1%})" for k, v in tally.items()})
    for t in ("change", "relation", "at_event", "fact", "compare"):
        conf = by_type[(t, "confirmed")]
        bad = by_type[(t, "contradicted")]
        print(f"  {t:9s} confirmed {conf:4d}  contradicted {bad:3d}  unknown {by_type[(t, 'unknown')]:3d}")


if __name__ == "__main__":
    main()
