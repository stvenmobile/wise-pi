#!/bin/bash

# 1. Rotate the screen immediately
# (Using || true prevents the script from crashing if the display isn't ready yet)
wlr-randr --output DSI-1 --transform 180 || true

# 2. Short wait to ensure network is up and rotation is applied
sleep 15

# 3. Find the browser executable
BROWSER=$(command -v chromium || command -v chromium-browser)

# 4. Launch in Kiosk Mode
# Added '--incognito' to prevent "Restore pages?" popups and double-fetching on reboot.
$BROWSER --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --kiosk \
  --incognito \
  http://localhost:8000
