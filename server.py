"""Local dev server for the Linger prototype.

Serves prototype/ and proxies flight searches to the Duffel API so the access
token stays on the server (read from .env, never sent to the browser).

    python3 server.py            # http://localhost:8765/linger.html#flights

Endpoints
  GET /api/flights?from=BKK&to=KBV&date=2026-12-12&adults=2&cabin=economy
  GET /api/places?q=krabi
"""
import gzip
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", 8765))
DUFFEL = "https://api.duffel.com"


def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()
TOKEN = os.environ.get("DUFFEL_ACCESS_TOKEN", "")


def duffel(method, path, body=None):
    req = urllib.request.Request(
        DUFFEL + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Duffel-Version": "v2",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return 200, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        if e.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        try:
            err = json.loads(raw)["errors"][0]
            msg = err.get("message") or err.get("title")
        except Exception:
            msg = raw[:300].decode(errors="replace")
        return e.code, {"error": msg}
    except Exception as e:  # network, timeout
        return 502, {"error": str(e)}


def minutes(iso):
    """PT1H20M / P1DT2H -> minutes"""
    if not iso:
        return None
    m = re.match(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", iso)
    d, h, mi = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mi


def rule(cond):
    if not cond:
        return "Not shown by airline"
    if not cond.get("allowed"):
        return "Not allowed"
    amt = cond.get("penalty_amount")
    if amt in (None, "0.00", "0"):
        return "Free"
    return {"amount": float(amt), "currency": cond.get("penalty_currency")}


def bags(segment):
    pax = (segment.get("passengers") or [{}])[0]
    out = []
    for b in pax.get("baggages") or []:
        if b.get("quantity"):
            out.append(f"{b['quantity']} {b['type'].replace('_', '-')} bag{'s' if b['quantity'] > 1 else ''}")
    return ", ".join(out) or "No bags included"


def slim(offer):
    s = offer["slices"][0]
    segs = s["segments"]
    first, last = segs[0], segs[-1]
    owner = offer["owner"]
    return {
        "id": offer["id"],
        "airline": owner["name"],
        "code": owner.get("iata_code") or "",
        "logo": owner.get("logo_symbol_url"),
        "from": first["origin"]["iata_code"],
        "to": last["destination"]["iata_code"],
        "dep": first["departing_at"][11:16],
        "arr": last["arriving_at"][11:16],
        "arr_date": last["arriving_at"][:10],
        "dep_date": first["departing_at"][:10],
        "dur": minutes(s.get("duration")) or 0,
        "stops": len(segs) - 1,
        "via": ", ".join(x["destination"]["iata_code"] for x in segs[:-1]),
        "flights": [f"{x['marketing_carrier']['iata_code']} {x['marketing_carrier_flight_number']}" for x in segs],
        "amount": float(offer["total_amount"]),
        "currency": offer["total_currency"],
        "bags": bags(first),
        "change": rule((offer.get("conditions") or {}).get("change_before_departure")),
        "refund": rule((offer.get("conditions") or {}).get("refund_before_departure")),
        "expires_at": offer.get("expires_at"),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=os.path.join(ROOT, "prototype"), **kw)

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path.startswith("/api/") and not TOKEN:
            return self.send_json(500, {"error": "DUFFEL_ACCESS_TOKEN is missing from .env"})
        if u.path == "/api/flights":
            code_re = re.compile(r"^[A-Z]{3}$")
            o, d = q.get("from", "").upper(), q.get("to", "").upper()
            date = q.get("date", "")
            if not (code_re.match(o) and code_re.match(d) and re.match(r"^\d{4}-\d{2}-\d{2}$", date)):
                return self.send_json(400, {"error": "Use 3-letter airport codes and a YYYY-MM-DD date."})
            adults = max(1, min(9, int(q.get("adults", 1) or 1)))
            body = {"data": {
                "slices": [{"origin": o, "destination": d, "departure_date": date}],
                "passengers": [{"type": "adult"} for _ in range(adults)],
                "cabin_class": q.get("cabin", "economy"),
            }}
            status, res = duffel("POST", "/air/offer_requests?return_offers=true&supplier_timeout=15000", body)
            if status != 200:
                return self.send_json(status, res)
            offers = sorted(res["data"]["offers"], key=lambda x: float(x["total_amount"]))[:30]
            return self.send_json(200, {
                "mode": "live" if res["data"].get("live_mode") else "test",
                "offer_request_id": res["data"]["id"],
                "offers": [slim(x) for x in offers],
            })
        if u.path == "/api/places":
            status, res = duffel("GET", "/places/suggestions?query=" + urllib.parse.quote(q.get("q", "")))
            if status != 200:
                return self.send_json(status, res)
            return self.send_json(200, [{"code": p.get("iata_code"), "name": p.get("name"), "type": p.get("type"),
                                         "city": p.get("city_name"), "country": p.get("iata_country_code")} for p in res["data"]])
        return super().do_GET()

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"Linger dev server on http://localhost:{PORT}/linger.html  (Duffel token {'found' if TOKEN else 'MISSING'})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
