Wise-Pi Dash (7" DSI) — Setup Guide

A lightweight FastAPI web app that shows a large, readable quote on a Raspberry Pi with a 7" DSI display, running in Chromium kiosk mode at boot. Designed to be simple now (quotes), but flexible for future tiles (weather, headlines, calendar, etc.).

What you’ll need

Raspberry Pi 4 (recommended; Zero 2 W will work but is slower)

7" DSI display (official or similar no-name; no touch required)

Raspberry Pi OS (Bookworm) with Desktop (32-bit is fine)

Network access (Wi-Fi or Ethernet)

Repo layout (branch pi-dash-7in):

dash/
  app/
    main.py
    requirements.txt
    config.yaml
    env.example
    static/
      index.html
      styles.css
  systemd/
    wise-dash.service       # service for the API
    wise-kiosk.service      # (optional) user-service variant
  stl/
    bracket_stand_v1.stl    # simple desk brackets (optional)

1) OS prep

Boot the Pi, connect to network.

Update OS:

sudo apt update && sudo apt full-upgrade -y
sudo reboot


Install system packages:

sudo apt install -y git python3-venv chromium-browser curl
# Some images use `chromium` instead of `chromium-browser`; we handle both later.


Tip: If you plan to hide the mouse pointer in kiosk, also:

sudo apt install -y unclutter

2) Get the code
cd ~
git clone https://github.com/<YOUR_GH_USER>/wise-pi.git
cd wise-pi
git fetch --all --prune
git switch -c pi-dash-7in origin/pi-dash-7in

3) Python venv & dependencies
cd ~/wise-pi/dash/app
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt


Config (optional for now):

config.yaml – theme/intervals (already defaults to sane values)

env.example – copy to .env if you add API keys later

4) Quick manual test (optional)
cd ~/wise-pi/dash/app
. .venv/bin/activate
# Serve on all interfaces so you can hit it from your laptop too:
python -m uvicorn main:app --host 0.0.0.0 --port 8000


On the Pi: open Chromium to http://localhost:8000

From another machine: http://<pi-ip>:8000

Stop with Ctrl+C.

5) Install the API as a service

We’ll run Uvicorn as a systemd service so it starts at boot.

# Create /etc/systemd/system/wise-pi-dash.service
sudo tee /etc/systemd/system/wise-pi-dash.service >/dev/null <<'EOF'
[Unit]
Description=Wise Pi Dash (FastAPI + Uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=%i
WorkingDirectory=/home/%i/wise-pi/dash/app
Environment="PATH=/home/%i/wise-pi/dash/app/.venv/bin"
ExecStart=/home/%i/wise-pi/dash/app/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Replace %i with your username and enable/start
sudo systemctl daemon-reload
sudo systemctl enable wise-pi-dash.service
sudo systemctl start  wise-pi-dash.service

# Verify:
systemctl status wise-pi-dash --no-pager
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8000/
# Expect "200"


Security note: If you don’t want LAN devices to access the API, bind to loopback:
change --host 0.0.0.0 → --host 127.0.0.1 in the unit file and restart the service.

6) Autostart Chromium in kiosk

We use a simple LXDE/Labwc autostart entry in the user’s session:

mkdir -p ~/.config/autostart
cat > ~/.config/autostart/wisepi-kiosk.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=WisePi Kiosk
Comment=Launch Chromium to the local dash
Exec=/bin/sh -lc 'sleep 5; B=$(command -v chromium || command -v chromium-browser); exec "$B" --noerrdialogs --disable-session-crashed-bubble --disable-infobars --kiosk http://localhost:8000'
X-GNOME-Autostart-enabled=true
EOF


Reboot and you should land directly in the fullscreen quote view.

If you installed unclutter:

unclutter -idle 1 -root &


To make that persistent, add it to ~/.config/lxsession/LXDE-pi/autostart or equivalent session startup file.

7) Rotate the display (optional)

If your 7" is DSI and you want it upside-down (e.g., connector at bottom):

Easiest: sudo raspi-config → Display Options → Screen Orientation

Manual: add to /boot/firmware/config.txt:

lcd_rotate=2


Then sudo reboot.

On Bookworm, /boot/firmware/config.txt is the correct path. On older images it may be /boot/config.txt.

8) Update / maintenance

Pull code updates:

cd ~/wise-pi
git fetch --all --prune
git switch pi-dash-7in
git pull --ff-only
# If Python deps changed:
cd ~/wise-pi/dash/app
. .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart wise-pi-dash

Troubleshooting

Kiosk didn’t launch at login

Ensure the .desktop file path is exact: ~/.config/autostart/wisepi-kiosk.desktop

Confirm Chromium is installed (chromium or chromium-browser)

Try launching manually:
chromium --kiosk http://localhost:8000 (or chromium-browser ...)

API not running

systemctl status wise-pi-dash --no-pager

Logs: journalctl -u wise-pi-dash -n 200 --no-pager

Port test: curl -I http://localhost:8000/

Two displays (HDMI + DSI) weirdness

The window manager may promote one display; unplug HDMI during testing or set primary display in Raspberry Pi Configuration.

No quotes / errors

Network/DNS issues will fall back to status or error on screen.

Check internet access: ping -c 2 8.8.8.8 and ping -c 2 zenquotes.io

3D-printed desk brackets (optional)

File: dash/stl/bracket_stand_v1.stl

Intended for M2.5 screws into the 7" display’s four rear bosses.

Measured hole rectangle: ~92 mm (H) × 154 mm (W), centered.
(Please verify—clone displays vary!)

Two suggested tilt angles: 60° (more relaxed) and 70° (more upright).
Current STL is a single-angle design; tweak as needed.

Roadmap ideas

Day/Night themes (light/dark schedule)

Weather/Calendar/Headlines tiles

Settings page to adjust font size, refresh interval, theme

Offline cache for quotes

License

MIT (see repository root).

Credits

FastAPI + Uvicorn for the API

Chromium for kiosk

zenquotes.io for quotes (no key required)