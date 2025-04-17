# Wise-Pi

A minimalist Raspberry Pi Zero project that displays rotating quotes on a Waveshare 2.7" e-paper display.

Perfect for your desk, nightstand, bookshelf, or as a gift.

---

## 📷 Overview

Wise-Pi is a self-contained quote display that fetches and displays inspirational quotes from the internet every 30 minutes. The screen is a crisp, power-efficient e-paper display, so it stays readable even with power interruptions.

---

## 🛠️ Hardware Requirements

- Raspberry Pi Zero 2 W
- Waveshare 2.7" e-Paper HAT (264x176)
- microSD card (8GB or larger)
- USB power supply (e.g. phone charger)

Optional:

- 3D printed enclosure (STL files provided)

---

## 🔌 Software Setup

### 1. Flash Raspberry Pi OS (Lite or Desktop)

Use Raspberry Pi Imager to flash the SD card. Enable SSH and set up Wi-Fi if desired.

### 2. SSH In and Update

```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Clone this repository

```bash
git clone https://github.com/yourusername/Wise-Pi.git
cd Wise-Pi
```

## 📦 Python Setup

After installing system dependencies (see below), clone the repository and set up the virtual environment:

```bash
git clone https://github.com/yourusername/wise-pi.git
cd wise-pi
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt



### 4. Set up Python environment

```bash
sudo apt install python3-pip python3-venv -y
python3 -m venv quoteenv
source quoteenv/bin/activate
pip install -r requirements.txt
```

### 5. Run the Quote Display

```bash
python quote_display.py
```

### (Optional) Enable on boot with cron:



```bash
crontab -e
```

Add this line:

```bash
@reboot /home/pi/Wise-Pi/quoteenv/bin/python /home/pi/Wise-Pi/quote_display.py
```

---

## 🖼️ Case Design

- The included STLs provide a desk-friendly enclosure at a 20° angle
- Designed for flush display mounting with visible screen window
- Back panel is designed to snap-fit or screw into place (coming soon)

Files:

- `stl/front_face.stl`
- `stl/full_case.stl`
- (Back panel WIP)

---

## 📦 File List

- `quote_display.py` – main script
- `requirements.txt` – Python dependencies
- `stl/` – printable case parts
- `images/` – build photos, renders, and screenshots
- `docs/setup.md` – optional extended instructions

---

## 📸 Photos

*Coming soon: photos of the assembled unit and print-ready model previews.*

---

## 🌐 Credits & Attribution

- Quotes pulled from the [ZenQuotes API](https://zenquotes.io/)
- e-Paper driver provided by [Waveshare's Python libraries](https://github.com/waveshare/e-Paper)

---

## 🧪 License

MIT License — free to use, share, remix, and improve.

---

## 💡 Inspired by

The quiet joy of slow technology.

If you build one or remix it, please share a photo or fork it — we'd love to see it.

**Hackaday.io project page coming soon!**

