"""Deploy audio-viz-api as a live MCP + REST server on Modal (scale to zero: nothing runs, and nothing bills, while idle).
  modal deploy modal_app.py                                  -> https://<workspace>--audio-viz-api-web.modal.run  (MCP at /mcp, REST at /v1/...)
  modal run modal_app.py::add_key --name my-radio --daily 5   -> prints a key once (only its hash is kept, in the Volume)
  modal run modal_app.py::list_keys   |   modal run modal_app.py::revoke_key --name my-radio
Renders run as their own function (cpu=2), so a request returns at once and `film_status` / `GET /v1/films/ID` report progress.
Swap the renderer with MS_RENDERER in the image env; the default draws a waveform + spectrum with ffmpeg."""
import modal
from pathlib import Path

HERE = Path(__file__).resolve().parent
app = modal.App("audio-viz-api")
vol = modal.Volume.from_name("audio-viz-data", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12").pip_install("numpy", "imageio-ffmpeg").run_commands("ln -sf $(python -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())') /usr/local/bin/ffmpeg", "ffmpeg -hide_banner -filters | grep -c showwaves")
         .env({"MS_DATA": "/data/films", "MS_KEYS": "/data/keys.json", "MS_HOST": "0.0.0.0", "MS_PORT": "8000", "MS_PREVIEW": "/app/preview", "MS_PUBLIC_URL": "https://medott29--audio-viz-api-web.us-east.modal.run", "MS_MAX_JOBS": "1"})
         .add_local_file(HERE / "server.py", "/app/server.py").add_local_file(HERE / "keys.py", "/app/keys.py")
         .add_local_file(HERE / "worker.py", "/app/worker.py").add_local_dir(HERE / "renderers", "/app/renderers").add_local_dir(HERE / "preview", "/app/preview"))

@app.function(image=image, volumes={"/data": vol}, cpu=2, memory=2048, timeout=900, max_containers=2)
def render(film_dir: str, args: list, secs: int):
    """One visualization job. Same renderer contract as the local worker: RENDERER (--audio|--envelope ...) --secs N --out DIR -> DIR/film.mp4"""
    import json, os, subprocess, sys, time
    from pathlib import Path as P
    vol.reload(); d = P(film_dir)
    def state(s, **k): (d / "state.json").write_text(json.dumps(dict(state=s, at=time.strftime("%F %T"), **k))); vol.commit()
    state("running")
    r = subprocess.run(os.environ.get("MS_RENDERER", f"{sys.executable} /app/renderers/waveform.py").split() + args + ["--secs", str(secs), "--out", str(d)], capture_output=True, text=True)
    (d / "render.log").write_text((r.stdout + r.stderr)[-4000:])
    state("done" if r.returncode == 0 and (d / "film.mp4").exists() else "failed", exit=r.returncode)

@app.function(image=image, volumes={"/data": vol}, scaledown_window=60, max_containers=2, timeout=600)
@modal.concurrent(max_inputs=20)
@modal.web_server(8000, startup_timeout=30)
def web():
    import sys, threading
    sys.path.insert(0, "/app"); import server
    lock = threading.Lock()
    def before_read():
        with lock:
            try: vol.reload()
            except Exception: pass
    def after_write():
        with lock: vol.commit()
    server.HOOKS.update(spawn=lambda d, args, secs: render.spawn(str(d), args, secs), before_read=before_read, after_write=after_write)
    threading.Thread(target=server.serve, kwargs=dict(host="0.0.0.0", port=8000), daemon=True).start()

@app.function(image=image, volumes={"/data": vol})
def _keys(cmd: str, name: str = "", daily: int = 2):
    import io, contextlib, subprocess, sys
    vol.reload(); r = subprocess.run([sys.executable, "-I", "/app/keys.py", cmd] + ([name] if name else []) + (["--daily", str(daily)] if cmd == "add" else []), capture_output=True, text=True, env={"MS_KEYS": "/data/keys.json"})
    vol.commit(); return (r.stdout + r.stderr).strip()

@app.local_entrypoint()
def add_key(name: str, daily: int = 2): print(_keys.remote("add", name, daily))
@app.local_entrypoint()
def list_keys(): print(_keys.remote("list"))
@app.local_entrypoint()
def revoke_key(name: str): print(_keys.remote("revoke", name) or "revoked")
