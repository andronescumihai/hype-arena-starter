"""Web app for the arena: serves the built frontend and runs the system live.

python web/server.py  ->  http://localhost:8000
No dependencies beyond the system's own (numpy, scikit-learn).
"""
import csv
import io
import json
import os
import sys
import time
from datetime import date as Date
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from arena.pipeline import load_practice, load_models, label_rows, read_csv, MODELS  # noqa: E402
from arena.claims import Knowledge, write_claims, render  # noqa: E402

DIST = os.path.join(ROOT, "web", "dist")
LEXICON = json.load(open(os.path.join(ROOT, "data", "lexicon.json"), encoding="utf-8"))
PRACTICE = load_practice()
if not os.path.exists(os.path.join(MODELS, "judge.pkl")):
    from arena import train
    train.main()
EXT, CLF = load_models()
METRICS = json.load(open(os.path.join(MODELS, "metrics.json")))
BT = os.path.join(MODELS, "backtest.json")
if os.path.exists(BT):
    METRICS["backtest"] = json.load(open(BT))
CLAIMS = None


def show(c):
    """A canonical value, as a person reads it."""
    k = c[0]
    if k == "quantity":
        n = c[2]
        n = int(n) if float(n).is_integer() else n
        return f"{n:,} {c[1]}" if isinstance(n, int) else f"{n} {c[1]}"
    if k == "money":
        sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(c[1], c[1] + " ")
        n = c[3]
        n = int(n) if float(n).is_integer() else n
        return f"{sym}{n:,}" + (f"/{c[2]}" if c[2] else "")
    if k == "percent":
        return f"{c[1]:g}%"
    if k == "duration":
        return f"{c[2]:g} {'s' if c[1] == 's' else 'mo'}"
    if k == "boolean":
        return "yes" if c[1] else "no"
    return str(c[1])


def iso(day):
    return Date.fromordinal(day).isoformat()


def sample_rows():
    path = os.path.join(ROOT, "sample", "sample.csv")
    if os.path.exists(path):
        return {"source": "sample/sample.csv", "rows": [
            {"id": r["id"], "text": r["text"], "date": r["date"]} for r in read_csv(path)]}
    # before the official sample exists: 20 practice rows, labels kept aside to score the demo
    picks = [r for i, r in enumerate(PRACTICE) if i % 97 == 3][:14] + \
            [r for r in PRACTICE if r["label"] == "false"][5::40][:6]
    return {"source": "practice demo (labels known)", "rows": [
        {"id": r["id"], "text": r["text"], "date": r["date"], "truth": r["label"]} for r in picks]}


def get_claims():
    global CLAIMS
    if CLAIMS is None:
        cl, dropped, n = write_claims(Knowledge(PRACTICE, LEXICON))
        CLAIMS = {"claims": cl, "dropped": dropped, "candidates": n}
    return CLAIMS


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIST, **kw)

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/meta":
            c = get_claims()
            from collections import Counter
            return self.send_json({"metrics": METRICS, "practice_rows": len(PRACTICE),
                                   "subjects": len(LEXICON["subjects"]), "events": len(LEXICON.get("events", [])),
                                   "claims_by_type": Counter(x["type"] for x in c["claims"]),
                                   "claims_candidates": c["candidates"], "claims_dropped": c["dropped"]})
        if self.path == "/api/sample":
            return self.send_json(sample_rows())
        if self.path.startswith("/api/claims"):
            c = get_claims()
            return self.send_json({"claims": c["claims"][:60], "total": len(c["claims"])})
        if not os.path.exists(os.path.join(DIST, self.path.lstrip("/").split("?")[0])) or self.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/run":
            return self.send_json({"error": "unknown endpoint"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(n) or b"{}")
        rows = payload.get("rows")
        if payload.get("csv"):
            rows = list(csv.DictReader(io.StringIO(payload["csv"])))
        truth = payload.get("truth") or {}
        rows = [{"id": str(r.get("id", i)), "text": r.get("text", ""), "date": (r.get("date") or "2026-10-29")[:10],
                 "label": "", "truth": r.get("truth") or r.get("label") or truth.get(str(r.get("id")), "")}
                for i, r in enumerate(rows or [])]
        if not rows:
            return self.send_json({"error": "Add at least one row with id, text and date."}, 400)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(obj, pause=0.0):
            self.wfile.write((json.dumps(obj) + "\n").encode())
            self.wfile.flush()
            if pause:
                time.sleep(pause)

        t0 = time.time()
        emit({"type": "stage", "agent": "extractor", "note": f"Reading {len(rows)} sentences"}, 0.5)
        result, hist, facts = label_rows(rows, LEXICON, PRACTICE, EXT, CLF)
        emit({"type": "stage", "agent": "historian",
              "note": f"Timelines for {len(hist.obs)} facts from {len(PRACTICE) + len(rows)} sources"}, 0.5)
        emit({"type": "stage", "agent": "judge", "note": "Ruling on each sentence"}, 0.3)
        right = scored = 0
        for r in rows:
            label, conf, reasons, p = result[r["id"]]
            out_facts = []
            for x in reasons:
                if "subject" not in x:
                    continue
                key = (x["subject"], x["attribute"])
                states, path, obs = hist.timeline(key)
                out_facts.append({
                    "subject": x["subject"], "attribute": x["attribute"].replace("_", " "),
                    "value": render(x["value"]) or str(x["value"].get("value")),
                    "verdict": x["verdict"], "why": x["why"],
                    "timeline": {
                        "points": [{"date": iso(o[0]), "value": show(o[1]),
                                    "kind": "self" if o[3] == r["id"] else o[4]} for o in obs][-60:],
                        "path": [[iso(d), show(v)] for d, v in sorted(path.items())][-60:],
                    }})
            if r["truth"] in ("true", "false"):
                scored += 1
                right += r["truth"] == label
            emit({"type": "row", "id": r["id"], "text": r["text"], "date": r["date"], "label": label,
                  "confidence": conf, "p_false": round(p, 3), "truth": r["truth"],
                  "why": reasons[0]["why"] if reasons else "", "facts": out_facts}, 0.18)
        emit({"type": "stage", "agent": "writer", "note": "Writing 1,000 new claims"}, 0.4)
        c = get_claims()
        emit({"type": "stage", "agent": "referee",
              "note": f"Checked {c['candidates']} candidates, dropped {sum(c['dropped'].values())}"}, 0.3)
        emit({"type": "claims", "items": c["claims"][:12], "total": len(c["claims"]),
              "by_type": {t: sum(1 for x in c["claims"] if x["type"] == t)
                          for t in ("fact", "compare", "change", "at_event", "relation")}})
        emit({"type": "done", "seconds": round(time.time() - t0, 1), "right": right, "scored": scored})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Hype or Truth Arena on http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
