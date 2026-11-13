"""End to end, no mocks: starts the server on a free port, asks for visualizations from audio and from a waveform feed, waits for the renders, checks the videos.
Needs ffmpeg + ffprobe. Run: python3 -m unittest discover -s tests"""
import base64, json, os, socket, subprocess, sys, tempfile, time, unittest, urllib.request, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def req(base, path, key=None, body=None):
    r = urllib.request.Request(base + path, json.dumps(body).encode() if body is not None else None, {"Authorization": f"Bearer {key}"} if key else {})
    try:
        with urllib.request.urlopen(r, timeout=30) as x: return x.status, x.read()
    except urllib.error.HTTPError as e: return e.code, e.read()

class E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = tempfile.mkdtemp(); s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        cls.env = dict(os.environ, MS_DATA=cls.t + "/data", MS_KEYS=cls.t + "/keys.json", MS_PORT=str(port), MS_HOST="127.0.0.1")
        cls.key = subprocess.check_output([sys.executable, "-I", str(ROOT / "keys.py"), "add", "a", "--daily", "3"], env=cls.env, text=True).strip()
        cls.other = subprocess.check_output([sys.executable, "-I", str(ROOT / "keys.py"), "add", "b"], env=cls.env, text=True).strip()
        cls.p = subprocess.Popen([sys.executable, "-I", str(ROOT / "server.py")], env=cls.env); cls.base = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(.1)
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=6,tremolo=f=3:d=0.8", "-ar", "44100", cls.t + "/tone.wav"], check=True)
    @classmethod
    def tearDownClass(cls): cls.p.terminate()

    def wait(self, fid):
        for _ in range(60):
            st = json.loads(req(self.base, f"/v1/films/{fid}", self.key)[1])["state"]
            if st in ("done", "failed"): return st
            time.sleep(1)
        return "timeout"
    def probe(self, fid):
        c, b = req(self.base, f"/v1/films/{fid}/video", self.key); self.assertEqual(c, 200); f = Path(self.t) / f"{fid}.mp4"; f.write_bytes(b)
        return subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(f)], text=True).split()

    def test_01_auth(self):
        self.assertEqual(req(self.base, "/v1/films")[0], 401); self.assertEqual(req(self.base, "/v1/films", "wrong")[0], 401)
    def test_02_audio_to_film_with_sound(self):
        c, b = req(self.base, "/v1/films", self.key, dict(audio_b64=base64.b64encode(Path(self.t + "/tone.wav").read_bytes()).decode(), secs=5)); self.assertEqual(c, 202)
        fid = json.loads(b)["id"]; self.assertEqual(self.wait(fid), "done"); self.assertEqual(sorted(set(self.probe(fid))), ["audio", "video"])
        self.assertEqual(req(self.base, f"/v1/films/{fid}", self.other)[0], 404)       # another key can't see it
    def test_03_waveform_feed_gives_picture_only(self):
        c, b = req(self.base, "/v1/films", self.key, dict(envelope=dict(peaks=[.1, .9, .3, .8, .2, .7, .4, 1, .1, .6, .3, .9], duration=6), secs=5)); self.assertEqual(c, 202)
        fid = json.loads(b)["id"]; self.assertEqual(self.wait(fid), "done"); self.assertEqual(self.probe(fid), ["video"])
    def test_04_private_urls_refused_and_nothing_left_behind(self):
        n = len([d for d in Path(self.t + "/data").iterdir() if d.name != ".locks"])
        for body in (dict(audio_url="http://127.0.0.1:1/x"), dict(peaks_url="http://10.0.0.1/x"), dict(envelope=dict(peaks=[1, 2, 3])), {}):
            self.assertEqual(req(self.base, "/v1/films", self.key, body)[0], 400)
        self.assertEqual(len([d for d in Path(self.t + "/data").iterdir() if d.name != ".locks"]), n)
    def test_05_mcp(self):
        def rpc(m, p=None): return json.loads(req(self.base, "/mcp", self.key, dict(jsonrpc="2.0", id=1, method=m, params=p or {}))[1])["result"]
        self.assertEqual([t["name"] for t in rpc("tools/list")["tools"]], ["list_music", "request_visualization", "film_status", "list_films"])
        r = rpc("tools/call", dict(name="request_visualization", arguments=dict(music_slug="nope"))); self.assertTrue(r["isError"])
    def test_06_daily_limit(self):
        for _ in range(3): req(self.base, "/v1/films", self.key, dict(envelope=dict(hz=2, values=[.1] * 20), secs=5))
        c, b = req(self.base, "/v1/films", self.key, dict(envelope=dict(hz=2, values=[.1] * 20), secs=5)); self.assertEqual(c, 400); self.assertIn("daily limit", b.decode())
if __name__ == "__main__": unittest.main()
