"""Honest evaluation, shaped like the real run: whole pages lose their labels.

For each of 5 folds, a fifth of the practice pages become unlabelled input; the Extractor
statistics and the Judge's model are retrained on the other pages only.

python -m arena.evaluate  ->  accuracy, confusion, and confidence calibration (models/evaluation.json)
"""
import json
import os
from collections import Counter

import numpy as np

from . import judge_model as JM
from .extract import Lexicon, Model
from .judge_model import vectorize
from .pipeline import load_practice, label_rows, MODELS, ROOT
from .train import oof_features, make_clf


def pages_of(rows):
    pages, cur = [], []
    for r in rows:
        if cur and r["date"] != cur[-1]["date"]:
            pages.append(cur)
            cur = []
        cur.append(r)
    return pages + [cur] if cur else pages


def main(folds=5):
    rows = load_practice()
    lexj = json.load(open(os.path.join(ROOT, "data", "lexicon.json")))
    lex = Lexicon(lexj)
    pages = pages_of(rows)
    confusion, confs = Counter(), []
    saved = JM.FEATURES
    for fold in range(folds):
        hidden = {r["id"] for i, pg in enumerate(pages) if i % folds == fold for r in pg}
        known = [r for r in rows if r["id"] not in hidden]
        ext = Model().fit(known)
        JM.FEATURES = None
        X = oof_features(known, lex, anchors=True) + oof_features(known, lex, anchors=False)
        clf = make_clf().fit(np.array(vectorize(X), float), np.array([r["label"] == "false" for r in known] * 2))
        inp = [dict(id=r["id"], text=r["text"], date=r["date"], label="" if r["id"] in hidden else r["label"])
               for r in rows]
        res, _, _ = label_rows(inp, lexj, known, ext, clf)
        for r in rows:
            if r["id"] in hidden:
                label, conf, _, _ = res[r["id"]]
                confusion[(r["label"], label)] += 1
                confs.append((conf, label == r["label"]))
    JM.FEATURES = saved
    n = sum(confusion.values())
    bins = []
    for lo, hi in ((0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.01)):
        b = [ok for c, ok in confs if lo <= c < hi]
        bins.append({"from": lo, "to": min(hi, 1.0), "rows": len(b), "right": round(sum(b) / max(1, len(b)), 3)})
    out = {
        "rows": n,
        "accuracy": round(sum(v for (g, p), v in confusion.items() if g == p) / n, 4),
        "baseline_all_true": round(sum(v for (g, _), v in confusion.items() if g == "true") / n, 4),
        "false_caught": confusion[("false", "false")],
        "false_total": sum(v for (g, _), v in confusion.items() if g == "false"),
        "false_calls_right": round(confusion[("false", "false")] /
                                   max(1, sum(v for (_, p), v in confusion.items() if p == "false")), 3),
        "calibration": bins,
    }
    os.makedirs(MODELS, exist_ok=True)
    json.dump(out, open(os.path.join(MODELS, "evaluation.json"), "w"), indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
