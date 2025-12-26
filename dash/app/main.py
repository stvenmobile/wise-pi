from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
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

# State Management
_last = {"ts": 0, "content": None, "type": "quote"}

ROTATION_CFG = CFG.get("rotation", {})
ROTATION_SEQUENCE = ROTATION_CFG.get("sequence", ["weather", "quote", "art"])
DURATIONS = ROTATION_CFG.get("durations_seconds", {})

# --- Helper: Universal Fallback (Only used if ALL sources fail) ---
def get_fallback_quote():
    fallback = CFG.get("fallback_quotes", [])
    if fallback:
        now_int = int(time.time())
        item = fallback[now_int % len(fallback)]
        return {"quote": item["q"], "author": item["a"]}
    return {"quote": "System Offline", "author": "Please check logs"}

# --- Core Fetch Functions ---

def fetch_weather():
    cfg_weather = CFG.get("weather", {})
    api_key = os.environ.get("OPENWEATHER_API_KEY") 
    lat = cfg_weather.get("lat")
    lon = cfg_weather.get("lon")

    if not (api_key and lat and lon):
        return None, "Missing API Key (ENV) or Geo Config (YAML)"

    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
    
    max_retries = 2 # Initial + 1 Retry
    retry_delay_sec = 1 
    
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status() 
            data = r.json()
            
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
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEBUG FETCH: Weather SUCCESS.")
            return forecast, None
            
        except Exception as e:
            if attempt < max_retries - 1:
                 time.sleep(retry_delay_sec)
                 continue 
            
            error_msg = f"Weather failed after {max_retries} attempts: {type(e).__name__}"
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}")
            return None, error_msg
            
    return None, "Unexpected failure."



def fetch_quote():
    url = "https://zenquotes.io/api/random"
    max_retries = 2
    timeout_sec = 12

    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=timeout_sec)
            r.raise_for_status() 
            data = r.json()
            
            # Check if the quote text ('q') is actually present and not empty
            if not data or not data[0].get('q'):
                raise ValueError("Empty quote data received")

            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEBUG FETCH: Quote SUCCESS.")
            return {"quote": data[0]["q"], "author": data[0]["a"]}, None
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            
            error_msg = f"Quote failed after {max_retries} attempts: {type(e).__name__}"
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}")
            return None, error_msg
            
    return None, "Unexpected failure."



def fetch_art():
    MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
    MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
    
    max_retries = 2 # Added retry logic for the search phase

    for attempt in range(max_retries):
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
                return None, "No object IDs found in search."

            max_sample = 100 
            sample_ids = random.sample(object_ids, min(max_sample, len(object_ids)))
            
            # If search succeeded, break the retry loop and proceed to image fetch
            break 

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            return None, f"Met Art Search failed: {type(e).__name__}"

    # Try to find a valid image in the sample (Internal loop, not a network retry)
    for obj_id in sample_ids:
        try:
            r_object = requests.get(f"{MET_OBJECT_URL}/{obj_id}", timeout=5)
            r_object.raise_for_status()
            obj_data = r_object.json()
            
            if (obj_data.get('primaryImageSmall') and 
                obj_data.get('primaryImageWidth', 0) >= obj_data.get('primaryImageHeight', 0)):
                
                art_payload = {
                    "image_url": obj_data['primaryImageSmall'], 
                    "title": obj_data.get('title', 'Untitled'),
                    "artist": obj_data.get('artistDisplayName', 'Unknown Artist'),
                    "date": obj_data.get('objectDate', 'Unknown Date')
                }
                return art_payload, None

        except Exception:
            continue

    return None, "Could not find a suitable image in sample."

# --- Helper Functions ---

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
    
    # 1. Check Cache
    if _last["content"] and (now - _last["ts"] < current_duration):
        return JSONResponse({"content": _last["content"], "type": current_type, "cached": True})

    # 2. Determine Next Type
    start_type = get_next_type(current_type)
    
    # --- FAILOVER LOOP: Attempt to find valid content ---
    tried_types = set()
    next_type = start_type
    new_content = None
    err = None
    
    # Keep trying until we find content or have tried every type
    while new_content is None and next_type not in tried_types:
        fetch_func = get_fetch_function(next_type)
        
        if not fetch_func:
            tried_types.add(next_type)
            next_type = get_next_type(next_type)
            continue
            
        new_content, err = fetch_func()
        
        if new_content is None:
            # If failed, log it, mark this type as tried, and move to next
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] FAILOVER: {next_type} failed ({err}). Trying next.")
            tried_types.add(next_type)
            next_type = get_next_type(next_type)
    
    # 3. Final Result Handling
    if new_content is None:
        # If absolutely everything failed, use the hardcoded fallback quote
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] CRITICAL: All sources failed.")
        fallback = get_fallback_quote()
        return {"quote": fallback["quote"], "author": fallback["author"], "type": "quote", "cached": False}

    # 4. Success Path
    content_type = next_type # The type that actually succeeded
    _last.update({"content": new_content, "type": content_type, "ts": now})
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEBUG ROTATE: Selected {content_type}.")

    if content_type == 'quote':
        return {"quote": new_content["quote"], "author": new_content["author"], "type": "quote", "cached": False}
    else:
        return {"content": new_content, "type": content_type, "cached": False}


@app.get("/api/theme")
def api_theme():
    return CFG.get("theme", {})

@app.get("/api/quote")
def redirect_old_quote_endpoint():
    return RedirectResponse(url="/api/content")

