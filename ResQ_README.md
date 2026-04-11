# ResQ v2.0.0 — Citizen Safety & Emergency Management Platform

ResQ is a modern safety platform designed to empower communities with real-time incident reporting, safe route planning, and emergency coordination.

## Download
### 📥 **[Download ResQ v2.0.0 Android APK](https://github.com/sohampatil01-svg/ResQ/raw/binaries/ResQ-v2.0.0.apk)**

## What's New in v2.0.0
- **Indigo Theme Overhaul:** A complete visual redesign using a professional Indigo and Slate palette.
- **Inter Typography:** Switched to the Inter font family for maximum clarity and a premium feel.
- **Enhanced UI/UX:** Improved layout with better spacing, modern shadows, and refined card designs.
- **Improved Android Stability:** Fixed build issues related to Python environments (Python 3.12+ compatibility).

📥 **[Download Latest APK (v2.1)](https://github.com/sohampatil01-svg/ResQ/releases/download/v2.1/app-debug.apk)**

## Quick Start

```bash
# 1. Install dependency
pip install flask werkzeug

# 2. Start the server
python3 ResQ_server.py

# 3. Open in browser
# http://localhost:8000
```

## Key Features
- **Real-time Safety Map:** View and report incidents (theft, accident, fire, etc.) with live updates using real OpenStreetMap tiles.
- **Safe Route Planner:** Get safety scores for your travel paths based on recent community data.
- **Emergency SOS:** Instantly alert saved contacts with your live GPS location.
- **Safety Check-in:** A timer-based system that alerts your contacts if you don't check in safely.
- **First Aid Guide:** Comprehensive, offline-ready medical procedures for emergencies.
- **Missing Persons Bureau:** Community-driven network to help locate missing individuals.

## Tech Stack
- **Backend:** Python (Flask), SQLite
- **Frontend:** Vanilla JS, Leaflet.js, CSS3 (Modern Indigo Theme)
- **Mobile:** Android (Kotlin + Chaquopy for embedded Python backend)

## Project Structure
- `ResQ_server.py`: The core Flask-based API and web server.
- `static/`: Contains the themed frontend (HTML/CSS/JS).
- `android-app/`: The native Android wrapper project.
- `resq.db`: SQLite database for persistent storage.

## Emergency Numbers (India)
- Police: 100
- Fire: 101  
- Ambulance: 108
- National SOS: 112
