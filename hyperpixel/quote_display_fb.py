#!/usr/bin/env python3
import os, sys, time, json, math, glob
import urllib.request, urllib.error
from datetime import datetime

# ---- Config ----
SCREEN_W, SCREEN_H = 800, 480   # HyperPixel 4 (landscape)
MARGIN_X = 24                   # left/right margin in px
MARGIN_TOP = 24                 # top margin (we keep first line blank per your preference)
LINE_SPACING = 6                # extra px between lines
QUOTE_FONT_PT = 36              # main quote font
AUTHOR_FONT_PT = 30             # author font
REFRESH_SECONDS = 15 * 60       # fetch a new quote every 15 min

BG = (0, 0, 0)                  # black background
FG = (255, 255, 255)            # white text

PREFERRED_FONTS = [
    "DejaVuSans",
    "LiberationSans",
    "Arial",
    "FreeSans"
]

# Brightness: 0.0 .. 1.0
DEFAULT_DAY_BRIGHTNESS = 0.85
DEFAULT_NIGHT_BRIGHTNESS = 0.18
NIGHT_START = 21  # 21:00
NIGHT_END   = 7   # 07:00

# ---- Pygame (framebuffer) init ----
def init_pygame_headless():
    # Try modern KMSDRM first, then fbcon
    for drv in ["KMSDRM", "fbcon"]:
        os.environ["SDL_VIDEODRIVER"] = drv
        os.environ.setdefault("SDL_FBDEV", "/dev/fb0")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        try:
            import pygame
            pygame.display.init()
            screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), 0, 32)
            pygame.mouse.set_visible(False)
            print(f"[BOOT] SDL_VIDEODRIVER={drv}", flush=True)
            return pygame, screen
        except Exception as e:
            print(f"[BOOT] Driver {drv} failed: {e}", flush=True)
            try:
                import pygame
                pygame.display.quit()
            except Exception:
                pass
    print("[ERR] No suitable SDL video driver found.", flush=True)
    sys.exit(1)

# ---- Fonts ----
def load_fonts(pygame):
    # Try system font names
    for name in PREFERRED_FONTS:
        try:
            qf = pygame.font.SysFont(name, QUOTE_FONT_PT)
            af = pygame.font.SysFont(name, AUTHOR_FONT_PT)
            print(f"[BOOT] Using system font: {name}", flush=True)
            return qf, af
        except Exception:
            pass
    # Fallback to default
    qf = pygame.font.Font(None, QUOTE_FONT_PT)
    af = pygame.font.Font(None, AUTHOR_FONT_PT)
    print("[BOOT] Using default font", flush=True)
    return qf, af

# ---- Word wrap (no mid-word breaks) ----
def wrap_text(text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = w if not cur else cur + " " + w
        if font.size(trial)[0] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
                cur = w
            else:
                # Single very-long word: hard-break but do not exceed width
                # (rare for normal quotes)
                cut = w
                while font.size(cut)[0] > max_width and len(cut) > 1:
                    cut = cut[:-1]
                lines.append(cut)
                cur = w[len(cut):]
    if cur:
        lines.append(cur)
    return lines

# ---- Rendering ----
def render_quote(pygame, screen, q_font, a_font, quote, author):
    screen.fill(BG)
    max_w = SCREEN_W - 2 * MARGIN_X

    # Wrap quote
    q_lines = wrap_text(quote, q_font, max_w)

    # Build surfaces
    y = MARGIN_TOP  # leave first line blank at very top (per your preference)
    for line in q_lines:
        surf = q_font.render(line, True, FG)
        screen.blit(surf, (MARGIN_X, y))
        y += surf.get_height() + LINE_SPACING

    # Blank line then author (if provided)
    if author.strip():
        y += LINE_SPACING  # one "blank line" gap
        a_text = f"— {author.strip()}"
        a_surf = a_font.render(a_text, True, FG)
        screen.blit(a_surf, (MARGIN_X, y))

    pygame.display.flip()

# ---- Quotes ----
def fetch_quote():
    url = "https://zenquotes.io/api/random"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wise-pi-hyperpixel/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status != 200:
                print(f"[HTTP] status={resp.status}", flush=True)
                raise RuntimeError("bad HTTP")
            data = json.loads(resp.read().decode("utf-8", "ignore"))
            # Expected: [{"q":"...","a":"..."}]
            q = data[0].get("q", "").strip()
            a = data[0].get("a", "").strip()
            print("[HTTP] fetched zenquotes", flush=True)
            return q or "Stay curious.", a or "Unknown"
    except Exception as e:
        print(f"[HTTP] fetch failed: {e}", flush=True)
        # Fallback
        return ("Perseverance is not a long race; "
                "it is many short races one after the other." , "Walter Elliot")

# ---- Backlight control ----
class Backlight:
    def __init__(self):
        self.mode = None
        self.sys_path = None
        self.pwm = None

        # Try /sys/class/backlight first
        candidates = glob.glob("/sys/class/backlight/*")
        if candidates:
            self.mode = "sysfs"
            self.sys_path = candidates[0]
            print(f"[BL] sysfs at {self.sys_path}", flush=True)
            return

        # Fallback to GPIO19 PWM
        try:
            import RPi.GPIO as GPIO
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(19, GPIO.OUT)
            self.pwm = GPIO.PWM(19, 1000)  # 1kHz
            self.pwm.start(0)              # start off
            self.mode = "pwm19"
            print("[BL] PWM on GPIO19", flush=True)
        except Exception as e:
            print(f"[BL] No backlight control available: {e}", flush=True)
            self.mode = "none"

    def set(self, level):  # level: 0..1
        level = max(0.0, min(1.0, float(level)))
        if self.mode == "sysfs":
            try:
                with open(os.path.join(self.sys_path, "max_brightness"), "r") as f:
                    maxi = int(f.read().strip())
                val = max(1, min(maxi, int(round(level * maxi))))
                with open(os.path.join(self.sys_path, "brightness"), "w") as f:
                    f.write(str(val))
            except Exception as e:
                print(f"[BL] sysfs write failed: {e}", flush=True)
        elif self.mode == "pwm19" and self.pwm:
            duty = int(round(level * 100.0))  # 0..100
            try:
                self.pwm.ChangeDutyCycle(duty)
            except Exception as e:
                print(f"[BL] PWM write failed: {e}", flush=True)

    def cleanup(self):
        if self.mode == "pwm19" and self.pwm:
            try:
                self.pwm.stop()
                import RPi.GPIO as GPIO
                GPIO.cleanup(19)
            except Exception:
                pass

def day_night_brightness():
    h = datetime.now().hour
    if NIGHT_START <= h or h < NIGHT_END:
        return DEFAULT_NIGHT_BRIGHTNESS
    return DEFAULT_DAY_BRIGHTNESS

# ---- Main loop ----
def main():
    pygame, screen = init_pygame_headless()
    pygame.font.init()
    q_font, a_font = load_fonts(pygame)

    bl = Backlight()
    bl.set(day_night_brightness())

    print("[BOOT] Init complete; drawing first quote...", flush=True)

    last_fetch = 0
    quote, author = "", ""
    try:
        while True:
            now = time.time()
            if now - last_fetch > REFRESH_SECONDS or not quote:
                quote, author = fetch_quote()
                last_fetch = now
            render_quote(pygame, screen, q_font, a_font, quote, author)

            # Periodic backlight update (time-of-day)
            bl.set(day_night_brightness())

            # Idle
            for _ in range(60):  # ~1 second, also pump events
                for event in pygame.event.get():
                    if event.type == getattr(pygame, "QUIT", None):
                        raise SystemExit
                time.sleep(1/60.0)
    except KeyboardInterrupt:
        print("[EXIT] KeyboardInterrupt", flush=True)
    finally:
        bl.cleanup()
        try:
            pygame.display.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
