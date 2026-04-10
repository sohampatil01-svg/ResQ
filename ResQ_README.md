# ResQ — Citizen Safety & Emergency Management Platform

## Quick Start

```bash
# 1. Install dependency
pip install flask

# 2. Start the server
python3 ResQ_server.py

# 3. Open in browser
# http://localhost:8000
```

## Mobile / Android

- Open the app from your phone browser on the same network: `http://<PC_IP>:8000`
- The app now uses a relative API base, so it works from your phone and not only from localhost.
- A Web App Manifest and service worker were added, so Chrome can install ResQ as a standalone Android app when served from a secure origin or localhost.

## What's Included

### Backend (ResQ_server.py)
- **Flask + SQLite** — zero external dependencies beyond Flask
- **Auto-seeds database** with 18 emergency services, 7 incidents, 1 missing person
- **Photo upload** support for incident reports (stored in uploads/ folder)
- **Background thread** expires check-in timers automatically

### Frontend (ResQ_App.html)
- Served automatically by the backend at http://localhost:8000
- Also works standalone (opens from file, connects to localhost:8000)
- **Real OpenStreetMap tiles** — actual streets and landmarks
- **Light + Dark mode** toggle, persists across sessions
- Mobile-first layout, works on phone/tablet/desktop

## Features & API Endpoints

| Feature | Endpoints |
|---------|-----------|
| **Dashboard** | GET /api/stats |
| **Safety Map** | GET /api/incidents (filter by category, severity, hours, radius) |
| **Report Incident** | POST /api/incidents (with photo upload support) |
| **Upvote/Verify** | POST /api/incidents/:id/upvote |
| **Emergency Services** | GET /api/emergency-services (sorted by distance) |
| **SOS Contacts** | GET/POST/DELETE /api/sos-contacts |
| **Trigger SOS** | POST /api/sos/trigger (dispatches to all contacts) |
| **Check-In Timer** | POST /api/checkins, POST /api/checkins/:id/confirm |
| **Missing Persons** | GET/POST /api/missing-persons, PATCH /api/missing-persons/:id/found |
| **Safe Routes** | POST /api/safe-routes (analyses danger from nearby incidents) |
| **Route History** | GET /api/safe-routes/history |
| **First Aid** | Fully offline, no API needed |

## Production Notes

- Replace Flask dev server with Gunicorn: `gunicorn -w 4 server:app`
- Add Twilio integration in `trigger_sos()` for real SMS/WhatsApp alerts
- PostgreSQL can replace SQLite by changing `sqlite3.connect()` to psycopg2
- Add JWT authentication for multi-user support
- Configure CORS origins for your domain

## Emergency Numbers (India)
- Police: 100
- Fire: 101  
- Ambulance: 108
- National SOS: 112
