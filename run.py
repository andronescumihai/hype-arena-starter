"""Offline evaluation entry point: /universe/universe.csv + lexicon.json -> /output/output.csv.

Writes a safe fallback table first (every row 'true', plus the claims), then the
real one, always under a temporary name renamed into place, so a table exists
even if the deadline hits mid-run.
"""
import csv
import json
import os
import signal
import sys
import time

from arena.claims import Knowledge, write_claims, ASOF
from arena.pipeline import load_practice, load_models, label_rows, read_csv
from arena.values import canon
from arena.verify import same

UNIVERSE = os.environ.get("UNIVERSE_DIR", "/universe")
OUTPUT = os.environ.get("OUTPUT_DIR", "/output")
COLUMNS = ["id", "type", "text", "form", "label", "confidence"]


def write_table(labels, claims, rows):
    tmp = os.path.join(OUTPUT, "output.csv.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            if r.get("label"):
                continue
            lab, conf = labels.get(r["id"], ("true", 0.6))
            w.writerow([r["id"], "", "", "", lab, "" if lab == "unsure" else f"{conf:.3f}"])
        for c in claims:
            w.writerow([c["id"], c["type"], c["text"], json.dumps(c["form"], ensure_ascii=False), "true",
                        f"{c['confidence']:.3f}"])
    os.replace(tmp, os.path.join(OUTPUT, "output.csv"))


def main():
    t0 = time.time()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    rows = read_csv(os.path.join(UNIVERSE, "universe.csv"))
    lexicon = json.load(open(os.path.join(UNIVERSE, "lexicon.json"), encoding="utf-8"))
    practice = load_practice()
    print(f"input: {len(rows)} rows, {sum(not r.get('label') for r in rows)} to label", flush=True)

    know = Knowledge(practice, lexicon)
    know.add_texts(rows)
    claims, dropped, n = write_claims(know)
    write_table({}, claims, rows)
    print(f"fallback table written ({time.time() - t0:.1f}s); claims: {len(claims)} of {n} candidates, "
          f"referee dropped {sum(dropped.values())}", flush=True)

    ext, clf = load_models()
    result, hist, _ = label_rows(rows, lexicon, practice, ext, clf,
                                 on_progress=lambda i, n: print(f"  judged {i}/{n}", flush=True))
    labels = {rid: (lab, conf) for rid, (lab, conf, _, _) in result.items()}

    # cross-check claims against the whole universe: drop a fact the evidence has moved past
    def veto(key, value):
        states, path, obs = hist.timeline(key)
        if not path:
            return False
        last_day = max(path)
        later = [o for o in obs if o[0] > last_day - 60 and o[2] > 0]
        return not same(path[last_day], canon(value)) and len(later) >= 3

    claims, dropped, n = write_claims(know, veto=veto)
    write_table(labels, claims, rows)
    falses = sum(1 for l, _ in labels.values() if l == "false")
    print(f"done in {time.time() - t0:.1f}s: {len(labels)} labels ({falses} false), {len(claims)} claims", flush=True)


if __name__ == "__main__":
    main()
