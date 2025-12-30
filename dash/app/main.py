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
from dotenv import load_dotenv 

# --- Configuration and Initialization ---
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

# Configure logging
try:
    logging.basicConfig(
        filename=ROOT / "wisepi.log", 
        filemode='a', 
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True 
    )
    logging.info("LOGGER STARTED SUCCESSFULLY.")
except Exception as e:
    print(f"CRITICAL ERROR: Logger failed to start. {e}")

# State Management
_last = {"ts": 0, "content": None, "type": "quote"}

# Load configuration
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

ROTATION_CFG = CFG.get("rotation", {})
ROTATION_SEQUENCE = ROTATION_CFG.get("sequence", ["weather", "quote"])
DURATIONS = ROTATION_CFG.get("durations_seconds", {})

# --- Core Fetch Functions ---

def fetch_weather() -> Tuple[Union[List[Dict], Dict], Union[str, None]]:
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
            
            if 'list' not in data:
                logging.error(f"DEBUG FETCH: Weather missing 'list' key. Keys found: {list(data.keys())}")
                return None, "API response malformed (missing 'list')"
            
            forecast = []
            seen_days = set()
            
            try:
                current_main = data['list'][0]['main']
                current_weather_data = {
                    "pressure": current_main.get('pressure'),
                    "humidity": current_main.get('humidity')
                }
            except (IndexError, KeyError) as e:
                logging.error(f"DEBUG FETCH: Could not parse current weather: {e}")
                current_weather_data = {"pressure": 0, "humidity": 0}

            for item in data['list']:
                 day_ts = item['dt_txt'].split(' ')[0]
                 if day_ts not in seen_days and len(forecast) < 6: 
                    forecast.append({
                        "day": day_ts,
                        "temp": item['main']['temp'],
                        "desc": item['weather'][0]['description'],
                        "icon": item['weather'][0]['icon']
                    })
                    seen_days.add(day_ts)
            
            if not forecast:
                logging.error(f"DEBUG FETCH: Weather SUCCESS but forecast list is EMPTY. Raw items: {len(data.get('list', []))}")
                raise ValueError("Filtered forecast is empty")

            logging.info(f"DEBUG FETCH: Weather SUCCESS. {len(forecast)} days parsed.")
            return {"forecast": forecast, "current": current_weather_data}, None
            
        except Exception as e:
            error_msg = f"Weather API attempt {attempt + 1} failed: {type(e).__name__}: {str(e)}"
            logging.error(error_msg)
            if attempt < max_retries - 1:
                 time.sleep(retry_delay_sec)
                 continue 
            return None, f"Weather API failed after {max_retries} attempts: {str(e)}"
    return None, "Unexpected weather API failure."



def fetch_zenquotes() -> Tuple[Dict[str, str], Union[str, None]]:
    url = "https://zenquotes.io/api/random"
    max_retries = 2
    timeout_sec = 12

    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=timeout_sec)
            r.raise_for_status() 
            data = r.json()
            if not data or not data[0].get('q'):
                return None, "ZenQuotes API returned empty or malformed data."
            logging.info(f"DEBUG FETCH: ZenQuotes SUCCESS (Status {r.status_code}).")
            return {"quote": data[0]["q"], "author": data[0]["a"]}, None
        except Exception as e:
            error_msg = f"ZenQuotes API attempt {attempt + 1} failed: {type(e).__name__}"
            logging.warning(error_msg)
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            return None, f"ZenQuotes API failed: {type(e).__name__}: {str(e)}"
    return None, "Unexpected ZenQuotes API failure."


def fetch_ninjaquotes() -> Tuple[Dict[str, str], Union[str, None]]:
    cfg_ninja = CFG.get("ninjaquotes", {})
    api_key = os.environ.get(cfg_ninja.get("api_key_env_var")) 
    topics = cfg_ninja.get("topics", [])
    
    if not api_key:
        return None, "Missing Ninja API Key (ENV)."
    if not topics:
        return None, "Missing Topics in config."

    topic = random.choice(topics)
    encoded_topic = quote_plus(topic)
    
    # UPDATED: Use /v2/randomquotes
    # CRITICAL: Parameter is now 'categories' (plural), not 'category'
    # REMOVED: limit=10 (Premium only feature, defaults to 1 on free tier)
    url = f"https://api.api-ninjas.com/v2/randomquotes?categories={encoded_topic}"
    headers = {'X-Api-Key': api_key}    
    max_retries = 2
    timeout_sec = 12

    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout_sec)
            r.raise_for_status() 
            data = r.json()
            
            # CHECK: Ensure we got a list and it is not empty
            if not data or not isinstance(data, list) or len(data) == 0:
                 # If specific topic fails, you might want to log it and retry 
                 # or fall back to no topic, but raising error is fine for now.
                 raise ValueError(f"Ninja API returned empty data for: {topic}")
            
            # Since limit is likely 1, we just take the first item.
            # The API has already done the "randomizing" for us.
            selected_quote = data[0]

            logging.info(f"DEBUG FETCH: Ninja Random Success | Topic: {topic} | Quote: {selected_quote.get('quote')[:30]}...")
            return {
                "quote": selected_quote.get("quote"), 
                "author": selected_quote.get("author", "Unknown")
            }, None
            
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(f"Ninja attempt {attempt+1} failed. Retrying...")
                time.sleep(0.5)
                continue
            error_msg = f"Ninja API failed after {max_retries} attempts: {str(e)}"
            logging.error(error_msg)
            return None, error_msg
            
    return None, "Unexpected failure after maximum retries."


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
    if content_type == 'weather': return fetch_weather
    if content_type == 'ninjaquotes': return fetch_ninjaquotes
    if content_type == 'zenquotes': return fetch_zenquotes
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
        ttl_ms = int((current_duration - (now - _last["ts"])) * 1000)
        return JSONResponse({"content": _last["content"], "type": current_type, "ttl": max(1000, ttl_ms), "cached": True})

    # 2. Determine the NEXT content type and Fetch
    start_type = get_next_type(current_type)
    tried_types = set()
    next_type = start_type
    new_content = None
    err = None 
    
    while new_content is None and next_type not in tried_types:
        fetch_func = get_fetch_function(next_type)
        if not fetch_func:
            tried_types.add(next_type)
            next_type = get_next_type(next_type)
            continue
        new_content, err = fetch_func() 
        if new_content is None:
            logging.error(f"FAILOVER: Fetch failed for {next_type}. Error: {err}")
            tried_types.add(next_type)
            next_type = get_next_type(next_type)
        if new_content:
            break
            
    if new_content is None:
        logging.critical("FAILOVER: All sources failed. Displaying permanent failure message.")
        return JSONResponse({"error": "All content sources failed to load."}, status_code=503)

    content_type = next_type
    
    log_msg = f"DEBUG ROTATE: Selected {next_type}. Result: {content_type}."
    if err:
        log_msg += f" Error: {err}"
        logging.warning(log_msg)
    else:
        logging.info(log_msg)

    # 4. Success Path
    _last.update({"content": new_content, "type": next_type, "ts": now})
    
    # Calculate TTL
    next_duration_sec = DURATIONS.get(content_type, 60)
    ttl_ms = next_duration_sec * 1000

    # Build Response
    response_payload = {
        "type": content_type,
        "ttl": ttl_ms,
        "cached": False
    }

    if content_type in ['zenquotes', 'ninjaquotes', 'quote']:
        response_payload.update({
            "quote": new_content["quote"], 
            "author": new_content["author"],
            "type": content_type
        })
    elif content_type == 'weather':
        response_payload["content"] = new_content
        response_payload["type"] = content_type

    return response_payload


@app.get("/api/theme")
def api_theme():
    return CFG.get("theme", {})

@app.get("/api/quote")
def redirect_old_quote_endpoint():
    return RedirectResponse(url="/api/content")
