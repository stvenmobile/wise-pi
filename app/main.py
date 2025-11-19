from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
import os
import time
import requests
import random
import logging
from pathlib import Path
import yaml
from typing import Dict, Any, Tuple, Union, List

# Local imports
from . import flickr 

# --- Configuration and Initialization ---
logging.basicConfig(level=logging.INFO)
ROOT = Path(__file__).parent

# State Management (Tracks current type and last update time)
_last = {"ts": 0, "content": None, "type": "quote"}

# Load configuration once at startup
try:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        CFG = yaml.safe_load(f)
except FileNotFoundError:
    CFG = {}
    logging.error(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR STARTUP: config.yaml not found.")
except yaml.YAMLError as e:
    CFG = {}
    logging.error(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR STARTUP: config.yaml parse error: {e}")


app = FastAPI()
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

# Define the sequence and durations from config (or use defaults if config failed)
ROTATION_CFG = CFG.get("rotation", {})
ROTATION_SEQUENCE = ROTATION_CFG.get("sequence", ["weather", "quote", "art"])
DURATIONS = ROTATION_CFG.get("durations_seconds", {})

# --- Universal Fallback ---
def get_fallback_quote() -> Dict[str, str]:
    fallback = CFG.get("fallback_quotes", [])
    if fallback:
        now_int = int(time.time())
        item = fallback[now_int % len(fallback)]
        return {"quote": item["q"], "author": item["a"]}
    return {"quote": "Error loading content.", "author": "WisePi"}

# --- Core Fetch Functions ---

def fetch_weather() -> Tuple[Union[List[Dict], Dict], Union[str, None]]:
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
            
            logging.info(f"DEBUG FETCH: Weather SUCCESS (Status {r.status_code}).")
            return forecast, None
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}"
            logging.warning(f"DEBUG FETCH: Weather FAILED (HTTP {e.response.status_code}). Falling back.")
            return get_fallback_quote(), error_msg
            
        except Exception as e:
            if attempt < max_retries - 1:
                 time.sleep(retry_delay_sec)
                 continue 
            error_msg = f"{type(e).__name__}: {str(e)}"
            logging.error(f"DEBUG FETCH: Weather FAILED ({type(e).__name__}). Falling back.")
            return get_fallback_quote(), error_msg
    return get_fallback_quote(), "Unknown failure after maximum retries."


def fetch_quote() -> Tuple[Dict[str, str], Union[str, None]]:
    url = "https://zenquotes.io/api/random"
    max_retries = 3
    timeout_sec = 12

    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=timeout_sec)
            r.raise_for_status() 
            data = r.json()
            logging.info(f"DEBUG FETCH: Quote SUCCESS (Status {r.status_code}).")
            return {"quote": data[0]["q"], "author": data[0]["a"]}, None
        except Exception as e:
            if attempt == max_retries - 1:
                logging.warning(f"DEBUG FETCH: Quote FAILED (Max Retries). Falling back.")
                return get_fallback_quote(), f"Max retries exceeded. Last error: {type(e).__name__}"
            time.sleep(0.5)
            
    return get_fallback_quote(), "Unexpected failure."


def fetch_art() -> Tuple[Union[Dict, None], Union[str, None]]:
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

        max_sample = 100 
        sample_ids = random.sample(object_ids, min(max_sample, len(object_ids)))
        
    except Exception as e:
        return get_fallback_quote(), f"Met Art Search failed: {type(e).__name__}"

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

        except Exception as e:
            continue

    return get_fallback_quote(), "Could not find a suitable landscape or square image in sample."


def fetch_flickr() -> Tuple[Union[Dict, None], Union[str, None]]:
    """Fetches a random photo from Flickr and conforms to the (content, error) tuple."""
    
    # 💡 FIX 1: Retrieve flickr_config from CFG (Resolves UnboundLocalError)
    flickr_config = CFG.get('flickr') 
    
    if not flickr_config:
        error_msg = "Flickr section missing from config.yaml."
        logging.error(f"DEBUG FETCH: Flickr FAILED (Config Missing).")
        return get_fallback_quote(), error_msg 
        
    # Call the actual Flickr logic from the imported module
    photo_data = flickr.get_random_public_photo(flickr_config)

    if not photo_data:
        error_msg = "Failed to fetch photo from Flickr."
        logging.error(f"DEBUG FETCH: Flickr FAILED (API Fail).")
        # Return fallback quote on API failure
        return get_fallback_quote(), error_msg 

    # Success: return the data and no error
    logging.info(f"DEBUG FETCH: Flickr SUCCESS.")
    
    # 💡 FIX 2: Explicitly build the final structure with image_url and required metadata 💡
    return {
        "image_url": photo_data.get("url"), 
        "title": photo_data.get("title", ""), # Added for structural consistency in case frontend needs it
        "artist": photo_data.get("artist", ""),
        "date": "" 
    }, None


def fetch_smithsonian() -> Tuple[Union[Dict, None], Union[str, None]]:
    cfg_smithsonian = CFG.get("smithsonian", {})
    api_key = os.environ.get(cfg_smithsonian.get("api_key_env_var"))

    if not api_key:
        return get_fallback_quote(), "Missing Smithsonian API Key (ENV)."

    # The specific topics you want to cycle through
    topics = [
        'topic:"Impressionism"',
        'topic:"Painting, American"',
        'topic:"Painting, Japanese"',
        'topic:"Painting, French"'
    ]
    
    # Randomly select one topic for the current fetch
    query_topic = random.choice(topics)

    # Base parameters including the specific topic and random sort
    params = {
        'q': query_topic,
        'rows': 50,
        'sort': 'random',
        'type': 'online_media', # Ensures we get items with image links
        'api_key': api_key
    }
    
    url = "https://api.si.edu/openaccess/api/v1.0/search"
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # Check for results and sample the first item (since it's randomly sorted)
        hits = data.get('response', {}).get('rows', [])
        
        if not hits:
            return get_fallback_quote(), f"Smithsonian search found no results for query: {query_topic}"

        # Select the first item, as the API has already randomly sorted the 50 results
        item = hits[0] 
        
        # Extract the primary image URL and metadata
        image_url = item.get('content', {}).get('online_media', {}).get('media', [{}])[0].get('url')
        
        if not image_url:
             return get_fallback_quote(), "Smithsonian item lacks a public image URL."

        smithsonian_payload = {
            "image_url": image_url,
            "title": item.get('title', 'Untitled'),
            # The 'name' field is used for artist in the Smithsonian structure
            "artist": item.get('content', {}).get('freetext', {}).get('name', ['Unknown Artist'])[0],
            "date": item.get('date', 'Unknown Date')
        }
        
        logging.info(f"DEBUG FETCH: Smithsonian SUCCESS for topic: {query_topic}")
        return smithsonian_payload, None

    except Exception as e:
        error_msg = f"Smithsonian API failed: {type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        return get_fallback_quote(), error_msg



# --- Helper Functions and Root Route ---

@app.get("/")
def root():
    return FileResponse(str(ROOT / "static" / "index.htm"))

def get_next_type(current_type: str) -> str:
    try:
        current_index = ROTATION_SEQUENCE.index(current_type)
        next_index = (current_index + 1) % len(ROTATION_SEQUENCE)
        return ROTATION_SEQUENCE[next_index]
    except ValueError:
        return ROTATION_SEQUENCE[0]

def get_fetch_function(content_type: str) -> Union[callable, None]:
    if content_type == 'weather':
        return fetch_weather
    if content_type == 'quote':
        return fetch_quote
    if content_type == 'art':
        return fetch_art
    if content_type == 'smithsonian':
        return fetch_smithsonian
    if content_type == 'flickr':
        return fetch_flickr
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
    
    # Determine the actual content type returned (will be 'quote' if a fetch fails)
    content_type = 'quote' if isinstance(new_content, dict) and 'quote' in new_content else next_type
    
    # Log the result of the entire content cycle
    logging.info(f"DEBUG ROTATE: Attempted {next_type}. Result: {content_type}. Error: {err}")

    # 4. Success / Failure
    if new_content:
        # Success path
        _last.update({"content": new_content, "type": content_type, "ts": now})
        
        # Format output based on content type
        if content_type == 'quote':
            return {"quote": new_content["quote"], "author": new_content["author"], "type": "quote", "cached": False}
        
        # 💡 FINAL FIX: Ensure ALL image payloads (flickr, art) are correctly wrapped 💡
        elif content_type == 'flickr' or content_type == 'art':
            
            # The frontend expects {"content": {"image_url": "...", ...}, "type": "flickr"}
            
            return {
                "content": new_content, 
                "type": content_type, 
                "cached": False
            }
            
        else:
            # Fallback for weather or other future types
            return {"content": new_content, "type": content_type, "cached": False}
    
    # 5. Failure Path (This should be unreachable due to the explicit fallback return in the fetch functions)
    if err:
        return JSONResponse({"error": f"Content Fetch Failed: {err}"}, status_code=503)

    # Should be unreachable
    return JSONResponse({"error": "Content fetch failed unexpectedly."}, status_code=503)


@app.get("/api/theme")
def api_theme():
    return CFG.get("theme", {})

@app.get("/api/quote")
def redirect_old_quote_endpoint():
    # Redirects old client requests to the new content handler
    return RedirectResponse(url="/api/content")
