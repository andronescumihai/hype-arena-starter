"""Build-time training: extractor statistics and the Judge's model, from the practice rows only.

python -m arena.train  ->  models/extractor.json, models/judge.pkl, models/metrics.json
"""
import json
import os
import pickle
import random

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from .extract import Lexicon, Model, extract_rows
from .judge_model import features, vectorize
from .pipeline import load_practice, MODELS, ROOT
from .verify import Historian, judge


def oof_features(rows, lex, folds=5, anchors=True):
    """Features for every row, computed as if its label were hidden (out of fold)."""
    X = [None] * len(rows)
    for fold in range(folds):
        hidden = {r["id"] for i, r in enumerate(rows) if i % folds == fold}
        m = Model().fit([r for r in rows if r["id"] not in hidden])
        ex = extract_rows(rows, lex, m)
        h = Historian()
        for r in rows:
            if r["id"] in hidden or not anchors:
                h.add(r["id"], r["date"], ex[r["id"]], "")
            else:
                h.add(r["id"], r["date"], json.loads(r["form"]), r["label"])
        for i, r in enumerate(rows):
            if r["id"] in hidden:
                _, _, reasons = judge(h, r["id"], r["date"], ex[r["id"]])
                X[i] = features(r["text"], reasons)
    return X


def make_clf():
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                          l2_regularization=1.0, random_state=0)


def main():
    rows = load_practice()
    lex = Lexicon(json.load(open(os.path.join(ROOT, "data", "lexicon.json"))))
    # train on both evidence regimes: with trusted neighbours and with votes only
    X = oof_features(rows, lex, anchors=True) + oof_features(rows, lex, anchors=False)
    y = np.array([r["label"] == "false" for r in rows] * 2)
    Xv = np.array(vectorize(X), float)
    # honest estimate: cross-validated accuracy on the votes-only half
    n = len(rows)
    idx = np.arange(2 * n)
    fold = (idx % n) % 7
    pred = np.zeros(2 * n)
    for f in range(7):
        tr = fold != f
        pred[~tr] = make_clf().fit(Xv[tr], y[tr]).predict_proba(Xv[~tr])[:, 1]
    labels = np.array([r["label"] for r in rows] * 2)
    guess = np.where(pred > 0.5, "false", "true")
    metrics = {
        "rows": n,
        "accuracy_with_anchors": round(float((guess[:n] == labels[:n]).mean()), 4),
        "accuracy_votes_only": round(float((guess[n:] == labels[n:]).mean()), 4),
        "baseline_all_true": round(float((labels[:n] == "true").mean()), 4),
        "false_caught": int(((guess[:n] == "false") & (labels[:n] == "false")).sum()),
        "false_total": int((labels[:n] == "false").sum()),
    }
    clf = make_clf().fit(Xv, y)
    os.makedirs(MODELS, exist_ok=True)
    with open(os.path.join(MODELS, "extractor.json"), "w") as f:
        json.dump(Model().fit(rows).to_json(), f)
    from . import judge_model
    with open(os.path.join(MODELS, "judge.pkl"), "wb") as f:
        pickle.dump({"clf": clf, "features": judge_model.FEATURES}, f)
    with open(os.path.join(MODELS, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    random.seed(0)
    main()
