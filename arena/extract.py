"""Extractor agent: turns a sentence into facts (subject, attribute, value).

No LLM. Subjects come from the lexicon (names and aliases), carried over from
earlier sentences of the same page when a sentence does not name one. Values come
from arena.values. Attributes are picked by a small scorer trained on the
practice forms: which value slots and which words go with which attribute.
"""
import json
import math
import re
from collections import Counter, defaultdict

from .values import parse, slot, singular, negated, canon

WORD = re.compile(r"[a-z0-9]+")
STOP = set("the a an of and or to in on at for per with from by is are was were be been has have had it its "
           "this that than as our we you your their his her he she they them now today new all every each "
           "hooly".split())


def words(text):
    return [singular(w) for w in WORD.findall(text.lower()) if w not in STOP]


def attr_words(attr):
    return [singular(w) for w in attr.lower().split("_") if w not in STOP]


class Lexicon:
    def __init__(self, lex):
        self.subjects = {s["name"]: s for s in lex["subjects"]}
        self.events = set(lex.get("events", []))
        names = []
        for s in lex["subjects"]:
            for n in [s["name"]] + s.get("aliases", []):
                names.append((n, s["name"]))
        names.sort(key=lambda x: -len(x[0]))
        self.patterns = [(re.compile(r"(?<![\w])" + re.escape(n).replace(r"\ ", r"\s*") + r"(?![\w])", re.I), s)
                         for n, s in names]

    def mentions(self, text):
        """[(start, end, subject)] longest-first, non-overlapping."""
        found, taken = [], []
        for pat, subj in self.patterns:
            for m in pat.finditer(text):
                s, e = m.span()
                if all(e <= a or s >= b for a, b in taken):
                    taken.append((s, e))
                    found.append((s, e, subj))
        return sorted(found)

    def attributes(self, subject):
        return self.subjects.get(subject, {}).get("attributes", [])


class Model:
    """Statistics learned from practice forms."""

    def __init__(self):
        self.slot_attr = defaultdict(Counter)      # attribute name -> slot counts
        self.word_attr = defaultdict(Counter)      # word -> attribute counts
        self.attr_count = Counter()
        self.name_values = defaultdict(set)        # attribute -> name values
        self.all_names = set()

    def fit(self, rows):
        for r in rows:
            form = r.get("form")
            if not form:
                continue
            ws = set(words(r["text"]))
            for f in json.loads(form):
                a, v = f["attribute"], f["value"]
                self.attr_count[a] += 1
                self.slot_attr[a][slot(v)] += 1
                for w in ws:
                    self.word_attr[w][a] += 1
                if v["kind"] == "name":
                    self.name_values[a].add(v["value"])
                    self.all_names.add(v["value"])
        return self

    def to_json(self):
        return {"slot_attr": {a: [[list(k), n] for k, n in c.items()] for a, c in self.slot_attr.items()},
                "word_attr": {w: dict(c) for w, c in self.word_attr.items()},
                "attr_count": dict(self.attr_count),
                "name_values": {a: sorted(v) for a, v in self.name_values.items()}}

    @classmethod
    def from_json(cls, d):
        m = cls()
        for a, items in d["slot_attr"].items():
            for k, n in items:
                m.slot_attr[a][tuple(k)] = n
        for w, c in d["word_attr"].items():
            m.word_attr[w] = Counter(c)
        m.attr_count = Counter(d["attr_count"])
        for a, v in d["name_values"].items():
            m.name_values[a] = set(v)
            m.all_names |= set(v)
        return m

    def slot_fit(self, attr, sl):
        """How well a value slot fits an attribute (0..1)."""
        c = self.slot_attr.get(attr)
        if c:
            tot = sum(c.values())
            if c.get(sl):
                return 0.5 + 0.5 * c[sl] / tot
            if any(k[0] == sl[0] for k in c):
                return 0.15
            return 0.0
        # unseen attribute: guess from its words
        aw = attr_words(attr)
        if sl[0] == "quantity" and sl[1] in aw:
            return 0.6
        hints = {"date": {"date", "joined", "founded", "launch", "released", "opened", "beta", "start", "meeting"},
                 "money": {"price", "cost", "revenue", "fee", "salary", "bounty", "funding", "budget", "spend"},
                 "percent": {"rate", "share", "percent", "growth", "margin", "uptime", "accuracy", "attendance"},
                 "duration": {"time", "duration", "latency", "life", "trial", "period", "history", "retention"},
                 "version": {"version", "release"},
                 "name": {"lead", "ceo", "cto", "head", "city", "venue", "headquarters", "provider", "partner"},
                 "boolean": set()}
        if set(aw) & hints.get(sl[0], set()):
            return 0.45
        return 0.05 if sl[0] in ("quantity", "boolean") else 0.02

    def word_fit(self, attr, ws):
        aw = set(attr_words(attr))
        overlap = len(aw & set(ws)) / max(1, len(aw))
        n = self.attr_count.get(attr, 0)
        if not n:
            return overlap
        score = 0.0
        for w in set(ws):
            c = self.word_attr.get(w)
            if c and c.get(attr):
                score += math.log(1 + c[attr]) * (c[attr] / sum(c.values()))
        return overlap + 0.25 * score


def extract_rows(rows, lex, model):
    """Extract facts for rows (in page order). Returns {row_id: [fact, ...]}."""
    out = {}
    context, ctx_date = [], None
    for r in rows:
        text, date = r["text"], r["date"]
        if date != ctx_date:
            context, ctx_date = [], date
        ms = lex.mentions(text)
        # mask names so "Hooly Pixel 10" or "Hooly I/O 2026" do not read as values
        masked = list(text)
        for s, e, _ in ms:
            masked[s:e] = "X" * (e - s)
        masked = "".join(masked)
        vals = [v for v in parse(masked) if not v.get("approx")]
        mentioned = [m[2] for m in ms]
        subjects = list(dict.fromkeys(mentioned + context[::-1]))
        global_search = not subjects
        if global_search:
            subjects = list(lex.subjects)
        ws = words(text)
        facts = []
        used_attr = set()
        # name values: lexicon mentions or known names that are not the topic
        name_cands = [(s, e, subj) for s, e, subj in ms]
        for nm in model.all_names:
            for m in re.finditer(r"(?<![\w])" + re.escape(nm) + r"(?![\w])", text, re.I):
                name_cands.append((m.start(), m.end(), nm))
        for v in vals:
            best = None
            cands = []
            units = v.get("alt_units") or [v.get("unit")]
            for ui, u in enumerate(units):
                vv = dict(v, unit=u) if v["kind"] == "quantity" else v
                sl = slot(vv)
                for si, subj in enumerate(subjects):
                    pos_bonus = 0.3 if subj in mentioned else 0.0
                    # prefer the mention nearest before the value
                    near = [abs(v["span"][0] - s) for s, e, ss in ms if ss == subj]
                    if near:
                        pos_bonus += 0.2 / (1 + min(near) / 20)
                    pos_bonus -= 0.05 * si if not global_search else 0.25
                    for a in lex.attributes(subj):
                        sf = model.slot_fit(a, sl)
                        if sf <= 0.05:
                            continue
                        sc = 2 * sf + model.word_fit(a, ws) + pos_bonus - 0.1 * ui - (0.3 if a in used_attr else 0)
                        cands.append((sc, subj, a, vv))
                        if best is None or sc > best[0]:
                            best = (sc, subj, a, vv)
            if best and best[0] > 0.9:
                sc, subj, a, vv = best
                used_attr.add((subj, a))
                clean = lambda x: {k: y for k, y in x.items() if k not in ("span", "approx", "alt_units")}
                cands.sort(key=lambda c: -c[0])
                alts = [{"subject": c[1], "attribute": c[2], "value": clean(c[3]), "score": round(c[0], 3)}
                        for c in cands[1:6] if c[0] > sc - 0.8 and (c[1], c[2]) != (subj, a)][:3]
                facts.append({"subject": subj, "attribute": a, "value": clean(vv), "score": round(sc, 3),
                              "alts": alts})
        # names
        for s, e, nm in name_cands:
            best = None
            for si, subj in enumerate(subjects):
                if subj == nm:
                    continue
                for a in lex.attributes(subj):
                    if model.slot_fit(a, ("name",)) < 0.5:
                        continue
                    wf = model.word_fit(a, ws)
                    known = nm in model.name_values.get(a, ())
                    sc = wf + (0.6 if known else 0) + (0.3 if subj in mentioned else 0) - (0.05 * si if not global_search else 0.3)
                    if best is None or sc > best[0]:
                        best = (sc, subj, a)
            if best and best[0] > 0.9 and not negated(text, s):
                sc, subj, a = best
                facts.append({"subject": subj, "attribute": a, "value": {"kind": "name", "value": nm},
                              "score": round(sc, 3)})
        # yes / no: attribute words present in the sentence
        if not facts:
            best = None
            for si, subj in enumerate(subjects[:3] if not global_search else subjects):
                for a in lex.attributes(subj):
                    if model.slot_fit(a, ("boolean",)) < 0.5:
                        continue
                    aw = set(attr_words(a))
                    ov = len(aw & set(ws)) / max(1, len(aw))
                    sc = ov + model.word_fit(a, ws) * 0.3 + (0.2 if subj in mentioned else 0) - (0.05 * si if not global_search else 0.25)
                    if best is None or sc > best[0]:
                        best = (sc, subj, a)
            if best and best[0] > 0.6:
                sc, subj, a = best
                facts.append({"subject": subj, "attribute": a,
                              "value": {"kind": "boolean", "value": not negated(text)}, "score": round(sc, 3)})
        out[r["id"]] = facts
        for m in mentioned:
            if m in context:
                context.remove(m)
            context.append(m)
        for f in facts:
            if f["subject"] in context:
                context.remove(f["subject"])
            context.append(f["subject"])
    return out
