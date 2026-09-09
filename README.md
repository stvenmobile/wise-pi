
<p float="left">
  <img src="images/rpi4_hdmi1.jpg" width="48%" alt="Front">
  <img src="images/rpi4_hdmi2.jpg"  width="48%" alt="Back">
</p>



# Wise-Pi HDMI — Setup Guide

A lightweight FastAPI web app hosted on raspberry Pi 4/5 that shows multiple types of content on a standard HDMI Display, 
running in **Chromium kiosk mode** at boot. The application will provide a sequence of displays including any of the following 
content types: Zenquote random quote, Ninjaquote random quote from selectable categories, artwork from the Smithsonian 
Institution, artwork from the Harvard Art Museum, or a random photo from user's Flickr account.
The length of time each content type remains visible is configurable, as well as which of the types to include in the rotation, 
and the order in which they are displayed.

### Architecture: two independent pieces

This app is really two things that start independently, which matters when troubleshooting a blank/grey screen:

1. **`wise-pi.service`** (systemd) — runs the FastAPI backend (`uvicorn`) on port 8000. This only serves content over HTTP; it has no idea whether anything is actually displaying it.
2. **Chromium kiosk** — *not* a systemd service. It's launched by an XDG autostart entry (`~/.config/autostart/wisepi-kiosk.desktop`) when the graphical desktop session starts. `systemd/wise-kiosk.service` exists in this repo only as a non-working reference (see the comment at the top of that file) — it is not used.

**A "healthy" `wise-pi.service` tells you nothing about the display.** If the screen is blank, check the kiosk/Chromium side (autostart entry, desktop session, GPU rendering) separately from the API service — see Troubleshooting below.

---

## What you’ll need

- **Raspberry Pi (RPI 4 or RPI 5)**
- **HDMI Display (PC Monitor, 7" monitor, etc.)**
- **Raspberry Pi OS (Bookworm) 64-bit with Desktop** 
- **Network access (Wi-Fi or Ethernet)**

**Repo layout (branch `rpi4-hdmi`):**
app/
- requirements.txt
- config.yaml
- env.example
- flickr.py
- main.py
- weather.py
- static/
  - index.htm
  - styles.css
autostart/
- unclutter.desktop
- wisepi-kiosk.desktop
images/
systemd/
- wise-pi.service
- wise-kiosk.service   (non-working reference only — kiosk actually launches via autostart/, not systemd)


---

### 1) OS prep
Update the OS and reboot:
```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```
Install packages:

```bash
sudo apt install -y git python3-venv chromium-browser curl
# Some images use `chromium` instead of `chromium-browser`; we handle both later.
# Optional: hide the mouse in kiosk
sudo apt install -y unclutter
```
---
### 2) Get the code
```bash
cd ~
git clone https://github.com/stvenmobile/wise-pi.git
cd wise-pi
git fetch --all --prune
git switch -c rpi4-hdmi origin/rpi4-hdmi
```
### 3) Python venv & dependencies
```bash
cd ~/wise-pi/app
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```
Review settings in config.yaml, adjust rotation to only include elements you want to include.

Create your `.env` from the template and fill in the keys for whichever content types you enabled in `config.yaml`:
```bash
cp ~/wise-pi/app/env.example ~/wise-pi/app/.env
nano ~/wise-pi/app/.env
```
`.env` is only picked up because `systemd/wise-pi.service` includes `EnvironmentFile=-/home/<user>/wise-pi/app/.env` — if you rename or move the app directory, update that line too, or the API keys silently won't reach the process and those content sources will just fail over to the next one in the rotation (zenquotes needs no key, so it'll still work, but nothing else will).

### 4) Quick manual test (optional)
```bash
cd ~/wise-pi/app
. .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```
On the Pi: open Chromium to http://localhost:8000
From another device: http://<pi-ip>:8000
Stop with Ctrl+C.

### 5) Install and Enable Systemd Service

The service file in the `systemd/` directory is complete but edit to replace the placeholder username 'steve'. 
The service file enables the backend python application to run as a service.

**CRITICAL: Use a text editor to globally replace ALL occurrences of 'steve' in `wise-pi.service` with YOUR actual Raspberry Pi username** (this affects `WorkingDirectory`, `PATH`, `EnvironmentFile`, and `User`/`Group`).


```bash
sudo cp ~/wise-pi/systemd/wise-pi.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable wise-pi.service
sudo systemctl start wise-pi.service
sudo systemctl status wise-pi --no-pager            # status should be active

curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8000/   # expect 200
```

Tip (local-only): If you don’t want WAN devices to access the API, bind to loopback:
change --host 0.0.0.0 → --host 127.0.0.1 in the unit file and restart the service.


### 6) Configure Autostart to load Chromium in kiosk and unclutter desktop
Use a desktop autostart entry to open Chromium fullscreen to the local app:

```bash
cp ~/wise-pi/autostart/unclutter.desktop ~/.config/autostart/
cp ~/wise-pi/autostart/wisepi-kiosk.desktop ~/.config/autostart/
```

Reboot and access the app URL to confirm kiosk mode.
http://<RPI IP ADDRESS>:8000

## Troubleshooting

Remember: the API (`wise-pi.service`) and the Chromium kiosk are independent (see Architecture above). "The service is running" only tells you the API is up — check the kiosk/display side separately.

### Backend API not running / not returning content
```bash
systemctl status wise-pi --no-pager
journalctl -u wise-pi -n 200 --no-pager
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8000/   # expect 200
curl -s http://localhost:8000/api/content
```
If this returns errors, check `app/wisepi.log` and confirm `.env` exists and is populated (see step 3) — repeated `FAILOVER` log lines mean a content source is missing its API key.

### Kiosk didn't launch at login (screen shows the desktop, not the app)
The kiosk is *not* a systemd service — it's an XDG autostart entry, so it only runs once a full graphical desktop session starts.
```bash
systemctl get-default                       # expect "graphical.target"
ls -la ~/.config/autostart/                 # expect wisepi-kiosk.desktop present
ps -ef | grep -iE "chromium|lightdm|Xorg"   # confirm a desktop session + chromium are actually running
which chromium chromium-browser             # confirm the binary referenced in the .desktop file exists
```
Try launching it manually to see errors directly:
```bash
DISPLAY=:0 XAUTHORITY=/home/<user>/.Xauthority chromium --kiosk http://localhost:8000
```

### Monitor is a solid grey screen — no text, no images, nothing (backend and Chromium both confirmed running)
This is a known Raspberry Pi GPU-rendering issue, not a content problem. Raspberry Pi OS's `chromium` wrapper auto-injects `--enable-gpu-rasterization --use-angle=gles`, and on some Pi 4/5 + Mesa/V3D driver combinations that combination initializes the GPU compositor but never actually paints a frame to the display — Chromium (and its GPU process) keep running, but nothing is ever drawn. A telltale sign is the Chromium `--type=gpu-process` accumulating almost no CPU time even though the page is actively refreshing content underneath.

Fix: disable GPU rendering for the kiosk. This repo's `autostart/wisepi-kiosk.desktop` already includes `--disable-gpu` in its `Exec=` line — if you're hitting this, confirm your deployed copy at `~/.config/autostart/wisepi-kiosk.desktop` has it too (older checkouts won't):
```bash
grep -- --disable-gpu ~/.config/autostart/wisepi-kiosk.desktop
```
If it's missing, edit the `Exec=` line to add `--disable-gpu` alongside the other flags, then `pkill -f chromium` and reboot to confirm the autostart entry picks it up cleanly.

You can test the theory live before editing anything:
```bash
pkill -f chromium
DISPLAY=:0 XAUTHORITY=/home/<user>/.Xauthority chromium --disable-gpu --incognito --no-first-run --noerrdialogs --password-store=basic --kiosk --disable-web-security http://localhost:8000/
```
(Omitting `--password-store=basic` here will trigger a GNOME keyring unlock prompt — harmless, but include it to match the real kiosk flags and avoid the prompt.)



## Roadmap ideas
Dark/Light themes 
Add Calendar content
Other content

## License
MIT (see repository root).

## Credits
FastAPI + Uvicorn for the API
Chromium for kiosk
zenquotes.io for quotes (no key required)

