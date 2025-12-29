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
from urllib.parse import quote_plus

# Local imports
from . import flickr 

# --- Configuration and Initialization ---

# 1. Define ROOT first so we can use it for the log file path
ROOT = Path(__file__).parent
LOG_FILE = ROOT / "wisepi.log"  # CHANGED: Log filename

# 2. Configure Logging (File + Console)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'), # Writes to wisepi.log
        logging.StreamHandler()                          # Writes to console
    ]
)

# State Management (Tracks current type and last update time)
_last = {"ts": 0, "content": None, "type": "quote"}

# Load configuration once at startup
try:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        CFG = yaml.safe_load(f)
except FileNotFoundError:
    CFG = {}
    logging.error("STARTUP ERROR: config.yaml not found.")
except yaml.YAMLError as e:
    CFG = {}
    logging.error(f"STARTUP ERROR: config.yaml parse error: {e}")


app = FastAPI()
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

# Define the sequence and durations from config (or use defaults if config failed)
ROTATION_CFG = CFG.get("rotation", {})
ROTATION_SEQUENCE = ROTATION_CFG.get("sequence", ["weather", "quote", "art"])
DURATIONS = ROTATION_CFG.get("durations_seconds", {})




# --- Core Fetch Functions ---


def fetch_weather() -> Tuple[Union[List[Dict], Dict], Union[str, None]]:
    """Fetches a 5-day/3-hour forecast from OpenWeatherMap."""
    cfg_weather = CFG.get("weather", {})
    api_key = os.environ.get("OPENWEATHER_API_KEY") 
    lat = cfg_weather.get("lat")
    lon = cfg_weather.get("lon")

    if not (api_key and lat and lon):
        return None, "Missing API Key (ENV) or Geo Config (YAML)"

    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
    
    max_retries = 2
    retry_delay_sec = 1 
    
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status() 
            data = r.json()
            
            # Data extraction logic: Filter 3-hour data to get 5 distinct days (6 items total)
            forecast = []
            seen_days = set()
            # --- CRITICAL: Extract Pressure and Humidity from the first item (today) ---
            # The first item (data['list'][0]) is the current weather forecast
            current_main = data['list'][0]['main']
            current_weather_data = {
                "pressure": current_main.get('pressure'),
                "humidity": current_main.get('humidity')
            }

            for item in data['list']:
                 day_ts = item['dt_txt'].split(' ')[0]
                 if day_ts not in seen_days and len(forecast) < 6: # < 6 limits it to 5 full days
                    forecast.append({
                        "day": day_ts,
                        "temp": item['main']['temp'],
                        "desc": item['weather'][0]['description'],
                        "icon": item['weather'][0]['icon']
                    })
                    seen_days.add(day_ts)
            
            logging.info(f"DEBUG FETCH: Weather SUCCESS (Status {r.status_code}).")
            return {"forecast": forecast, "current": current_weather_data}, None
            
        except Exception as e:
            error_msg = f"Weather API attempt {attempt + 1} failed: {type(e).__name__}"
            logging.error(error_msg)
            
            if attempt < max_retries - 1:
                 time.sleep(retry_delay_sec)
                 continue 
            
            return None, f"Weather API failed after {max_retries} attempts: {str(e)}"
    return None, "Unexpected weather API failure."



def fetch_weather_and_quote() -> Tuple[Dict[str, Any], Union[str, None]]:
    """Fetches weather and quote data simultaneously for the dual display."""
    
    # Attempt to fetch both necessary pieces of data
    weather_content, weather_err = fetch_weather() # This is the 5-day forecast data
    quote_content, quote_err = fetch_zenquotes()   # This is the quote data
    
    if not weather_content:
        # If weather fails, log it and return failure, letting the rotation move on.
        logging.error(f"DUAL-FETCH: Weather failed. Error: {weather_err}")
        return None, "Weather component failed in dual fetch."
    
    # Even if quote fails, we proceed with the weather data, using a placeholder.
    if not quote_content:
        # NOTE: This placeholder is simple data, not a formatted quote payload
        quote_content = {"quote": "Quote fetch failed.", "author": "ZenQuotes API"}
        logging.warning("DUAL-FETCH: Quote failed, substituting placeholder.")

    # Package data under a single 'content' key for the frontend
    dual_payload = {
        "weather": weather_content,
        "quote": quote_content
    }
    
    return dual_payload, None

# --- Inside app/main.py, update get_fetch_function ---
def get_fetch_function(content_type: str) -> Union[callable, None]:
    if content_type == 'weather':
        return fetch_weather_and_quote # <--- NEW DUAL-FETCH FUNCTION
    # ... (rest of the map remains the same) ...





def fetch_zenquotes() -> Tuple[Dict[str, str], Union[str, None]]:
    """Fetches a random quote from ZenQuotes.io."""
    
    # ZenQuotes requires no API key or specific configuration
    url = "https://zenquotes.io/api/random"
    max_retries = 2
    timeout_sec = 12

    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=timeout_sec)
            r.raise_for_status() 
            data = r.json()
            
            # ZenQuotes returns a list containing one quote dictionary
            if not data or not data[0].get('q'):
                return None, "ZenQuotes API returned empty or malformed data."
            
            logging.info(f"DEBUG FETCH: ZenQuotes SUCCESS (Status {r.status_code}).")
            
            # Return content and no error
            return {"quote": data[0]["q"], "author": data[0]["a"]}, None
            
        except Exception as e:
            error_msg = f"ZenQuotes API attempt {attempt + 1} failed: {type(e).__name__}"
            logging.warning(error_msg)
            
            if attempt < max_retries - 1:
                # Sleep briefly and then continue to the next attempt
                time.sleep(0.5)
                continue
            
            # If max retries hit, return the failure without displaying a quote
            logging.error(f"ZenQuotes API failed after {max_retries} attempts.")
            return None, f"ZenQuotes API failed: {type(e).__name__}: {str(e)}"
            
    return None, "Unexpected ZenQuotes API failure."




def fetch_ninjaquotes() -> Tuple[Dict[str, str], Union[str, None]]:
    """Fetches a random quote from API Ninjas, selected from configured topics."""
    
    cfg_ninja = CFG.get("ninjaquotes", {})
    # Retrieve API key from environment
    api_key = os.environ.get(cfg_ninja.get("api_key_env_var")) 
    topics = cfg_ninja.get("topics", [])
    
    if not api_key:
        logging.error("DEBUG FETCH: Ninja Quote FAILED. API Key not found in environment.")
        return None, "Missing Ninja API Key (ENV)."
    
    if not topics:
        logging.error("DEBUG FETCH: Ninja Quote FAILED. Topics list is empty in config.")
        return None, "Missing Topics in config."

    # 1. Select a random topic to keep queries varied
    topic = random.choice(topics)
    encoded_topic = quote_plus(topic)

    url = f"https://api.api-ninjas.com/v2/quotes?category={encoded_topic}" 
    headers = {'X-Api-Key': api_key}    
    
    max_retries = 2
    timeout_sec = 12
    status_code = None

    for attempt in range(max_retries):
        try:
            # CRITICAL: Use the custom header for authentication
            r = requests.get(url, headers=headers, timeout=timeout_sec)
            r.raise_for_status() # Raises an HTTPError for 4xx/5xx responses
            data = r.json()
            
            # API Ninjas returns a list of quotes; take the first one
            if not data or not data[0].get('quote'):
                 return None, f"Ninja API returned no quote for category: {topic}"
                 
            logging.info(f"DEBUG FETCH: Ninja Quote SUCCESS for topic: {topic}.")
            return {"quote": data[0]["quote"], "author": data[0]["author"]}, None
        
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            
            if attempt == max_retries - 1:
                logging.warning(f"DEBUG FETCH: Ninja Quote FAILED (HTTP {status_code}). Falling back.")
                return None, f"Max retries exceeded. Last error: HTTP {status_code}"
            
            logging.warning(f"Ninja API attempt {attempt+1} failed with status: {status_code}")
            time.sleep(0.5)

        except Exception as e:
            # Catch all other exceptions (network, JSON parsing)
            error_msg = f"Non-HTTP Error: {type(e).__name__}: {str(e)}"
            if attempt == max_retries - 1:
                logging.error(f"DEBUG FETCH: Ninja Quote FAILED. Last error: {error_msg}")
                return None, f"Max retries exceeded. Last error: {type(e).__name__}"
            time.sleep(0.5)
            
    return None, "Unexpected failure after maximum retries."


def fetch_art() -> Tuple[Union[Dict, None], Union[str, None]]:
    MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
    MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
    
    try:
        search_params = {
            'q': 'painting OR drawing OR sketch', 
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
        
    except Exception as e:
        return None, f"Met Art Search failed: {type(e).__name__}"

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

    return None, "Could not find a suitable landscape or square image in sample."


def fetch_smithsonian() -> Tuple[Union[Dict, None], Union[str, None]]:
    cfg_smithsonian = CFG.get("smithsonian", {})
    api_key = os.environ.get(cfg_smithsonian.get("api_key_env_var"))

    if not api_key:
        return None, "Missing Smithsonian API Key (ENV)."

    # The specific topics you want to cycle through
    topics = [
        'topic:Impressionism',
        'topic:"Painting, Japanese"',
        'topic:"Painting, French"'
    ]
    
    query_topic = topics[0] 

    try:
        query_topic = random.choice(topics)
    except IndexError:
        query_topic = 'topic:"Painting, Japanese"'
        
    # Base parameters including the specific topic and random sort
    params = {
        'q': query_topic, 
        'rows': 50,
        'sort': 'random',
        'api_key': api_key,
        'fsq': 'online_media_type:Images AND access:CC0',
        'fso': 'media_usage',
    }

    url = "https://api.si.edu/openaccess/api/v1.0/search"
    
    try:
        # DEBUG STEP: Construct the full URL for logging
        req = requests.Request('GET', url, params=params)
        prepared_req = req.prepare()
        logging.info(f"DEBUG SMITHSONIAN URL: {prepared_req.url}") 
        
        r = requests.get(prepared_req.url, timeout=10) 
        r.raise_for_status()
        data = r.json()
        
        # Check for results and sample the first item (since it's randomly sorted)
        hits = data.get('response', {}).get('rows', [])
        
        if not hits:
            return None, f"Smithsonian search found no results for query: {query_topic}"

        # Select the first item, as the API has already randomly sorted the 50 results
        item = hits[0] 
        
        # Extract the primary image URL and metadata
        image_url = item.get('content', {}).get('online_media', {}).get('media', [{}])[0].get('url')
        
        if not image_url:
             return None, "Smithsonian item lacks a public image URL."

        smithsonian_payload = {
            "image_url": image_url,
            "title": item.get('title', 'Untitled'),
            "artist": item.get('content', {}).get('freetext', {}).get('name', ['Unknown Artist'])[0],
            "date": item.get('date', 'Unknown Date')
        }
        
        logging.info(f"DEBUG FETCH: Smithsonian SUCCESS for topic: {query_topic}")
        return smithsonian_payload, None

    except Exception as e:
        error_msg = f"Smithsonian API failed: {type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        return None, error_msg


def fetch_harvard() -> Tuple[Union[Dict, None], Union[str, None]]:
    """Fetches Harvard Art. Allows 1 retry before failing over."""
    cfg_harvard = CFG.get("harvard", {})
    api_key = os.environ.get(cfg_harvard.get("api_key_env_var"))

    if not api_key:
        return None, "Missing Harvard API Key (ENV)."

    filters = [
        "classification:Paintings&period=Edo+Period", 
        "classification:Drawings&period=Meiji+Period",
        "period=Impressionism",
        "style=Post-Impressionism"
    ]
    filter_set = random.choice(filters)
    url = "https://api.harvardartmuseums.org/object"

    max_retries = 2
    
    for attempt in range(max_retries):
        try:
            # 1. Get total count
            params = {
                'apikey': api_key,
                'hasimage': 1,
                'q': filter_set,
                'size': 1                  
            }
            
            r_count = requests.get(url, params=params, timeout=10)
            r_count.raise_for_status()
            
            total_records = r_count.json().get('info', {}).get('totalrecords', 0)
            
            if total_records == 0:
                return None, f"Harvard search found no records for filter: {filter_set}"

            # 2. Fetch random item
            random_offset = random.randint(1, total_records - 1) if total_records > 1 else 0
            params['page'] = random_offset
            params['size'] = 1 

            r_final = requests.get(url, params=params, timeout=10)
            r_final.raise_for_status()
            item = r_final.json().get('records', [{}])[0]
            
            # --- CRITICAL FIX START ---
            image_url = item.get('primaryimageurl')
            if not image_url:
                # If the API promised an image but didn't give one, treat as failure
                raise ValueError("Item returned no primaryimageurl")
            
            harvard_payload = {
                "image_url": image_url,
                "title": item.get('title', 'Untitled'),
                "artist": item.get('people', [{}])[0].get('displayname', 'Unknown Artist'),
                "date": item.get('dated', 'Unknown Date')
            }
            # --- CRITICAL FIX END ---
            
            logging.info(f"DEBUG FETCH: Harvard SUCCESS for filter: {filter_set}")
            return harvard_payload, None 

        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(f"Harvard attempt {attempt+1} failed. Retrying...")
                time.sleep(1)
                continue
            
            error_msg = f"Harvard API failed after {max_retries} attempts: {type(e).__name__}"
            logging.error(error_msg)
            return None, error_msg
            
    return None, "Unexpected Harvard API failure."




def fetch_flickr() -> Tuple[Union[Dict, None], Union[str, None]]:
    """Fetches a random photo from Flickr and conforms to the (content, error) tuple."""
    
    flickr_config = CFG.get('flickr') 
    
    if not flickr_config:
        return None, "Flickr section missing from config.yaml."
        
    photo_data = flickr.get_random_public_photo(flickr_config)

    # --- CRITICAL FIX START ---
    if not photo_data or not photo_data.get("url"):
        error_msg = "Failed to fetch photo from Flickr (Empty Data or Missing URL)."
        logging.error(f"DEBUG FETCH: Flickr FAILED: {error_msg}")
        return None, error_msg 
    # --- CRITICAL FIX END ---

    logging.info(f"DEBUG FETCH: Flickr SUCCESS.")
    
    return {
        "image_url": photo_data.get("url"), 
        "title": photo_data.get("title", ""),
        "artist": photo_data.get("artist", ""),
        "date": "" 
    }, None


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
        return fetch_weather_and_quote
    if content_type == 'ninjaquotes':
        return fetch_ninjaquotes
    if content_type == 'art':
        return fetch_art
    if content_type == 'flickr':
        return fetch_flickr
    if content_type == 'harvard':
        return fetch_harvard
    if content_type == 'smithsonian':
        return fetch_smithsonian
    if content_type == 'zenquotes':
        return fetch_zenquotes
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
    start_type = get_next_type(current_type)
    
    # --- FAILOVER LOOP: Attempt to find valid content ---
    tried_types = set()
    next_type = start_type
    
    new_content = None
    
    while new_content is None and next_type not in tried_types:
        fetch_func = get_fetch_function(next_type)
        if not fetch_func:
            tried_types.add(next_type)
            next_type = get_next_type(next_type)
            continue
            
        # Attempt to fetch content
        new_content, err = fetch_func() 
        
        # Log failure and continue loop if necessary
        if new_content is None:
            logging.error(f"FAILOVER: Fetch failed for {next_type}. Error: {err}")
            tried_types.add(next_type)
            next_type = get_next_type(next_type)
        
        # If fetch succeeded, break the loop
        if new_content:
            break
            
    # --- 3. Final Result Handling ---
    
    if new_content is None:
        # CRITICAL: If the loop finishes and nothing worked, display failure to user.
        logging.critical("FAILOVER: All sources failed. Displaying permanent failure message.")
        return JSONResponse({"error": "All content sources failed to load."}, status_code=503)

    # Determine the actual content type returned (now ONLY the fetch type)
    content_type = next_type
    
    # Log the result of the entire content cycle (Clean Log Logic)
    if err:
        logging.info(f"DEBUG ROTATE: Selected {next_type}. Result: {content_type}. Error: {err}")
    else:
        logging.info(f"DEBUG ROTATE: Selected {next_type}. Result: {content_type}.")

    # 4. Success Path (Guaranteed to succeed past this point)
    _last.update({"content": new_content, "type": next_type, "ts": now})
    
    # Format output based on content type
    if content_type in ['zenquotes', 'ninjaquotes']:
        return {"quote": new_content["quote"], "author": new_content["author"], "type": "quote", "cached": False}
    
    # FINAL FIX: Ensure ALL image payloads (flickr, art, smithsonian, harvard) are correctly wrapped 
    elif content_type in ['flickr', 'art', 'harvard', 'smithsonian']:
        return {
            "content": new_content, 
            "type": content_type, 
            "cached": False
        }
        
    elif content_type == 'weather':
        # Weather returns pure HTML content in the 'new_content' variable
        return {
            "content": new_content, 
            "type": content_type, 
            "cached": False
        }
        
    else:
        # Should be unreachable
        return JSONResponse({"error": "Content fetch failed unexpectedly."}, status_code=503)


@app.get("/api/theme")
def api_theme():
    return CFG.get("theme", {})

@app.get("/api/quote")
def redirect_old_quote_endpoint():
    return RedirectResponse(url="/api/content")
