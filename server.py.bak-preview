"""audio-viz-api: an audio-visualization request API + MCP. Key required, quotas per key, any renderer behind it.
  REST  GET /v1/music | GET /v1/films | POST /v1/films {music_slug | audio_url | audio_b64 | audio_json_url | envelope | peaks_url, secs, title, mux_audio}
        GET /v1/films/ID | GET /v1/films/ID/video
  MCP   POST /mcp (JSON-RPC 2.0): list_music, request_visualization, film_status, list_films
Config (env): MS_HOST (127.0.0.1) MS_PORT (8921) MS_DATA (./data) MS_MUSIC_DIR (optional dir with catalog.json: {"tracks":[{"slug","file","seconds","film"}]})
              MS_RENDERER (default: renderers/waveform.py) MS_MAX_JOBS (1) MS_KEYS (keys.json). Bind to a LAN or private interface unless you put your own auth proxy in front."""
import base64, hashlib, ipaddress, json, os, re, secrets, socket, subprocess, sys, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); import keys as K
FILMS = Path(os.environ.get("MS_DATA", HERE / "data")); FILMS.mkdir(parents=True, exist_ok=True)
MUSIC = Path(os.environ["MS_MUSIC_DIR"]) if os.environ.get("MS_MUSIC_DIR") else None; MAXB = 40 * 1024 * 1024
HOST, PORT = os.environ.get("MS_HOST", "127.0.0.1"), int(os.environ.get("MS_PORT", 8921))

def spawn(d, args, secs):
    """Start a render for film dir d. Replaceable: modal_app.py swaps in a Modal function."""
    subprocess.Popen([sys.executable, str(HERE / "worker.py"), str(d)] + args + ["--secs", str(secs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
HOOKS = dict(spawn=spawn, before_read=lambda: None, after_write=lambda: None)   # modal_app.py overrides these

def fetch(url, limit=MAXB):
    """GET a client-supplied URL: http(s) only, never a private/loopback/link-local address (a key must not be a way into the operator's network)."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname: raise ValueError("url must be http(s)")
    for ai in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80)):
        ip = ipaddress.ip_address(ai[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved: raise ValueError("that address is not reachable from here")
    b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "audio-viz"}), timeout=60).read(limit + 1)
    if len(b) > limit: raise ValueError("response over 40 MB")
    return b

def as_envelope(j):
    """accept {hz, values} or a {peaks, duration} waveform overview"""
    if not isinstance(j, dict): raise ValueError('waveform must be {"hz", "values"} or {"peaks", "duration"}')
    if "values" in j and j.get("hz"): e = dict(hz=float(j["hz"]), values=j["values"])
    elif "peaks" in j and j.get("duration"): e = dict(hz=len(j["peaks"]) / float(j["duration"]), values=j["peaks"])
    else: raise ValueError('waveform must be {"hz", "values"} or {"peaks", "duration"}')
    if not (10 <= len(e["values"]) <= 2_000_000) or e["hz"] <= 0: raise ValueError("waveform needs 10 to 2,000,000 values and hz > 0")
    return dict(hz=e["hz"], values=[float(x) for x in e["values"]])

def who(h, q):
    a = h.headers.get("Authorization", ""); t = (a[7:] if a.startswith("Bearer ") else (q.get("k") or [""])[0]).strip(); s = hashlib.sha256(t.encode()).hexdigest()
    for n, v in K.load().items():
        if v["sha"] == s and not v["revoked"]: return n, v
    return None, None

def catalog(): return json.loads((MUSIC / "catalog.json").read_text())["tracks"] if MUSIC and (MUSIC / "catalog.json").exists() else []
def music(): return [dict(slug=t["slug"], seconds=t.get("seconds"), title=t.get("film")) for t in catalog()]

def film(fid):
    d = FILMS / fid; m = json.loads((d / "meta.json").read_text())
    try: m["state"] = json.loads((d / "state.json").read_text())["state"]
    except Exception: m["state"] = "queued"
    m["video"] = f"/v1/films/{fid}/video" if (d / "film.mp4").exists() else None; return m

def mine(name): return [film(f.name) for f in sorted(FILMS.iterdir()) if (f / "meta.json").exists() and json.loads((f / "meta.json").read_text())["key"] == name]

def make(name, v, a):
    import shutil
    try: return _make(name, v, a)
    except Exception:
        for f in FILMS.iterdir():
            if f.is_dir() and f.name != ".locks" and not (f / "meta.json").exists(): shutil.rmtree(f, ignore_errors=True)
        raise

def _make(name, v, a):
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if sum(1 for m in mine(name) if m["day"] == today) >= v["daily"]: raise ValueError(f"daily limit reached ({v['daily']} per day for this key)")
    fid = secrets.token_hex(6); d = FILMS / fid; d.mkdir(); src = d / "input"; a = dict(a); env = None
    if a.get("peaks_url"): a["envelope"] = as_envelope(json.loads(fetch(a["peaks_url"], 5_000_000)))
    elif a.get("audio_json_url"):   # a JSON response holding base64 audio (e.g. a generation service's poll status)
        a["audio_b64"] = json.loads(fetch(a["audio_json_url"])).get(a.get("audio_json_field") or "audio_data") or ""
        if not a["audio_b64"]: raise ValueError("no audio field in that response")
    if isinstance(a.get("envelope"), dict): env = as_envelope(a["envelope"]); label = "waveform feed"
    elif a.get("music_slug"):
        t = next((x for x in catalog() if x["slug"] == a["music_slug"]), None)
        if not t: raise ValueError("unknown music_slug; call list_music")
        src = MUSIC / t["file"]; label = a["music_slug"]
    elif a.get("audio_url"): src.write_bytes(fetch(a["audio_url"])); label = "url"
    elif a.get("audio_b64"):
        b = base64.b64decode(a["audio_b64"])
        if len(b) > MAXB: raise ValueError("audio over 40 MB")
        src.write_bytes(b); label = "upload"
    else: raise ValueError("give music_slug, audio_url, audio_b64, audio_json_url, envelope or peaks_url")
    secs = max(5, min(90, int(a.get("secs") or 64)))
    if env: (d / "envelope.json").write_text(json.dumps(env)); args = ["--envelope", str(d / "envelope.json")]
    else: args = ["--audio", str(src)] + ([] if a.get("mux_audio", True) else ["--nomux"])
    (d / "meta.json").write_text(json.dumps(dict(id=fid, key=name, day=today, secs=secs, title=(a.get("title") or label)[:80], source=label, submitted=time.strftime("%F %T"))))
    HOOKS["spawn"](d, args, secs); HOOKS["after_write"]()
    return film(fid)

TOOLS = [
 dict(name="list_music", description="Tracks the operator has made available as music_slug.", inputSchema=dict(type="object", properties={})),
 dict(name="request_visualization", description="Request an audio visualization (picture) for a radio or track. Give ONE of: music_slug, audio_url (public), audio_b64, audio_json_url (JSON with base64 audio), envelope {hz, values} or {peaks, duration} (a waveform feed; amplitude only, silent output), peaks_url. mux_audio=false returns picture only. Poll film_status.",
      inputSchema=dict(type="object", properties=dict(music_slug=dict(type="string"), audio_url=dict(type="string"), audio_b64=dict(type="string"), audio_json_url=dict(type="string"), audio_json_field=dict(type="string"), peaks_url=dict(type="string"), envelope=dict(type="object"), mux_audio=dict(type="boolean"), secs=dict(type="integer", description="5-90, default 64"), title=dict(type="string")))),
 dict(name="film_status", description="State of a request (queued, running, done, failed) and its video path.", inputSchema=dict(type="object", properties=dict(id=dict(type="string")), required=["id"])),
 dict(name="list_films", description="Your requests.", inputSchema=dict(type="object", properties={}))]
def call(name, v, tool, args):
    if tool == "list_music": return music()
    if tool == "request_visualization": return make(name, v, args)
    if tool == "film_status":
        f = film(re.sub(r"\W", "", args["id"]))
        if f["key"] != name: raise ValueError("no such request")
        return f
    if tool == "list_films": return mine(name)
    raise ValueError("unknown tool")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj, ct="application/json"):
        b = obj if isinstance(obj, bytes) else json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def route(self, method):
        HOOKS["before_read"](); u = urlparse(self.path); q = parse_qs(u.query); name, v = who(self, q)
        if not name: return self.send(401, dict(error="a key is required: Authorization: Bearer KEY. Ask the operator for access."))
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}") if method == "POST" else {}
            if u.path == "/mcp" and method == "POST":
                rid, m = body.get("id"), body.get("method")
                if m == "initialize": r = dict(protocolVersion="2025-03-26", capabilities=dict(tools={}), serverInfo=dict(name="audio-viz-api", version="0.1"))
                elif m == "tools/list": r = dict(tools=TOOLS)
                elif m == "tools/call":
                    try: r = dict(content=[dict(type="text", text=json.dumps(call(name, v, body["params"]["name"], body["params"].get("arguments") or {}), indent=1))])
                    except Exception as e: r = dict(isError=True, content=[dict(type="text", text=str(e))])
                elif m and m.startswith("notifications/"): return self.send(202, b"")
                else: return self.send(200, dict(jsonrpc="2.0", id=rid, error=dict(code=-32601, message="method not found")))
                return self.send(200, dict(jsonrpc="2.0", id=rid, result=r))
            if u.path == "/v1/music": return self.send(200, music())
            if u.path == "/v1/films" and method == "GET": return self.send(200, mine(name))
            if u.path == "/v1/films" and method == "POST": return self.send(202, make(name, v, body))
            m = re.fullmatch(r"/v1/films/(\w+)(/video)?", u.path)
            if m:
                f = film(m.group(1))
                if f["key"] != name: return self.send(404, dict(error="no such request"))
                if m.group(2):
                    p = FILMS / m.group(1) / "film.mp4"
                    return self.send(200, p.read_bytes(), "video/mp4") if p.exists() else self.send(409, dict(error="not finished", state=f["state"]))
                return self.send(200, f)
            self.send(404, dict(error="not found"))
        except Exception as e: self.send(400, dict(error=str(e)))
    def do_GET(self): self.route("GET")
    def do_POST(self): self.route("POST")
def serve(host=HOST, port=PORT): ThreadingHTTPServer((host, port), H).serve_forever()
if __name__ == "__main__": serve()
