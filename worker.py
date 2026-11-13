"""Runs one visualization job: waits its turn (MS_MAX_JOBS at a time, via file locks), runs the renderer, records state.json.
  worker.py FILM_DIR [renderer args...]"""
import fcntl, json, os, subprocess, sys, time
from pathlib import Path
d = Path(sys.argv[1]); args = sys.argv[2:]; lockdir = d.parent / ".locks"; lockdir.mkdir(exist_ok=True)
def state(s, **k): (d / "state.json").write_text(json.dumps(dict(state=s, at=time.strftime("%F %T"), **k)))
state("queued"); slots = int(os.environ.get("MS_MAX_JOBS", 1)); held = None
while held is None:
    for i in range(slots):
        f = open(lockdir / f"slot{i}", "w")
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); held = f; break
        except OSError: f.close()
    else: time.sleep(2)
state("running")
renderer = os.environ.get("MS_RENDERER", f"{sys.executable} {Path(__file__).resolve().parent}/renderers/waveform.py").split()
r = subprocess.run(renderer + args + ["--out", str(d)], capture_output=True, text=True)
(d / "render.log").write_text((r.stdout + r.stderr)[-4000:])
state("done" if r.returncode == 0 and (d / "film.mp4").exists() else "failed", exit=r.returncode)
