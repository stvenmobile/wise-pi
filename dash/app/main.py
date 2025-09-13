from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os, json, time
import requests
from pathlib import Path
import yaml

ROOT = Path(__file__).parent
with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

@app.get("/")
def root():
    return FileResponse(str(ROOT / "static" / "index.html"))

_last = {"ts": 0, "quote": None, "author": None}
def fetch_quote():
    url = "https://zenquotes.io/api/random"
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        data = r.json()
        q = data[0]["q"]
        a = data[0]["a"]
        return q, a, None
    except Exception as e:
        return None, None, str(e)

@app.get("/api/quote")
def api_quote():
    # simple cache so we don't hammer the API when the page reloads
    ttl = int(CFG.get("refresh_seconds", 60))
    now = time.time()
    if _last["quote"] and (now - _last["ts"] < ttl):
        return JSONResponse({"quote": _last["quote"], "author": _last["author"], "cached": True})

    q, a, err = fetch_quote()
    if q:
        _last.update({"quote": q, "author": a, "ts": now})
        return {"quote": q, "author": a, "cached": False}
    # fallback
    fallback = CFG.get("fallback_quotes", [])
    if fallback:
        item = fallback[int(now) % len(fallback)]
        q, a = item["q"], item["a"]
        _last.update({"quote": q, "author": a, "ts": now})
        return {"quote": q, "author": a, "cached": False, "fallback": True}
    return JSONResponse({"error": "quote fetch failed"}, status_code=503)

@app.get("/api/theme")
def api_theme():
    theme = CFG.get("theme", {})
    return theme
