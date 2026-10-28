"""Historian + Judge agents: build each fact's timeline from every source, then rule on each row.

Historian: for each fact (subject, attribute) it gathers what every sentence says.
A value is credible when a labelled row backs it, or when two or more sentences
repeat it. Credible values are ordered by when they first appear, which gives
the fact's timeline: each value holds until the next one starts.

Judge: a sentence is true when its value is the one holding on its date;
false when it repeats a value the timeline has moved past (stale), or states a
value no other source backs while sources agree on another (hype).
"""
import math
from collections import defaultdict
from datetime import date as Date

from .values import canon

W_TRUE, W_FALSE, W_UNL = 3.0, -3.0, 1.0
CHANGE = 1.6


def days(d):
    y, m, dd = (int(x) for x in d[:10].split("-"))
    return Date(y, m, dd).toordinal()


def same(a, b):
    """Two canonical values agree (dates agree on the precision both state)."""
    if a == b:
        return True
    if a[0] == "date" and b[0] == "date":
        x, y = a[1], b[1]
        return x.startswith(y) or y.startswith(x)
    if a[0] == b[0] and a[0] in ("quantity", "percent", "duration") and isinstance(a[-1], float):
        return a[:-1] == b[:-1] and abs(a[-1] - b[-1]) <= 1e-9 * max(1, abs(a[-1]))
    return False


class Historian:
    def __init__(self):
        self.obs = defaultdict(list)   # key -> [(day, canon value, weight, row_id, kind)]
        self._tl = {}

    def add(self, row_id, date_s, facts, label):
        t = days(date_s)
        for f in facts:
            v = f["value"]
            if v.get("op"):
                continue
            key = (f["subject"], f["attribute"])
            c = canon(v)
            if label == "true":
                self.obs[key].append((t, c, W_TRUE, row_id, "anchor"))
            elif label == "false":
                if len(facts) == 1:
                    self.obs[key].append((t, c, W_FALSE, row_id, "refuted"))
            elif label != "unsure":
                self.obs[key].append((t, c, W_UNL, row_id, "vote"))
        self._tl.clear()

    def timeline(self, key):
        """Most likely value on each date: a sticky path (Viterbi) through the sightings.

        Changing value costs CHANGE, so one lone source cannot move the timeline,
        but a run of sources saying the same new thing can. Cached per key.
        """
        if key in self._tl:
            return self._tl[key]
        obs = sorted(self.obs.get(key, ()))
        states = []
        for o in obs:
            if not any(same(s, o[1]) for s in states):
                states.append(o[1])
            else:  # keep the most precise date form
                i = next(i for i, s in enumerate(states) if same(s, o[1]))
                if o[1][0] == "date" and len(o[1][1]) > len(states[i][1]):
                    states[i] = o[1]
        dates = sorted({o[0] for o in obs})
        by_date = {d: [o for o in obs if o[0] == d] for d in dates}
        n = len(states)
        score = [0.0] * n
        back = []
        for d in dates:
            emit = [sum(o[2] if (o[2] > 0) == True and same(st, o[1]) else (o[2] if o[2] < 0 and same(st, o[1]) else 0)
                        for o in by_date[d]) for st in states]
            best_prev = max(range(n), key=lambda i: score[i]) if n else 0
            new, ptr = [], []
            for j in range(n):
                stay, move = score[j], score[best_prev] - CHANGE
                if stay >= move:
                    new.append(stay + emit[j]); ptr.append(j)
                else:
                    new.append(move + emit[j]); ptr.append(best_prev)
            score = new
            back.append(ptr)
        path = {}
        if dates:
            j = max(range(n), key=lambda i: score[i])
            for k in range(len(dates) - 1, -1, -1):
                path[dates[k]] = states[j]
                j = back[k][j]
        self._tl[key] = (states, path, obs)
        return self._tl[key]


def judge(historian, row_id, date_s, facts):
    """Return (label, confidence, reasons) for one row."""
    t = days(date_s)
    if not facts:
        return "true", 0.6, [{"why": "no checkable fact found; most sentences are true"}]
    reasons, verdicts = [], []
    for f in facts:
        v, key = f["value"], (f["subject"], f["attribute"])
        agree = rival = ratio = 0.0
        roundness = 0
        if v.get("op") in ("gt", "lt"):
            vd, conf, why = "hype", 0.6, "states a bound (over / under) instead of an exact value"
        elif v.get("op"):
            vd, conf, why = "unknown", 0.55, "states a limit (up to / at least)"
        else:
            c = canon(v)
            states, path, obs = historian.timeline(key)
            others = [o for o in obs if o[3] != row_id]
            held = path.get(t)
            num = c[-1] if isinstance(c[-1], float) else None
            if num is not None and held is not None and isinstance(held[-1], float) and held[-1] > 0 and num > 0:
                ratio = math.log(num / held[-1])
            if num is not None and num >= 10:
                roundness = int(num % 10 == 0) + int(num % 100 == 0) + int(num % 1000 == 0)
            agree = sum(o[2] for o in others if o[2] > 0 and same(o[1], c) and abs(o[0] - t) <= 90)
            if not others:
                vd, conf, why = "unknown", 0.55, "no other source states this fact"
            elif held is not None and same(held, c):
                vd, conf, why = "true", min(0.97, 0.66 + 0.06 * agree), "matches the value the timeline holds on this date"
            else:
                rival = sum(o[2] for o in others if o[2] > 0 and held is not None and same(o[1], held)
                            and abs(o[0] - t) <= 90)
                earlier = any(same(o[1], c) and o[0] < t and o[2] > 0 for o in others)
                later = any(same(o[1], c) and o[0] > t and o[2] > 0 for o in others)
                if rival < 1.5:
                    vd, conf, why = "unknown", 0.55, "too few sources to tell"
                else:
                    vd = "false"
                    conf = min(0.95, 0.55 + 0.06 * rival)
                    why = ("stale: the value had moved on by this date" if earlier else
                           "premature: this value only holds later" if later else
                           "hype: no source backs this value, others agree on another")
        explained = 0
        if vd == "false" and f.get("alts"):
            # the Challenger's check: could the Extractor have misread this value?
            for alt in f["alts"]:
                st, pa, ob = historian.timeline((alt["subject"], alt["attribute"]))
                h2 = pa.get(t)
                if h2 is not None and same(h2, canon(alt["value"])) and \
                        any(o[3] != row_id and same(o[1], h2) for o in ob):
                    explained = 1
                    vd, conf = "true", 0.6
                    why = f"read as {alt['attribute'].replace('_', ' ')} of {alt['subject']}, it matches the timeline"
                    break
        verdicts.append((vd, conf))
        reasons.append({"subject": f["subject"], "attribute": f["attribute"], "value": v, "verdict": vd,
                        "confidence": round(conf, 2), "why": why,
                        "agree": agree, "rival": rival, "score": f.get("score", 3.0),
                        "ratio": ratio, "round": roundness, "explained": explained})
    falses = [c for vd, c in verdicts if vd == "false"]
    if falses:
        return "false", max(falses), reasons
    if any(vd == "hype" for vd, _ in verdicts):
        return "false", 0.6, reasons
    trues = [c for vd, c in verdicts if vd == "true"]
    return ("true", min(trues), reasons) if trues else ("true", 0.55, reasons)
