from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os, json
import time # Ensure time is imported for logging and sleeping
import requests
from pathlib import Path
import yaml

# --- Configuration and Initialization ---
ROOT = Path(__file__).parent
with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

# State Management (Updated)
# content can hold either {"quote": q, "author": a} or the weather data
_last = {"ts": 0, "content": None, "type": "quote"}
_quote_counter = 0 

@app.get("/")
def root():
    return FileResponse(str(ROOT / "static" / "index.html"))

# --- Core Fetch Functions ---

def fetch_quote():
    url = "https://zenquotes.io/api/random"
    max_retries = 3
    timeout_sec = 12

    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=timeout_sec)
            
            # --- LOGGING SUCCESS ---
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Quote Fetch SUCCESS (Attempt {attempt + 1}/{max_retries}) | Status Code: {r.status_code}")
            
            r.raise_for_status() 
            data = r.json()
            q = data[0]["q"]
            a = data[0]["a"]
            return q, a, None
            
        except requests.exceptions.HTTPError as e:
            # --- LOGGING HTTP FAILURE ---
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Quote Fetch FAILURE (Attempt {attempt + 1}/{max_retries}) | HTTP Status: {e.response.status_code}")
            
        except Exception as e:
            # --- LOGGING OTHER FAILURE (Timeout, Connection, JSON, etc.) ---
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Quote Fetch FAILURE (Attempt {attempt + 1}/{max_retries}) | Error: {type(e).__name__}: {str(e)}")

        if attempt == max_retries - 1:
            return None, None, f"Max retries exceeded. Last error: {type(e).__name__}"
        
        # Wait briefly before the next attempt
        time.sleep(0.5)
            
    return None, None, "Unexpected error in fetch_quote loop."


def fetch_weather():
    cfg_weather = CFG.get("weather", {})
    api_key = cfg_weather.get("api_key")
    lat = cfg_weather.get("lat")
    lon = cfg_weather.get("lon")
    
    if not (api_key and lat and lon):
        print("Weather configuration missing (API Key, Lat, or Lon). Check config.yaml.")
        return None, "Missing config"
        
    # OpenWeatherMap 5-day / 3-hour forecast API
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    
    try:
        r = requests.get(url, timeout=10)
        
        # --- LOGGING WEATHER FETCH ---
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Weather Fetch Status Code: {r.status_code}")
        
        r.raise_for_status()
        data = r.json()
        
        # Simplified data extraction for a 5-day view (taking one entry per day)
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
        
        return forecast, None
        
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Weather Fetch FAILURE: {type(e).__name__}: {str(e)}")
        return None, str(e)


# --- API Endpoint (Replaced /api/quote with /api/content) ---

@app.get("/api/content")
def api_content():
    global _quote_counter, _last
    now = time.time()
    ttl = int(CFG.get("refresh_seconds", 60))
    weather_cfg = CFG.get("weather", {})
    
    # --- 1. Check Cache and Weather Duration ---
    if _last["content"] and (now - _last["ts"] < ttl):
        
        if _last["type"] == "weather":
            duration = weather_cfg.get("display_duration_seconds", 20)
            # If weather is cached and still within its display time, return it
            if now - _last["ts"] < duration:
                return JSONResponse({"content": _last["content"], "type": "weather", "cached": True})
            # If weather time has expired, fall through to fetch new quote/check rotation
            
        else: # Content is a quote and is still valid
            return JSONResponse({"quote": _last["content"]["quote"], "author": _last["content"]["author"], "type": "quote", "cached": True})

    # --- 2. Rotation Check: Time to display weather? ---
    interval = weather_cfg.get("quote_interval", 5)
    
    # Check if we should try to display weather
    if _quote_counter % interval == 0:
        weather_data, err = fetch_weather()
        if weather_data:
            # Successfully fetched weather
            _last.update({"content": weather_data, "type": "weather", "ts": now})
            _quote_counter += 1
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ROTATION: Displaying Weather. Counter: {_quote_counter}")
            return {"content": weather_data, "type": "weather", "cached": False}
        # Fall-through to quote if weather fetch fails

    # --- 3. Fetch New Quote ---
    q, a, err = fetch_quote()
    if q:
        # Successfully fetched quote
        _last.update({"content": {"quote": q, "author": a}, "type": "quote", "ts": now})
        _quote_counter += 1
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ROTATION: Displaying Quote. Counter: {_quote_counter}")
        return {"quote": q, "author": a, "type": "quote", "cached": False}
        
    # --- 4. Fallback (Quote fetch failed) ---
    fallback = CFG.get("fallback_quotes", [])
    if fallback:
        now_int = int(now)
        item = fallback[now_int % len(fallback)]
        q, a = item["q"], item["a"]
        
        # Log that a fallback was used
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Fallback used: Quote fetch failed.")
        
        _last.update({"content": {"quote": q, "author": a}, "type": "quote", "ts": now})
        _quote_counter += 1
        return {"quote": q, "author": a, "type": "quote", "cached": False, "fallback": True}
        
    return JSONResponse({"error": "Content fetch failed, no fallback available."}, status_code=503)


@app.get("/api/theme")
def api_theme():
    theme = CFG.get("theme", {})
    return theme
