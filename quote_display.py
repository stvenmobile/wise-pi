#!/usr/bin/env python3

import os
import sys
import time
import logging
import requests
from PIL import Image, ImageDraw, ImageFont

# ----- Logging Setup -----
log_file = os.path.expanduser("~/wise-pi/quote_display.log")
logging.basicConfig(
    filename=log_file,
    filemode='a',
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# ----- GPIO Setup Before Import -----
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
except Exception as e:
    logging.warning(f"GPIO setup warning: {e}")

# ----- Waveshare EPD Path -----
sys.path.append('/home/steve/e-Paper/RaspberryPi_JetsonNano/python/lib')
from waveshare_epd import epd2in7

# ----- Text Wrapping -----
def wrap_text(text, font, max_width):
    lines = []
    words = text.split()
    line = ""
    for word in words:
        test_line = f"{line} {word}".strip()
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            line = test_line
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

# ----- Quote Fetching -----
def fetch_quote():
    try:
        r = requests.get("https://zenquotes.io/api/random", timeout=10)
        r.raise_for_status()
        data = r.json()[0]
        return data['q'], data['a']
    except Exception as e:
        logging.error(f"Failed to fetch quote: {e}")
        return "Error fetching quote", ""

# ----- Display Function -----
def display_quote(quote, author, epd):
    image = Image.new('1', (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)

    font_options = [(18, 16), (16, 14)]  # Quote font, Author font
    max_width = epd.height - 20
    canvas_height = epd.width

    for quote_size, author_size in font_options:
        font_quote = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', quote_size)
        font_author = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', author_size)

        wrapped_quote = wrap_text(quote, font_quote, max_width)
        wrapped_author = wrap_text(f"— {author}", font_author, max_width)

        total_height = 0
        spacing = 2

        for line in wrapped_quote:
            bbox = font_quote.getbbox(line)
            total_height += (bbox[3] - bbox[1]) + spacing

        total_height += font_quote.getbbox("A")[3] - font_quote.getbbox("A")[1]  # blank line

        for line in wrapped_author:
            bbox = font_author.getbbox(line)
            total_height += (bbox[3] - bbox[1]) + spacing

        if total_height <= canvas_height:
            break
    else:
        logging.warning("Quote too long even after font fallback.")
        return

    y = (canvas_height - total_height) // 2

    for line in wrapped_quote:
        draw.text((10, y), line, font=font_quote, fill=0)
        bbox = font_quote.getbbox(line)
        y += (bbox[3] - bbox[1]) + spacing

    y += font_quote.getbbox("A")[3] - font_quote.getbbox("A")[1]  # space between quote and author

    for line in wrapped_author:
        draw.text((10, y), line, font=font_author, fill=0)
        bbox = font_author.getbbox(line)
        y += (bbox[3] - bbox[1]) + spacing

    epd.display(epd.getbuffer(image.rotate(180)))


# ----- Main Loop -----
if __name__ == "__main__":
    logging.info("Quote display script started.")

    try:
        epd = epd2in7.EPD()
        epd.init()
        epd.Clear(0xFF)
    except Exception as e:
        logging.error(f"Failed to initialize e-paper display: {e}")
        sys.exit(1)

    while True:
        try:
            quote, author = fetch_quote()
            logging.info(f'Displaying new quote:\n"{quote}" — {author}')
            display_quote(quote, author, epd)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
        time.sleep(600)  #delay 10 minutes per quote
