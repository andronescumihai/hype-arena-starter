"""The arena: Extractor -> Historian -> Judge for labels, Writer -> Referee for claims.

Used by run.py (the offline evaluation run) and by the web app (live runs).
"""
import csv
import json
import os
import pickle

from .extract import Lexicon, Model, extract_rows
from .verify import Historian, judge
from .judge_model import features
from . import judge_model

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PRACTICE = os.path.join(ROOT, "data", "practice.csv")
MODELS = os.path.join(ROOT, "models")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm(t):
    return " ".join(t.lower().split())


def load_practice():
    return read_csv(PRACTICE)


def load_models():
    with open(os.path.join(MODELS, "extractor.json")) as f:
        ext = Model.from_json(json.load(f))
    with open(os.path.join(MODELS, "judge.pkl"), "rb") as f:
        bundle = pickle.load(f)
    judge_model.FEATURES = bundle["features"]
    return ext, bundle["clf"]


def label_rows(rows, lexicon, practice, ext, clf, on_progress=None):
    """Label every row with an empty label. Returns ({id: (label, conf, reasons, p_false)}, historian, facts)."""
    lex = Lexicon(lexicon)
    gold = {(norm(r["text"]), r["date"]): r for r in practice}
    facts = extract_rows(rows, lex, ext)
    hist = Historian()
    # practice rows the input does not hold still count as trusted evidence
    in_input = set()
    for r in rows:
        g = gold.get((norm(r["text"]), r["date"]))
        if r.get("label") and g:
            hist.add(r["id"], r["date"], json.loads(g["form"]), r["label"])
            in_input.add(g["id"])
        else:
            hist.add(r["id"], r["date"], facts[r["id"]], r.get("label", ""))
    for g in practice:
        if g["id"] not in in_input:
            hist.add("practice:" + g["id"], g["date"], json.loads(g["form"]), g["label"])
    out = {}
    todo = [r for r in rows if not r.get("label")]
    feats, metas = [], []
    for i, r in enumerate(todo):
        lab, conf, reasons = judge(hist, r["id"], r["date"], facts[r["id"]])
        feats.append(features(r["text"], reasons))
        metas.append((r, lab, conf, reasons))
        if on_progress and i % 500 == 0:
            on_progress(i, len(todo))
    probs = clf.predict_proba(judge_model.vectorize(feats))[:, 1] if feats else []
    for (r, lab, conf, reasons), p in zip(metas, probs):
        p = float(p)
        label = "false" if p > 0.5 else "true"
        confidence = round(max(p, 1 - p), 3)
        confidence = min(1.0, max(0.5, confidence))
        out[r["id"]] = (label, confidence, reasons, p)
    return out, hist, facts
