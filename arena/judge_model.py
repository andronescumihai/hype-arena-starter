"""Judge: turns the Historian's evidence for a row into P(false) with a small learned model.

Features are the evidence itself (how many sources agree, how strong the rival
value is, stale / premature / hype verdicts, how sure the extractor was) plus a
few wording cues. The model is a gradient-boosted tree ensemble from
scikit-learn, trained on the practice rows. No language model involved.
"""
import re

CUES = {
    "now": r"\bnow\b", "today": r"\btoday\b", "still": r"\bstill\b", "up_from": r"\bup from\b|\bdown from\b",
    "grows": r"\bgrow|\brose\b|\brises\b|\bclimb|\bjump", "first_person": r"\b(I|I'm|I've|my|me)\b",
    "we": r"\b(we|our|us)\b", "quote": r"[\"“”]|\bsaid\b|\bsays\b", "superlative": r"\b(every|all|best|most|any)\b",
    "more_than": r"\bmore than\b|\bover\b|\bat least\b", "hedge": r"\b(told|heard|reportedly|apparently|rumou?r)",
    "exclaim": r"!", "colon": r":", "since": r"\bsince\b|\bfrom today\b|\bas of\b",
}
VERDICTS = ["true", "false", "unknown", "hype"]
WHYS = ["stale", "premature", "hype", "matches", "no other", "too few", "states a bound", "states a limit"]


def features(text, reasons):
    fs = [r for r in reasons if "verdict" in r]
    x = {
        "n_facts": len(fs),
        "len": len(text),
        "digits": len(re.findall(r"\d", text)),
    }
    for v in VERDICTS:
        x["v_" + v] = sum(r["verdict"] == v for r in fs)
    for w in WHYS:
        x["w_" + w.replace(" ", "_")] = sum(r["why"].startswith(w) for r in fs)
    x["max_rival"] = max([r["rival"] for r in fs], default=0)
    x["min_agree"] = min([r["agree"] for r in fs], default=0)
    x["max_agree"] = max([r["agree"] for r in fs], default=0)
    x["min_score"] = min([r["score"] for r in fs], default=0)
    x["false_score"] = max([r["score"] for r in fs if r["verdict"] == "false"], default=0)
    x["max_conf_false"] = max([r["confidence"] for r in fs if r["verdict"] == "false"], default=0)
    for k, pat in CUES.items():
        x["c_" + k] = int(bool(re.search(pat, text, re.I if k not in ("first_person",) else 0)))
    kinds = [r["value"]["kind"] for r in fs]
    for k in ("quantity", "money", "percent", "duration", "date", "version", "name", "boolean"):
        x["k_" + k] = kinds.count(k)
    return x


FEATURES = None


def vectorize(dicts):
    global FEATURES
    if FEATURES is None:
        FEATURES = sorted(dicts[0])
    return [[d.get(k, 0) for k in FEATURES] for d in dicts]
