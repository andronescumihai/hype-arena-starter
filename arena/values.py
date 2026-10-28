"""Value parser: reads the values a sentence states, following contracts/value-forms.md.

Deterministic, regex based. Returns dicts shaped like claimed_value.schema.json
(kind, value, unit/currency/per, optional op) plus the character span.
"""
import re

WORDNUM = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
for t, v in TENS.items():
    WORDNUM[t] = v
    for u, uv in list(WORDNUM.items()):
        if 0 < uv < 10:
            WORDNUM[f"{t}-{u}"] = v + uv
WORDNUM.update({"a dozen": 12, "a hundred": 100, "one hundred": 100, "two hundred": 200, "three hundred": 300})

_WN = "|".join(sorted((re.escape(w) for w in WORDNUM), key=len, reverse=True))
NUM = rf"(?:\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?|(?:{_WN}))"
SCALE = r"(?:\s?(?:thousand|million|billion|bn|M|k)\b)?"
SCALES = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9}

MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
MON_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
            "oct": 10, "nov": 11, "dec": 12}
_MON = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?"

DATA_UNITS = {"b": "B", "byte": "B", "kb": "KB", "kilobyte": "KB", "mb": "MB", "megabyte": "MB", "gb": "GB",
              "gig": "GB", "gigabyte": "GB", "tb": "TB", "terabyte": "TB"}
PHYS_UNITS = {"mm": "mm", "millimetre": "mm", "millimeter": "mm", "cm": "cm", "centimetre": "cm",
              "centimeter": "cm", "m": "m", "metre": "m", "meter": "m", "km": "km", "kilometre": "km",
              "kilometer": "km", "inch": "in", "g": "g", "gram": "g", "gramme": "g", "kg": "kg",
              "kilogram": "kg", "kilo": "kg", "mah": "mAh", "hz": "Hz", "hertz": "Hz", "khz": "kHz",
              "kilohertz": "kHz", "mhz": "MHz", "megahertz": "MHz", "ghz": "GHz", "gigahertz": "GHz",
              "mw": "mW", "milliwatt": "mW", "w": "W", "watt": "W", "kw": "kW", "kilowatt": "kW"}
UNITS = {**DATA_UNITS, **PHYS_UNITS}
DUR_UNITS = {"ms": "ms", "millisecond": "ms", "s": "s", "sec": "s", "second": "s", "min": "min", "minute": "min",
             "h": "h", "hr": "h", "hour": "h", "d": "day", "day": "day", "week": "week", "wk": "week",
             "fortnight": "week", "month": "month", "mo": "month", "mth": "month", "year": "year", "yr": "year",
             "decade": "year"}
CURRENCY_SYM = {"€": "EUR", "$": "USD", "£": "GBP", "US$": "USD"}
CURRENCY_CODES = "EUR USD GBP CHF RON PLN CZK HUF SEK NOK DKK JPY CNY INR CAD AUD".split()
CURRENCY_WORDS = {"euro": "EUR", "euros": "EUR", "dollar": "USD", "dollars": "USD", "lei": "RON"}

NEGATION = re.compile(r"\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|\w+n't\b|\w+n’t\b", re.I)
APPROX_BEFORE = re.compile(r"(?:about|around|approximately|approx\.?|roughly|nearly|almost|circa|ca\.?|some|"
                           r"estimated|est\.?|close to|more or less|~|≈|±)\s*$", re.I)
APPROX_AFTER = re.compile(r"^\s*(?:or so|give or take|-ish)", re.I)
OPS_BEFORE = [
    ("gt", r"(?:over|more than|greater than|higher than|above|exceeding|in excess of|upwards of)"),
    ("lt", r"(?:under|less than|fewer than|lower than|below)"),
    ("le", r"(?:up to|at most|no more than|not more than|maximum|max|within)"),
    ("ge", r"(?:at least|no less than|not less than|no fewer than|minimum)"),
]
OPS_AFTER = [("le", r"(?:or less|or fewer|or under|or below|or lower|or shorter)"),
             ("ge", r"(?:or more|or higher|or above|or longer|or over|\+)")]
NOUN_STOP = {"of", "the", "a", "an", "and", "or", "to", "in", "on", "at", "for", "per", "with", "from", "by",
             "is", "are", "was", "were", "has", "have", "it", "its", "this", "that", "than", "as"}


def num(s):
    s = s.strip().lower()
    if s in WORDNUM:
        return WORDNUM[s]
    return float(s.replace(",", ""))


def scaled(numtxt, scaletxt):
    v = num(numtxt)
    if scaletxt:
        sc = scaletxt.strip()
        v *= SCALES["m" if sc == "M" else sc.lower()]
    return int(v) if float(v).is_integer() else round(v, 6)


def singular(w):
    w = w.lower()
    irregular = {"people": "person", "children": "child", "men": "man", "women": "woman"}
    if w in irregular:
        return irregular[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "shes", "ches", "xes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 2:
        return w[:-1]
    return w


def _op(text, start, end):
    before, after = text[max(0, start - 30):start], text[end:end + 15]
    for op, pat in OPS_BEFORE:
        if re.search(pat + r"\s*$", before, re.I):
            return op
    for op, pat in OPS_AFTER:
        if re.match(r"\s*" + pat, after, re.I):
            return op
    return None


def parse(text):
    """Return all values stated in text, each {'kind',...,'span':(s,e),'approx':bool,'op':...}."""
    out, taken = [], []

    def free(s, e):
        return all(e <= a or s >= b for a, b in taken)

    def add(v, s, e):
        if not free(s, e):
            return
        taken.append((s, e))
        v["span"] = (s, e)
        v["approx"] = bool(APPROX_BEFORE.search(text[max(0, s - 25):s]) or APPROX_AFTER.search(text[e:e + 12]))
        if v["kind"] not in ("name", "boolean", "version"):
            op = _op(text, s, e)
            if op:
                v["op"] = op
        out.append(v)

    # dates
    for m in re.finditer(rf"\b(\d{{4}})-(\d{{2}})(?:-(\d{{2}}))?\b", text):
        y, mo, d = m.groups()
        add({"kind": "date", "value": f"{y}-{mo}" + (f"-{d}" if d else "")}, *m.span())
    for m in re.finditer(rf"\b(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s*({_MON})\s+(\d{{4}})\b", text):
        d, mon, y = m.groups()
        mo = MONTHS.get(mon.lower().rstrip("."), MON_ABBR.get(mon.lower().rstrip(".")))
        add({"kind": "date", "value": f"{y}-{mo:02d}-{int(d):02d}"}, *m.span())
    for m in re.finditer(rf"\b({_MON})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", text):
        mon, d, y = m.groups()
        mo = MONTHS.get(mon.lower().rstrip("."), MON_ABBR.get(mon.lower().rstrip(".")))
        add({"kind": "date", "value": f"{y}-{mo:02d}-{int(d):02d}"}, *m.span())
    for m in re.finditer(rf"\b({_MON})\s+(\d{{4}})\b", text):
        mon, y = m.groups()
        if mon == "May" or mon.lower() != "may":
            mo = MONTHS.get(mon.lower().rstrip("."), MON_ABBR.get(mon.lower().rstrip(".")))
            add({"kind": "date", "value": f"{y}-{mo:02d}"}, *m.span())
    # money
    sym = r"(?:US\$|€|\$|£)"
    codes = "|".join(CURRENCY_CODES)
    per = r"(?:\s*(?:per user|/seat|per seat))?\s*(?:/\s?(?P<p1>month|mo|day|week|year|yr)\b|\b(?:a|per)\s+(?P<p2>month|day|week|year)\b|\b(?P<p3>monthly|daily|weekly|yearly|annually|per annum)\b)?"
    mnum = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d{1,2})?(?!\d|,\d))"
    money_pats = [
        rf"(?P<cur>{sym})\s?(?P<n>{mnum})(?P<sc>{SCALE}){per}",
        rf"\b(?P<cur>{codes})\s?(?P<n>{mnum})(?P<sc>{SCALE}){per}",
        rf"(?P<n>{mnum})(?P<sc>{SCALE})\s?(?P<cur>{codes}|euros?|dollars?|lei)\b{per}",
    ]
    for pat in money_pats:
        for m in re.finditer(pat, text):
            cur = m.group("cur")
            cur = CURRENCY_SYM.get(cur) or CURRENCY_WORDS.get(cur.lower()) or cur.upper()
            n = m.group("n")
            if re.fullmatch(r"\d+,\d{1,2}", n):
                n = n.replace(",", ".")
            elif "," in n and not re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", n):
                continue
            v = {"kind": "money", "value": scaled(n, m.group("sc")), "currency": cur}
            p = m.group("p1") or m.group("p2") or m.group("p3")
            if p:
                p = p.lower()
                p = {"mo": "month", "yr": "year", "monthly": "month", "daily": "day", "weekly": "week",
                     "yearly": "year", "annually": "year", "per annum": "year"}.get(p, p)
                v["per"] = p
            add(v, *m.span())
    # percent
    for m in re.finditer(rf"\b({NUM})\s?(?:%|percent\b|per cent\b)", text, re.I):
        add({"kind": "percent", "value": scaled(m.group(1), None)}, *m.span())
    # versions
    for m in re.finditer(r"\b(?:v|version\s|ver\.\s?)(\d+(?:\.\d+)*)\b", text, re.I):
        add({"kind": "version", "value": m.group(1)}, *m.span())
    for m in re.finditer(r"\b\d+\.\d+\.\d+\b", text):
        add({"kind": "version", "value": m.group(0)}, *m.span())
    for m in re.finditer(r"\b[A-Z][\w/]*\s(\d+\.\d+)\b(?!\s?(?:%|inch|in\b|GB|MB|TB|kg|g\b|mm|cm|km|GHz|MHz|Hz|W\b|kW|mAh|s\b|ms\b|h\b|min|sec|second|hour|day|week|month|year|million|billion|bn|k\b|M\b|\"))", text):
        add({"kind": "version", "value": m.group(1)}, m.start(1), m.end(1))
    # durations
    du = "|".join(sorted(DUR_UNITS, key=len, reverse=True))
    for m in re.finditer(rf"\b({NUM}|an?)[\s-]?({du})s?\b", text, re.I):
        n, u = m.group(1), m.group(2)
        u_l = u.lower()
        if len(u) == 1 and u != u_l:
            continue
        if n.lower() in ("a", "an"):
            pre = text[max(0, m.start() - 12):m.start()].lower()
            if not re.search(r"(under|within|in|for|over|than|at least|at most|to|only|just|about|around)\s*$", pre):
                continue
            n = "one"
        val = num(n)
        unit = DUR_UNITS[u_l] if u_l in DUR_UNITS else DUR_UNITS.get(u_l.rstrip("s"))
        if unit is None:
            continue
        if u_l == "fortnight":
            val *= 2
        if u_l == "decade":
            val *= 10
        add({"kind": "duration", "value": int(val) if float(val).is_integer() else val, "unit": unit}, *m.span())
    # physical / data quantities
    un = "|".join(sorted(UNITS, key=len, reverse=True))
    for m in re.finditer(rf"\b({NUM})(?:\s?|-)({un})s?\b|\b({NUM})(\"|″)", text, re.I):
        if m.group(3):
            add({"kind": "quantity", "value": scaled(m.group(3), None), "unit": "in"}, *m.span())
            continue
        u = m.group(2)
        key = u.lower()
        if u in ("M", "m") and u == "M":
            continue
        unit = UNITS.get(key)
        if key in ("mw",) and u == "MW":
            continue
        if unit and len(u) <= 3 and key in DATA_UNITS and u[-1] == "b" and u.lower() not in ("kb", "mb", "gb", "tb"):
            continue
        if unit:
            add({"kind": "quantity", "value": scaled(m.group(1), None), "unit": unit}, *m.span())
    # counted nouns
    for m in re.finditer(rf"\b({NUM})({SCALE})(\+)?\s+((?:[A-Za-z][\w-]*\s+){{0,2}}?)([A-Za-z][A-Za-z-]+)\b", text, re.I):
        n = m.group(1)
        if re.fullmatch(r"(19|20)\d\d", n):
            continue
        noun = m.group(5)
        mid = m.group(4).split()
        if noun.lower() in NOUN_STOP or any(w.lower() in NOUN_STOP - {"of"} for w in mid):
            # allow "10,000 of our customers"
            if not (mid and mid[0].lower() == "of"):
                continue
        words = [w for w in mid if w.lower() not in NOUN_STOP] + [noun]
        v = {"kind": "quantity", "value": scaled(n, m.group(2) or None), "unit": singular(words[0])}
        v["alt_units"] = [singular(w) for w in words]
        add(v, *m.span())
    for m in re.finditer(r"\b(?:in|founded in|since|from|by|until)\s+((?:19|20)\d\d)\b", text):
        add({"kind": "date", "value": m.group(1)}, m.start(1), m.end(1))
    out.sort(key=lambda v: v["span"])
    return out


def negated(text, pos=None):
    """True when the clause around pos (or the whole text) holds a negation."""
    if pos is None:
        return bool(NEGATION.search(text))
    start = max(text.rfind(c, 0, pos) for c in ".,;:!?•·|") + 1
    return bool(NEGATION.search(text[start:pos]))


def canon(v):
    """Comparable key of a value, unit-normalised where units convert."""
    k = v["kind"]
    if k == "quantity":
        u = UNITS.get(v["unit"].lower(), v["unit"]) if v["unit"].lower() in UNITS and v["unit"] not in ("M",) else v["unit"]
        conv = {"B": ("B", 1), "KB": ("B", 1e3), "MB": ("B", 1e6), "GB": ("B", 1e9), "TB": ("B", 1e12),
                "mm": ("m", 1e-3), "cm": ("m", 1e-2), "m": ("m", 1), "km": ("m", 1e3), "in": ("m", 0.0254),
                "g": ("g", 1), "kg": ("g", 1e3), "Hz": ("Hz", 1), "kHz": ("Hz", 1e3), "MHz": ("Hz", 1e6),
                "GHz": ("Hz", 1e9), "mW": ("W", 1e-3), "W": ("W", 1), "kW": ("W", 1e3)}
        if u in conv:
            base, f = conv[u]
            return ("quantity", base, round(float(v["value"]) * f, 6))
        return ("quantity", singular(u), float(v["value"]))
    if k == "duration":
        sec = {"ms": 1e-3, "s": 1, "min": 60, "h": 3600, "day": 86400, "week": 604800}
        if v["unit"] in sec:
            return ("duration", "s", round(float(v["value"]) * sec[v["unit"]], 6))
        months = {"month": 1, "year": 12}
        return ("duration", "mo", float(v["value"]) * months[v["unit"]])
    if k == "money":
        return ("money", v["currency"], v.get("per"), float(v["value"]))
    if k == "percent":
        return ("percent", float(v["value"]))
    if k == "name":
        return ("name", str(v["value"]).lower())
    if k == "boolean":
        return ("boolean", bool(v["value"]))
    return (k, str(v["value"]))


def slot(v):
    """The 'kind slot' of a value: what attribute family it can belong to."""
    c = canon(v)
    if c[0] == "quantity":
        return ("quantity", c[1])
    if c[0] == "money":
        return ("money", c[1], c[2])
    return (c[0],)
