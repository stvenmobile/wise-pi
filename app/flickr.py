import os
import random
import requests
import logging

from urllib.parse import urlencode

# Base URL for the Flickr API
FLICKR_API_BASE = "https://api.flickr.com/services/rest/"
# The default format for the photo URL after fetching details
PHOTO_URL_TEMPLATE = "https://farm{farm_id}.staticflickr.com/{server_id}/{id}_{secret}_b.jpg"

def get_random_public_photo(config: dict):
    """Fetches a random public photo from the specified user/tags."""
    
    # 1. Get API Key from environment (must be set in .env file and loaded by systemd)
    api_key = os.getenv(config.get('api_key_env_var', 'FLICKR_API_KEY'))
    user_id = config.get('user_id')
    tags = config.get('tags')
    
    if not api_key:
        logging.error("Flickr API Key is missing from environment.")
        return None

    # --- Step A: Get Total Count and Pages (Find Random Page) ---
    # We use photos.search to query public photos and determine total pages.
    params = {
        'method': 'flickr.photos.search',
        'api_key': api_key,
        'user_id': user_id,
        'tags': tags,
        'safe_search': 1,      # Safe search enabled
        'content_type': 1,     # Photos only
        'per_page': 50,        # Fetch 50 photos per page
        'format': 'json',
        'nojsoncallback': 1,
    }

    try:
        response = requests.get(FLICKR_API_BASE, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data['stat'] != 'ok':
            logging.error(f"Flickr API Status Error: {data.get('message', 'Unknown error')}")
            return None
            
        photos_page = data['photos']
        total_pages = int(photos_page['pages'])

        if total_pages == 0:
            logging.warning("Flickr search found no photos matching criteria.")
            return None

        # Choose a random page to introduce randomness across the entire library
        random_page = random.randint(1, total_pages)

    except Exception as e:
        logging.error(f"Flickr API failed in Step A (Count): {e}")
        return None

    # --- Step B: Fetch Photos from the Random Page ---
    params['page'] = random_page

    try:
        response = requests.get(FLICKR_API_BASE, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Select a random photo from the 50 photos on the chosen page
        photos = data['photos']['photo']
        if not photos:
            return None

        photo = random.choice(photos)
        
        # 3. Construct the final high-resolution URL (using the '_b' suffix for large size)
        photo_url = PHOTO_URL_TEMPLATE.format(
            farm_id=photo['farm'], 
            server_id=photo['server'], 
            id=photo['id'], 
            secret=photo['secret']
        )

        # 💡 ADD THIS DEBUG LINE 💡
        logging.info(f"DEBUG FLICKR URL: {photo_url}")
        
        return {
            "url": photo_url
        }

    except Exception as e:
        logging.error(f"Flickr API failed in Step B (Fetch): {e}")
        return None
