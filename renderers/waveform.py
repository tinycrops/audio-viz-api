"""Default renderer: a plain ffmpeg waveform + spectrum picture. The public stack works with this; swap in a richer renderer with MS_RENDERER.
Renderer contract: RENDERER (--audio FILE | --envelope JSON) [--secs N] [--nomux] --out DIR   ->   DIR/film.mp4
(envelope JSON is {"hz": N, "values": [0..1,...]}.)"""
import argparse, json, subprocess, sys
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("--audio"); ap.add_argument("--envelope"); ap.add_argument("--secs", type=int, default=64); ap.add_argument("--nomux", action="store_true"); ap.add_argument("--out", required=True); a = ap.parse_args()
out = Path(a.out); secs = max(5, min(90, a.secs))
if a.envelope:   # synthesize a tone whose loudness follows the envelope, just to draw it; the film is picture only
    import numpy as np
    e = json.loads(Path(a.envelope).read_text()); v = np.clip(np.asarray(e["values"], float), 0, None); v = v / (v.max() or 1); sr = 16000; n = secs * sr
    amp = np.interp(np.arange(n) / sr * float(e["hz"]), np.arange(len(v)), v); wav = out / "env.wav"
    import wave; w = wave.open(str(wav), "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((np.sin(2 * np.pi * 220 * np.arange(n) / sr) * amp * 30000).astype("<i2").tobytes()); w.close(); src, nomux = str(wav), True
else: src, nomux = a.audio, a.nomux
g = "[0:a]atrim=0:%d,asplit=2[a][b];[a]showwaves=s=1280x360:mode=cline:colors=0xf0b266:rate=24[w];[b]showspectrum=s=1280x360:mode=combined:color=intensity:slide=scroll:fps=24[s];[w][s]vstack[v]" % secs
cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", src, "-filter_complex", g, "-map", "[v]"] + ([] if nomux else ["-map", "0:a", "-c:a", "aac", "-b:a", "192k"]) + ["-t", str(secs), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", str(out / "film.mp4")]
subprocess.run(cmd, check=True)
