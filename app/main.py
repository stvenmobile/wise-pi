from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import RedirectResponse
import os
import time
import requests
import random
from pathlib import Path
import yaml

# --- Configuration and Initialization ---
ROOT = Path(__file__).parent
try:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        CFG = yaml.safe_load(f)
except FileNotFoundError:
    CFG = {}
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR STARTUP: config.yaml not found.")

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

# State Management (Tracks current type and last update time)
_last = {"ts": 0, "content": None, "type": "quote"}

# Define the sequence and durations from config
ROTATION_CFG = CFG.get("rotation", {})
ROTATION_SEQUENCE = ROTATION_CFG.get("sequence", ["weather", "quote", "art"])
DURATIONS = ROTATION_CFG.get("durations_seconds", {})

# --- Universal Fallback ---
def get_fallback_quote():
    fallback = CFG.get("fallback_quotes", [])
    if fallback:
        now_int = int(time.time())
        item = fallback[now_int % len(fallback)]
        return {"quote": item["q"], "author": item["a"]}
    return None

# --- Core Fetch Functions ---

def fetch_weather():
    cfg_weather = CFG.get("weather", {})
    api_key = os.environ.get("OPENWEATHER_API_KEY") 
    lat = cfg_weather.get("lat")
    lon = cfg_weather.get("lon")

    if not (api_key and lat and lon):
        return get_fallback_quote(), "Missing API Key (ENV) or Geo Config (YAML)"

    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
    
    max_retries = 3
    retry_delay_sec = 1 
    
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status() 
            data = r.json()
            
            # Data extraction logic
            forecast = []
            seen_days = set()
            for item in data['list']:
                 day_ts = item['dt_txt'].split(' ')[0]
                 if day_ts not in seen_days and len(forecast) < 5:
                    forecast.append({
                        "day": day_ts,
                        "temp": item['main']['temp'],
                        "desc": item['weather'][0]['description'],
                        "icon": item['weather'][0]['icon']
                    })
                    seen_days.add(day_ts)
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEBUG FETCH: Weather SUCCESS (Status {r.status_code}).")
            return forecast, None
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}"
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEBUG FETCH: Weather FAILED (HTTP {e.response.status_code}). Falling back.")
            return get_fallback_quote(), error_msg
            
        except Exception as e:
            if attempt < max_retries - 1:
                 time.sleep(retry_delay_sec)
                 continue 
            error_msg = f"{type(e).__name__}: {str(e)}"
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEBUG FETCH: Weather FAILED ({type(e).__name__}). Falling back.")
            return get_fallback_quote(), error_msg
    return get_fallback_quote(), "Unknown failure after maximum retries."


def fetch_quote():
    url = "https://zenquotes.io/api/random"
    max_retries = 3
    timeout_sec = 12

    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=timeout_sec)
            r.raise_for_status() 
            data = r.json()
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEBUG FETCH: Quote SUCCESS (Status {r.status_code}).")
            return {"quote": data[0]["q"], "author": data[0]["a"]}, None
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEBUG FETCH: Quote FAILED (Max Retries). Falling back.")
                return get_fallback_quote(), f"Max retries exceeded. Last error: {type(e).__name__}"
            time.sleep(0.5)
            
    return get_fallback_quote(), "Unexpected failure."


def fetch_art():
    MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
    MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
    
    try:
        search_params = {
            'q': 'painting OR print OR photograph', 
            'hasImages': 'true',
            'isPublicDomain': 'true' 
        }
        r_search = requests.get(MET_SEARCH_URL, params=search_params, timeout=10)
        r_search.raise_for_status()
        search_data = r_search.json()
        
        object_ids = search_data.get('objectIDs', [])
        if not object_ids:
            return get_fallback_quote(), "No object IDs found in search."

        # Sample up to 100 IDs to make landscape search more resilient
        max_sample = 100 
        sample_ids = random.sample(object_ids, min(max_sample, len(object_ids)))
        
    except Exception as e:
        return get_fallback_quote(), f"Met Art Search failed: {type(e).__name__}"

    for obj_id in sample_ids:
        try:
            r_object = requests.get(f"{MET_OBJECT_URL}/{obj_id}", timeout=5)
            r_object.raise_for_status()
            obj_data = r_object.json()
            
            # --- UPDATED LOGIC: width >= height (Includes square images) ---
            if (obj_data.get('primaryImageSmall') and 
                obj_data.get('primaryImageWidth', 0) >= obj_data.get('primaryImageHeight', 0)):
                
                art_payload = {
                    "image_url": obj_data['primaryImageSmall'], 
                    "title": obj_data.get('title', 'Untitled'),
                    "artist": obj_data.get('artistDisplayName', 'Unknown Artist'),
                    "date": obj_data.get('objectDate', 'Unknown Date')
                }
                return art_payload, None

        except Exception as e:
            continue

    return get_fallback_quote(), "Could not find a suitable landscape or square image in sample."

# --- Helper Functions and Root Route ---

@app.get("/")
def root():
    return FileResponse(str(ROOT / "static" / "index.htm"))

def get_next_type(current_type):
    try:
        current_index = ROTATION_SEQUENCE.index(current_type)
        next_index = (current_index + 1) % len(ROTATION_SEQUENCE)
        return ROTATION_SEQUENCE[next_index]
    except ValueError:
        return ROTATION_SEQUENCE[0]

def get_fetch_function(content_type):
    if content_type == 'weather':
        return fetch_weather
    if content_type == 'quote':
        return fetch_quote
    if content_type == 'art':
        return fetch_art
    return None

# --- API Endpoint Handlers ---

@app.get("/api/content")
def api_content():
    global _last
    now = time.time()
    
    current_type = _last["type"]
    current_duration = DURATIONS.get(current_type, 60)
    
    # 1. Check Cache and Duration
    if _last["content"] and (now - _last["ts"] < current_duration):
        return JSONResponse({"content": _last["content"], "type": current_type, "cached": True})

    # 2. Determine the NEXT content type and Fetch
    next_type = get_next_type(current_type)
    fetch_func = get_fetch_function(next_type)
    
    if not fetch_func:
        return JSONResponse({"error": f"Unknown content type: {next_type}"}, status_code=500)

    # 3. Fetch the new content
    new_content, err = fetch_func()
    
    # Determine the actual content type returned (might be a fallback quote)
    content_type = 'quote' if isinstance(new_content, dict) and 'quote' in new_content else next_type
    
    # Log the result of the entire content cycle
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEBUG ROTATE: Attempted {next_type}. Result: {content_type}. Error: {err}")

    # 4. Success / Fallback
    if new_content:
        _last.update({"content": new_content, "type": content_type, "ts": now})
        
        # Format output based on content type
        if content_type == 'quote':
            return {"quote": new_content["quote"], "author": new_content["author"], "type": "quote", "cached": False}
        else:
            return {"content": new_content, "type": content_type, "cached": False}
        
    # Should be unreachable due to universal fallback
    return JSONResponse({"error": "Content fetch failed, no fallback available."}, status_code=503)


@app.get("/api/theme")
def api_theme():
    return CFG.get("theme", {})

@app.get("/api/quote")
def redirect_old_quote_endpoint():
    # Redirects old client requests to the new content handler
    return RedirectResponse(url="/api/content")
