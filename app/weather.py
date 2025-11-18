from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import RedirectResponse
import os
import time
import requests
from pathlib import Path
import yaml

# --- Configuration and Initialization ---
ROOT = Path(__file__).parent
try:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        CFG = yaml.safe_load(f)
except FileNotFoundError:
    CFG = {}
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: config.yaml not found.")

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

@app.get("/")
def root():
    return FileResponse(str(ROOT / "static" / "index.htm")) 

# --- Dedicated Weather Fetch Function with Retries ---

def fetch_weather():
    cfg_weather = CFG.get("weather", {})
    
    api_key = os.environ.get("OPENWEATHER_API_KEY") 
    lat = cfg_weather.get("lat")
    lon = cfg_weather.get("lon")

    if not (api_key and lat and lon):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WARNING: Weather configuration incomplete (API Key or Geo missing).")
        return None, "Missing API Key (ENV) or Geo Config (YAML)"

    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
    
    # --- RETRY LOGIC ADDED HERE ---
    max_retries = 3
    retry_delay_sec = 1 
    
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=10)
            
            # Log the status code (essential for success/failure)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] INFO: OpenWeatherMap fetch status: {r.status_code} (Attempt {attempt + 1}/{max_retries})")
            
            r.raise_for_status() 
            data = r.json()
            
            # Data extraction logic (Success)
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
            
            return forecast, None # Success! Exit function.
            
        except requests.exceptions.HTTPError as e:
            # If it's a permanent HTTP error (e.g., 401 Unauthorized), don't retry.
            error_msg = f"HTTP Error {e.response.status_code}"
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: OpenWeatherMap HTTP Failure: {error_msg}. Not retrying.")
            return None, error_msg
            
        except Exception as e:
            # Catch transient errors like NameResolutionError (DNS) or ConnectionError
            error_msg = f"{type(e).__name__}: {str(e)}"
            
            if attempt < max_retries - 1:
                 print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WARNING: Transient failure detected. Retrying in {retry_delay_sec}s. Error: {type(e).__name__}")
                 time.sleep(retry_delay_sec)
                 continue # Go to the next attempt

            # If it's the final attempt, log the final error
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: OpenWeatherMap General Failure: {error_msg}. Max retries exceeded.")
            return None, error_msg

    return None, "Unknown failure after maximum retries."


# --- API Endpoint Handlers ---

@app.get("/api/weather")
def api_weather():
    forecast, err = fetch_weather()
    
    if forecast:
        return {"content": forecast, "type": "weather", "cached": False}
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WARNING: API /weather failed to fetch. Returning 503.")
        return JSONResponse({"error": f"Weather fetch failed: {err}"}, status_code=503)

@app.get("/api/theme")
def api_theme():
    return CFG.get("theme", {})

@app.get("/api/quote")
def redirect_old_quote_endpoint():
    return RedirectResponse(url="/api/weather")
