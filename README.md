# audio-viz-api

![real output: a floating ASCII moon, darkness passing in front of it in time with the music](preview/eclipse.gif)

*Above: real output from a private renderer that plugs in through `MS_RENDERER`. A track's energy becomes light; three different generative ASCII brains each melt and redraw it in their own texture, glyphs mixed across writing systems; amber marks cells being rewritten. Below: what this repo's default renderer returns out of the box.*

![default renderer output](preview/default-renderer.gif)

**Send a sound, get back something to watch.** A radio plays its own audio; this gives it a picture that moves with the music. Open the live server's landing page for the full-quality clip, or call the free `preview` tool from any MCP client before deciding anything.

An **audio-visualization request API + MCP server**. A client (a person, an agent, a radio's automation) sends audio or a waveform feed and gets back a video
layer. Standard library only; the default renderer needs `ffmpeg`.

```
python3 keys.py add my-radio --daily 5      # prints the key once; only its hash is stored
MS_HOST=127.0.0.1 MS_PORT=8921 python3 server.py
```

## Example (this is the request that made the second clip)

```bash
curl -s https://YOUR-SERVER/v1/films -H "Authorization: Bearer YOUR_KEY" -d '{
  "envelope": {"peaks": [0.1, 0.9, 0.3, 0.8, 0.2, 0.7, 0.4, 1.0, 0.1, 0.6, 0.3, 0.9], "duration": 6},
  "secs": 6, "title": "my radio" }'
# -> {"id": "f33f62e2c84f", "state": "queued", ...}      then poll GET /v1/films/ID until "done", and GET /v1/films/ID/video
```
A waveform feed gives a silent picture layer (the radio keeps its own sound); send `audio_url` or `audio_b64` and the picture follows the spectrum too.

## Ask for a visualization

REST (header `Authorization: Bearer KEY`):
```
POST /v1/films   {"audio_url": "https://..." | "audio_b64": "..." | "audio_json_url": "https://..." | "music_slug": "..."
                  | "envelope": {"hz": 20, "values": [...]} | {"peaks": [...], "duration": 200} | "peaks_url": "https://...",
                  "secs": 64, "mux_audio": true, "title": "..."}
GET  /v1/films           your requests              GET /v1/films/ID         queued | running | done | failed
GET  /v1/films/ID/video  the mp4 when done          GET /v1/music            library tracks (optional)
```
MCP: `POST /mcp` (JSON-RPC 2.0) with tools `list_music`, `request_visualization`, `film_status`, `list_films`.
```json
{"mcpServers": {"audio-viz": {"type": "http", "url": "http://127.0.0.1:8921/mcp", "headers": {"Authorization": "Bearer YOUR_KEY"}}}}
```
- **A radio has its own sound**, so send a waveform (`envelope`, or the `{peaks, duration}` overview many players expose) and you get a silent picture layer back.
  With only a waveform the visual follows amplitude; with audio it can follow the spectrum.
- `audio_json_url` takes a JSON response that carries base64 audio (a generation service's poll status, field `audio_data` by default).
- Input URLs must be public http(s): private, loopback and link-local addresses are refused, so a key is not a way into the operator's network.
- 5-90 s per request, audio up to 40 MB, a daily quota per key, `MS_MAX_JOBS` renders at a time.

## Renderers

`renderers/waveform.py` (default) draws a waveform plus a scrolling spectrum with ffmpeg. Set `MS_RENDERER="python3 /path/to/your_renderer.py"` to use another one.
Contract: `RENDERER (--audio FILE | --envelope JSON) [--secs N] [--nomux] --out DIR` writes `DIR/film.mp4`; envelope JSON is `{"hz": N, "values": [0..1, ...]}`.

## Configuration (environment)
`MS_HOST` (127.0.0.1), `MS_PORT` (8921), `MS_DATA` (./data), `MS_KEYS` (keys.json), `MS_MUSIC_DIR` (optional folder with `catalog.json`:
`{"tracks": [{"slug", "file", "seconds", "film"}]}`), `MS_RENDERER`, `MS_MAX_JOBS` (1).

The server speaks plain HTTP and has key auth only. Keep it on a private interface, or put TLS and your own access controls in front of it before exposing it.

## Tests
`python3 -m unittest discover -s tests` starts the real server and renders real videos (needs `ffmpeg` and `ffprobe`).

## Deploy live on Modal (scale to zero)

```
pip install modal && modal setup
modal deploy modal_app.py                                   # -> https://<workspace>--audio-viz-api-web.<region>.modal.run  (MCP at /mcp)
modal run modal_app.py::add_key --name my-radio --daily 5   # prints a key once
```
The web function and the render function both scale to zero, so nothing runs or bills while idle. Data and key hashes live in a Modal Volume (`audio-viz-data`).
A request returns at once and renders in a separate 2-core function (`max_containers=2`); the daily quota per key bounds spend. TLS is Modal's. Point an MCP client at
`https://<your-url>/mcp` with `Authorization: Bearer KEY`. `modal run modal_app.py::list_keys` / `::revoke_key --name X` manage keys.
