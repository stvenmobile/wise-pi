# CYD ESP32 2.8" (ILI9341) — Minimal Quote Display

A bare-bones ESP32 + 2.8" TFT (CYD) build that shows rotating quotes.  
No printed case required—the panel stands at a nice angle if you use a 90° USB-C power adapter.

---

## Hardware

- **Board:** ESP32 Dev Module (dual-core, 240 MHz)
- **Display:** CYD 2.8" TFT, **ILI9341** driver, **320×240** (rendered in landscape)
- **Backlight (BL):** PWM on **GPIO 21**
- **Ambient (LDR):** **GPIO 39** (ADC1_CH3)
- **Touch:** not used

> If your CYD variant is wired differently, adjust `include/User_Setup.h`.

---

## Project Layout (branch `cyd-esp32-2_8`)

cyd/
include/
secrets.example.h # template for Wi-Fi creds
User_Setup.h # TFT_eSPI overrides for this panel
src/
main.cpp # app (quotes, word-wrap, backlight control)
platformio.ini


- `include/secrets.h` is **gitignored** for safety.

---

## Quick Start (PlatformIO)

1. **Clone & switch**
   ```bash
   git clone <your-repo-url>
   cd wise-pi
   git switch cyd-esp32-2_8

    Secrets

    cp cyd/include/secrets.example.h cyd/include/secrets.h
    # edit secrets.h -> set WIFI_SSID / WIFI_PASSWORD

    Build & Upload

        Open the cyd project folder in VS Code (PlatformIO).

        Select environment: cyd (esp32dev, Arduino).

        Build → Upload → open Serial Monitor @ 115200.

    First boot

        You should see boot logs, Wi-Fi connect, HTTP 200 from zenquotes,
        then the quote on a black background (white text).

TFT_eSPI Setup Notes

We ship a working include/User_Setup.h for this CYD panel:

    Driver: ILI9341_DRIVER

    Rotation: set in code to tft.setRotation(1) (landscape)

    SPI speed: 27 MHz (stable)

    Pins: matched for this CYD variant (backlight on 21, etc.)

If your module differs, edit include/User_Setup.h and rebuild.
App Behavior

    Quotes via HTTPS from zenquotes.io.

    Word-wrap breaks only on whole words; quotes & author on separate blocks.

    Backlight auto-dim using LDR (GPIO 39) with smoothing:

        Tune in main.cpp: BL_MIN, BL_MAX, and mapping if desired.

    Refresh cadence: REFRESH_MS (default 60 s).

    On errors: the error is rendered instead of a quote.

Common Issues & Fixes

    Blank/dim screen

        Confirm BL pin (TFT_BL = 21) and PWM set up.

        Check User_Setup.h matches your display pins/driver.

    Wi-Fi never connects

        SSID is case sensitive. Verify in include/secrets.h.

    JSON/HTTP errors

        Check DNS/connectivity; the app logs HTTP status & fallback behavior.

    Touch warnings

        Harmless—touch is disabled unless you wire a controller.

Customize

    Theme: change BG_COLOR/FG_COLOR in main.cpp.

    Spacing/margins: adjust PAD, TXT_SIZE, lineH() padding.

    Day/Night idea: gate colors on time or LDR thresholds.

Safety

    Do not commit include/secrets.h.

    Only secrets.example.h is tracked.

License

MIT (unless stated otherwise in the repo). Credits to the library authors:

    TFT_eSPI (Bodmer)

    ArduinoJson

    ESP32 Arduino core