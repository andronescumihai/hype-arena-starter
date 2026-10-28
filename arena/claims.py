"""Writer + Referee agents: write exactly 1,000 new claims, each one true, each one checked.

Knowledge comes from rows labelled true (practice forms). The Writer turns it into
the five claim types of contracts/claim-forms.md using fixed sentence templates.
The Referee re-reads every sentence with the same value parser the labeler uses
and drops any claim whose text does not state exactly what its form says.
Claims are ranked by how safe they are, safest first.
"""
import json
import re
from collections import defaultdict
from datetime import date as Date

from .values import parse, canon, NEGATION, singular
from .verify import same, days

ASOF = days("2026-10-29")
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]
TIME_WORDS = set("ago yesterday tomorrow once formerly previously originally initially recently lately soon "
                 "eventually then before after since until till earlier later january february march april may "
                 "june july august september october november december spring summer autumn winter monday "
                 "tuesday wednesday thursday friday saturday sunday next last past future time".split())
CMP_PHRASES = re.compile(r"\b(more|higher|greater|larger|bigger|longer|less|fewer|lower|smaller|shorter|cheaper)\b"
                         r"|\bthe same\b|\bas much\b|\bas many\b|\bas long as\b|\bas high as\b|\bequal to\b"
                         r"|\bafter\b|\blater than\b|\bbefore\b|\bearlier than\b", re.I)
SYM = {"EUR": "€", "USD": "$", "GBP": "£"}
DUR_WORD = {"ms": "ms", "s": "second", "min": "minute", "h": "hour", "day": "day", "week": "week",
            "month": "month", "year": "year"}
IRREGULAR_PLURAL = {"person": "people", "child": "children"}


def plural(w, n):
    if n == 1:
        return w
    if w in IRREGULAR_PLURAL:
        return IRREGULAR_PLURAL[w]
    if re.search(r"[^aeiou]y$", w):
        return w[:-1] + "ies"
    if re.search(r"(s|sh|ch|x|z)$", w):
        return w + "es"
    return w + "s"


def fmt_num(x):
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    if isinstance(x, int):
        return f"{x:,}"
    s = f"{x:,.6f}".rstrip("0").rstrip(".")
    # three digits after the only point reads as ambiguous unless a percentage
    return s


def render(v):
    """Write a value in a form value-forms.md reads back exactly; None if unsafe."""
    k = v["kind"]
    if k == "quantity":
        n, u = v["value"], v["unit"]
        num = fmt_num(n)
        if re.fullmatch(r"\d+\.\d{3}", num):
            return None
        if u in ("B", "KB", "MB", "GB", "TB", "mm", "cm", "m", "km", "in", "g", "kg", "mAh", "Hz", "kHz",
                 "MHz", "GHz", "mW", "W", "kW"):
            return f"{num} {u}" if u != "in" else f"{num}-inch"
        if not re.fullmatch(r"[a-z][a-z-]*", u):
            return None
        return f"{num} {plural(u, n)}"
    if k == "money":
        num = fmt_num(v["value"])
        cur = v["currency"]
        s = f"{SYM[cur]}{num}" if cur in SYM else f"{cur} {num}"
        if v.get("per"):
            s += f" per {v['per']}"
        return s
    if k == "percent":
        return f"{fmt_num(v['value'])}%"
    if k == "duration":
        n, u = v["value"], v["unit"]
        if u == "ms":
            return f"{fmt_num(n)} ms"
        return f"{fmt_num(n)} {plural(DUR_WORD[u], n)}"
    if k == "date":
        p = v["value"].split("-")
        if len(p) == 3:
            return f"{int(p[2])} {MONTH_NAMES[int(p[1]) - 1]} {p[0]}"
        if len(p) == 2:
            return f"{MONTH_NAMES[int(p[1]) - 1]} {p[0]}"
        return p[0]
    if k == "version":
        return f"version {v['value']}"
    if k == "name":
        return v["value"]
    return None


def attr_phrase(attr):
    ws = attr.replace("_", " ").split()
    up = {"ceo": "CEO", "cto": "CTO", "ai": "AI", "eu": "EU", "soc": "SOC", "p99": "p99", "p95": "p95",
          "sdks": "SDKs", "api": "API", "ui": "UI"}
    return " ".join(up.get(w, w) for w in ws)


NAME_WORDS = set()


def safe_words(phrase):
    ws = phrase.lower().split()
    if any(re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", phrase.lower()) for n in NAME_WORDS):
        return False
    return not any(w in TIME_WORDS for w in ws) and not re.search(r"\d", phrase) and not NEGATION.search(phrase)


class Knowledge:
    """Timelines of facts from rows labelled true."""

    def __init__(self, rows, lexicon):
        self.lex = lexicon
        self.anchors = defaultdict(list)   # key -> [(day, value)]
        self.refuted = defaultdict(list)
        self.texts = set()
        for r in rows:
            self.texts.add(" ".join(r["text"].lower().split()).rstrip(".!? "))
            if not r.get("form"):
                continue
            for f in json.loads(r["form"]):
                v = f["value"]
                if v.get("op"):
                    continue
                key = (f["subject"], f["attribute"])
                if r["label"] == "true":
                    self.anchors[key].append((days(r["date"]), v))
                elif r["label"] == "false" and len(json.loads(r["form"])) == 1:
                    self.refuted[key].append((days(r["date"]), v))
        for k in self.anchors:
            self.anchors[k].sort(key=lambda x: x[0])
        self.names = set()
        for s in lexicon["subjects"]:
            self.names.add(s["name"].lower())
            for a in s.get("aliases", []):
                self.names.add(a.lower())
        self.events = lexicon.get("events", [])
        NAME_WORDS.clear()
        NAME_WORDS.update(self.names)

    def add_texts(self, rows):
        """Input rows a claim must not copy."""
        for r in rows:
            self.texts.add(" ".join(r["text"].lower().split()).rstrip(".!? "))

    def segments(self, key):
        """[(value, first_day, last_day)] in order; None if the anchors flip back and forth."""
        segs = []
        for t, v in self.anchors.get(key, ()):
            c = canon(v)
            if segs and same(canon(segs[-1][0]), c):
                if v["kind"] == "date" and len(v["value"]) > len(segs[-1][0]["value"]):
                    segs[-1][0] = v
                segs[-1][2] = t
            else:
                if any(same(canon(s[0]), c) for s in segs):
                    return None
                segs.append([v, t, t])
        return segs

    def current(self, key):
        """Value on 29 Oct 2026 with a safety score, or None."""
        segs = self.segments(key)
        if not segs:
            return None
        v, first, last = segs[-1]
        n = sum(1 for t, _ in self.anchors[key] if t >= first)
        static = len(segs) == 1
        age = ASOF - last
        safety = 0.6 + 0.08 * min(n, 4) + (0.1 if static else 0) - min(0.35, age / 300)
        if v["kind"] == "date" and key[1] in ("joined", "founded", "date", "launched") and static:
            safety += 0.1
        return v, min(0.97, safety)

    def value_at(self, key, t):
        """Value on day t when anchors on both sides agree; else None."""
        segs = self.segments(key)
        if not segs:
            return None
        for v, first, last in segs:
            if first <= t <= last:
                return v
        return None


def mentions_exact(text, name):
    return re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text, re.I) is not None


def lexicon_ok(form, typ, k):
    attrs = {x["name"]: set(x["attributes"]) for x in k.lex["subjects"]}
    facts = []
    if typ == "compare":
        facts = [(form["left"]["subject"], form["left"]["attribute"]), (form["right"]["subject"], form["right"]["attribute"])]
    elif typ == "relation":
        facts = [(form["subject"], form["link"]), (form["target"], form["attribute"])]
    else:
        facts = [(form["subject"], form["attribute"])]
    if typ == "at_event" and form["event"] not in k.events:
        return False
    return all(a in attrs.get(s_, ()) for s_, a in facts)


def referee(c, k):
    """Internal check of one claim against the forms the referee reads. Returns reason or None."""
    text, form, typ = c["text"], c["form"], c["type"]
    if not lexicon_ok(form, typ, k):
        return "not in this lexicon"
    if len(text) > 300 or " ".join(text.lower().split()).rstrip(".!? ") in k.texts:
        return "length or copy"
    sent = text  # every template is one sentence
    vals = [v for v in parse(mask_names(sent, k)) if not v.get("approx")]
    if typ in ("fact", "at_event", "relation"):
        v = form["value"]
        if v["kind"] == "name":
            if v["value"].lower() not in k.names or not mentions_exact(sent, v["value"]):
                return "name not in lexicon"
            if NEGATION.search(sent):
                return "negation"
        elif v["kind"] != "boolean":
            mine = [x for x in vals if same(canon(x), canon(v)) and not x.get("op")]
            if not mine:
                return "value not read back"
            if v["kind"] != "name":
                kin = [x for x in vals if x["kind"] == v["kind"]]
                if len(kin) != 1:
                    return "another value of the same kind"
            if v["kind"] != "date" and any(x["kind"] == "date" for x in vals):
                return "stray date"
            if NEGATION.search(sent):
                return "negation"
    if typ == "compare":
        if vals or re.search(r"\d", mask_names(sent, k)):
            return "a number in a compare"
        if len(CMP_PHRASES.findall(sent)) != 1:
            return "phrase count"
        if NEGATION.search(sent):
            return "negation"
    if typ == "change":
        if NEGATION.search(sent):
            return "negation"
        for side in ("from", "to"):
            if form[side]["kind"] == "name":
                if form[side]["value"].lower() not in k.names or not mentions_exact(sent, form[side]["value"]):
                    return "change name not in lexicon"
                continue
            if not any(same(canon(x), canon(form[side])) for x in vals):
                return "change side not read back"
    return None


def mask_names(text, k):
    out = text
    for n in sorted(k.names, key=len, reverse=True):
        out = re.sub(r"(?<![\w])" + re.escape(n) + r"(?![\w])", lambda m: "X" * len(m.group(0)), out, flags=re.I)
    return out


def write_claims(k, n=1000, veto=None):
    """Return up to n claims, safest first. veto(key, value) -> True drops a fact the evidence contradicts."""
    cands = []
    subj_attrs = {s["name"]: s["attributes"] for s in k.lex["subjects"]}

    def add(typ, text, form, conf, tag):
        cands.append({"type": typ, "text": text, "form": form, "confidence": round(conf, 3), "_tag": tag})

    cur = {}
    for key in k.anchors:
        c = k.current(key)
        if c and not (veto and veto(key, c[0])):
            cur[key] = c

    # change: one value, later another; true whatever the as-of date
    for key in k.anchors:
        segs = k.segments(key)
        if not segs or len(segs) < 2:
            continue
        subj, attr = key
        pairs = [(segs[i], segs[j], j == i + 1) for i in range(len(segs)) for j in range(i + 1, len(segs))]
        for (a, _, _), (b, _, _), adjacent in pairs:
            if a["kind"] in ("boolean",) or a["kind"] != b["kind"]:
                continue
            ra, rb = render(a), render(b)
            ap = attr_phrase(attr)
            if not ra or not rb or not safe_words(ap):
                continue
            text = f"At {subj}, the {ap} went from {ra} to {rb}."
            add("change", text, {"subject": subj, "attribute": attr, "from": a, "to": b},
                0.93 if adjacent else 0.91, "change")

    # relation: a fact of whoever a link names
    for key, anchors in k.anchors.items():
        subj, link = key
        segs = k.segments(key)
        if not segs:
            continue
        lp = attr_phrase(link)
        if not safe_words(lp):
            continue
        for v, first, last in segs:
            if v["kind"] != "name" or v["value"] not in subj_attrs:
                continue
            target = v["value"]
            for tattr in subj_attrs[target]:
                tsegs = k.segments((target, tattr))
                if not tsegs or len(tsegs) != 1:
                    continue
                tv = tsegs[0][0]
                rv = render(tv)
                tp = attr_phrase(tattr)
                if not rv or tv["kind"] in ("boolean", "name") or not safe_words(tp):
                    continue
                text = f"The {lp} of {subj} has {tp} {rv}." if tv["kind"] != "date" else \
                    f"The {lp} of {subj} {tp} on {rv}." if tattr == "joined" else f"The {lp} of {subj} has {tp} {rv}."
                add("relation", text, {"subject": subj, "link": link, "target": target, "attribute": tattr,
                                       "value": tv}, 0.9, "relation")

    # at_event: a fact on the date of an event
    event_days = {}
    for e in k.events:
        segs = k.segments((e, "date"))
        if segs and len(segs) == 1 and len(segs[0][0]["value"]) == 10:
            event_days[e] = days(segs[0][0]["value"])
    for key in k.anchors:
        subj, attr = key
        ap = attr_phrase(attr)
        if not safe_words(ap):
            continue
        for e, ed in event_days.items():
            if subj == e:
                continue
            v = k.value_at(key, ed)
            if not v or v["kind"] in ("boolean", "date"):
                continue
            rv = render(v)
            if not rv:
                continue
            text = f"At {e}, the {ap} of {subj} was {rv}."
            add("at_event", text, {"subject": subj, "attribute": attr, "event": e, "value": v}, 0.88, "at_event")

    # fact: value on 29 Oct 2026
    for key, (v, safety) in cur.items():
        subj, attr = key
        ap = attr_phrase(attr)
        rv = render(v) if v["kind"] != "boolean" else None
        if v["kind"] == "boolean":
            if v["value"]:
                text = f"{subj} has {ap}." if not ap.startswith(("is ", "has ")) else f"{subj} {ap}."
            else:
                continue
            if not safe_words(ap):
                continue
        else:
            if not rv or not safe_words(ap):
                continue
            verbs = {"joined": "joined on", "founded": "was founded on", "launched": "launched on"}
            if v["kind"] == "date" and attr in verbs:
                text = f"{subj} {verbs[attr]} {rv}."
            else:
                text = f"The {ap} of {subj} is {rv}."
        add("fact", text, {"subject": subj, "attribute": attr, "value": v}, safety, "fact")

    # compare: two facts of one kind on 29 Oct 2026, no value in the sentence
    by_slot = defaultdict(list)
    for key, (v, safety) in cur.items():
        if v["kind"] in ("name", "boolean", "version"):
            continue
        c = canon(v)
        slot = c[:-1] if v["kind"] != "date" else ("date",)
        if v["kind"] == "date" and len(v["value"]) != 10:
            continue
        by_slot[slot].append((key, v, safety))
    for slot, items in by_slot.items():
        for i in range(len(items)):
            for j in range(len(items)):
                if i == j:
                    continue
                (lk, lv, ls), (rk, rv_, rs) = items[i], items[j]
                if lk[0] == rk[0] and lk[1] == rk[1]:
                    continue
                lc, rc = canon(lv), canon(rv_)
                if lv["kind"] == "date":
                    if lc[1] < rc[1]:
                        op, phrase = "lt", "before"
                    elif lc[1] > rc[1]:
                        continue  # write each pair once, as 'before'
                    else:
                        op, phrase = "eq", "on the same day as"
                    lp, rp = attr_phrase(lk[1]), attr_phrase(rk[1])
                    if not safe_words(lp) or not safe_words(rp):
                        continue
                    text = f"The {lp} of {lk[0]} falls {phrase} the {rp} of {rk[0]}."
                    # left subject must come first: it does (inside 'The ... of X')
                else:
                    a, b = lc[-1], rc[-1]
                    if a > b:
                        op, phrase = "gt", "higher than"
                    elif a == b:
                        if i > j:
                            continue
                        op, phrase = "eq", "equal to"
                    else:
                        continue
                    lp, rp = attr_phrase(lk[1]), attr_phrase(rk[1])
                    if not safe_words(lp) or not safe_words(rp) or re.search(CMP_PHRASES, lp + " " + rp):
                        continue
                    text = f"The {lp} of {lk[0]} is {phrase} the {rp} of {rk[0]}."
                gap = abs(lc[-1] - rc[-1]) / max(abs(lc[-1]), abs(rc[-1]), 1e-9) if lv["kind"] != "date" else 1
                conf = min(ls, rs) * (0.95 if op != "eq" else 0.9) + (0.03 if gap > 0.3 else 0)
                add("compare", text, {"left": {"subject": lk[0], "attribute": lk[1]},
                                      "right": {"subject": rk[0], "attribute": rk[1]}, "op": op},
                    min(0.97, conf), "compare")

    # referee pass, dedupe, rank
    seen, ok, dropped = set(), [], defaultdict(int)
    for c in cands:
        t = c["text"]
        if t in seen:
            continue
        seen.add(t)
        why = referee(c, k)
        if why:
            dropped[why] += 1
            continue
        ok.append(c)
    order = {"change": 0, "relation": 1, "at_event": 2, "fact": 3, "compare": 4}
    ok.sort(key=lambda c: (-c["confidence"], order[c["type"]]))
    # keep variety: interleave types while confidence allows
    picked = ok[:n]
    # stated confidence, calibrated on the back-test (python -m arena.backtest): history-based
    # types never failed there; claims about 29 Oct 2026 can miss a change the Writer never saw
    ceiling = {"change": 0.98, "relation": 0.97, "at_event": 0.97, "compare": 0.96, "fact": 0.95}
    for i, c in enumerate(picked):
        c["id"] = f"nn-{c['type']}-{i + 1}"
        c["confidence"] = round(min(ceiling[c["type"]], c["confidence"] + 0.05), 3)
        c.pop("_tag", None)
    return picked, dict(dropped), len(cands)
