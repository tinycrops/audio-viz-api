"""keys.py add NAME [--daily N] | list | revoke NAME.  A key is shown once; only its sha256 is stored (keys.json, mode 600)."""
import hashlib, json, os, secrets, sys
from pathlib import Path
P = Path(os.environ.get("MS_KEYS", Path(__file__).resolve().parent / "keys.json"))
def load(): return json.loads(P.read_text()) if P.exists() else {}
def save(d): P.write_text(json.dumps(d, indent=1)); os.chmod(P, 0o600)
if __name__ == "__main__":
    c, d = sys.argv[1], load()
    if c == "add":
        name = sys.argv[2]; daily = int(sys.argv[sys.argv.index("--daily") + 1]) if "--daily" in sys.argv else 2
        k = "ms_" + secrets.token_urlsafe(24); d[name] = dict(sha=hashlib.sha256(k.encode()).hexdigest(), daily=daily, revoked=False); save(d); print(k)
    elif c == "list":
        for n, v in d.items(): print(n, "daily", v["daily"], "REVOKED" if v["revoked"] else "active")
    elif c == "revoke": d[sys.argv[2]]["revoked"] = True; save(d)
