# api/update_monke_count.py
import json, os, time, urllib.parse
from http.server import BaseHTTPRequestHandler
import requests

UPSTASH_URL   = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
API_KEY       = os.environ.get("MONKE_API_KEY", "")  # simple shared secret

# Redis keys
ZSET_SERIES = "monke:series"     # sorted set of (score=unix_ts, member=json)
HASH_CURR   = "monke:current"    # hash for the latest snapshot

def runcmd(cmd, *args):
    # Upstash REST (pipeline one command): returns {"result": ...}
    payload = {"cmd": cmd, "args": list(args)}
    r = requests.post(
        f"{UPSTASH_URL}/pipeline",
        headers={"Authorization": f"Bearer {UPSTASH_TOKEN}",
                 "Content-Type": "application/json"},
        data=json.dumps([payload]),
        timeout=5,
    )
    r.raise_for_status()
    return r.json()[0]["result"]

def zadd_series(ts, item_json):
    return runcmd("ZADD", ZSET_SERIES, "NX", ts, item_json)

def ztrim_older_than(cutoff_ts):
    return runcmd("ZREMRANGEBYSCORE", ZSET_SERIES, "-inf", cutoff_ts)

def zrange_24h(from_ts):
    return runcmd("ZRANGEBYSCORE", ZSET_SERIES, from_ts, "+inf")

def hset_current(snapshot):
    # Flatten dict into [k1, v1, k2, v2, ...]
    flat = []
    for k, v in snapshot.items():
        flat.extend([k, str(v)])
    return runcmd("HSET", HASH_CURR, *flat)

def hgetall_current():
    return runcmd("HGETALL", HASH_CURR)

def parse_form(body):
    parsed = urllib.parse.parse_qs(body)
    # take first value for each key
    return {k: v[0] for k, v in parsed.items()}

def parse_body(content_type, raw):
    if (content_type or "").startswith("application/json"):
        return json.loads(raw or "{}")
    # default: x-www-form-urlencoded (UnityWebRequest.Post)
    return parse_form(raw or "")

def ok(self, obj):
    data = json.dumps(obj).encode()
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.send_header("Cache-Control", "no-store")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)

def bad(self, code, msg):
    data = json.dumps({"error": msg}).encode()
    self.send_response(code)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-API-Key")
        self.end_headers()

    def do_POST(self):
        # simple shared-secret gate
        if API_KEY and self.headers.get("X-API-Key") != API_KEY:
            return bad(self, 401, "unauthorized")

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            payload = parse_body(self.headers.get("Content-Type",""), raw)
        except Exception:
            return bad(self, 400, "invalid body")

        # expected fields from Unity
        try:
            count = int(payload.get("player_count"))
        except Exception:
            return bad(self, 400, "player_count required (int)")

        now = int(time.time())

        snapshot = {
            "player_count": count,
            "room_name": payload.get("room_name", ""),
            "game_version": payload.get("game_version", ""),
            "game_name": payload.get("game_name", ""),
            "timestamp": now,
        }

        # store time-series (24h window) + latest
        try:
            zadd_series(now, json.dumps({"t": now, "c": count}))
            ztrim_older_than(now - 24*3600)
            hset_current(snapshot)
        except Exception as e:
            return bad(self, 500, f"storage error: {e}")

        return ok(self, {"ok": True})

    def do_GET(self):
        # Read current + last 24h + peak
        now = int(time.time())
        from_ts = now - 24*3600
        try:
            series_raw = zrange_24h(from_ts)
            # series_raw is a flat list of members (because we didn’t ask WITHSCORES)
            series = [json.loads(s) for s in series_raw] if series_raw else []
            peak = max((pt["c"] for pt in series), default=0)
            # current hash to dict
            curr = hgetall_current() or {}
        except Exception as e:
            return bad(self, 500, f"read error: {e}")

        return ok(self, {
            "current": curr,           # latest snapshot hash
            "peak_24h": peak,          # integer
            "last_24h": series         # [{t, c}, ...]
        })
