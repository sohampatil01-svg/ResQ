#!/usr/bin/env python3
"""
ResQ — Citizen Safety & Emergency Management
Embedded Android server: Flask + SQLite
"""

import os, json, uuid, sqlite3, math, time, base64, io, threading
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, g, send_file

# ─────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.environ.get("HOME", BASE_DIR), 'resq.db')
UPLOAD_DIR = os.path.join(os.environ.get("HOME", BASE_DIR), 'uploads')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ─────────────────────────────────────────
# CORS
# ─────────────────────────────────────────
@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,PATCH,DELETE,OPTIONS'
    return r

@app.before_request
def preflight():
    if request.method == 'OPTIONS':
        from flask import Response
        return Response('', 204)

# ─────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def qry(sql, params=(), one=False):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    if one:
        row = cur.fetchone()
        return dict(row) if row else None
    return [dict(r) for r in cur.fetchall()]

def run(sql, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur.lastrowid

def uid(): return str(uuid.uuid4()).replace('-', '')[:16]
def now_ms(): return int(time.time() * 1000)
def ok(data=None, **kw):
    r = {'success': True}
    if data is not None: r['data'] = data
    r.update(kw)
    return jsonify(r)
def err(msg, code=400): return jsonify({'success': False, 'error': msg}), code

def haversine(a, b, c, d):
    R = 6371
    dL = math.radians(c - a); dG = math.radians(d - b)
    x = math.sin(dL/2)**2 + math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(dG/2)**2
    return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1 - x))

# ─────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    description TEXT DEFAULT '',
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    address TEXT DEFAULT '',
    photo_path TEXT,
    severity TEXT DEFAULT 'medium',
    anonymous INTEGER DEFAULT 0,
    verified INTEGER DEFAULT 0,
    upvotes INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS emergency_services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    address TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    hours TEXT DEFAULT '24/7',
    rating REAL DEFAULT 0,
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sos_contacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT DEFAULT '',
    relationship TEXT DEFAULT 'other',
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sos_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    lat REAL,
    lng REAL,
    message TEXT DEFAULT '',
    contacts_notified INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS checkins (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_name TEXT DEFAULT 'Anonymous',
    lat REAL,
    lng REAL,
    timer_minutes INTEGER NOT NULL,
    status TEXT DEFAULT 'active',
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    confirmed_at INTEGER
);
CREATE TABLE IF NOT EXISTS missing_persons (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER,
    gender TEXT DEFAULT '',
    description TEXT DEFAULT '',
    last_seen_location TEXT DEFAULT '',
    last_seen_lat REAL,
    last_seen_lng REAL,
    last_seen_date TEXT DEFAULT '',
    contact_name TEXT DEFAULT '',
    contact_phone TEXT DEFAULT '',
    photo_path TEXT,
    status TEXT DEFAULT 'missing',
    views INTEGER DEFAULT 0,
    tips_count INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS missing_tips (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES missing_persons(id),
    tip TEXT NOT NULL,
    location TEXT DEFAULT '',
    anonymous INTEGER DEFAULT 1,
    contact_info TEXT DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS route_history (
    id TEXT PRIMARY KEY,
    session_id TEXT DEFAULT '',
    from_address TEXT DEFAULT '',
    from_lat REAL,
    from_lng REAL,
    to_address TEXT DEFAULT '',
    to_lat REAL,
    to_lng REAL,
    mode TEXT DEFAULT 'walking',
    safety_score REAL,
    incidents_nearby INTEGER DEFAULT 0,
    distance_km REAL,
    estimated_minutes INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inc_cat ON incidents(category);
CREATE INDEX IF NOT EXISTS idx_inc_ts ON incidents(created_at);
CREATE INDEX IF NOT EXISTS idx_ck_sess ON checkins(session_id);
CREATE INDEX IF NOT EXISTS idx_miss_st ON missing_persons(status);
"""

# ─────────────────────────────────────────
# SEED DATA
# ─────────────────────────────────────────
def seed():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executescript(SCHEMA)

            # Seed emergency services if empty
            count = conn.execute("SELECT COUNT(*) FROM emergency_services").fetchone()[0]
            if count == 0:
                services = [
                    ('Ruby Hall Clinic', 'hospital', 18.5314, 73.8446, 'Sassoon Road, Pune', '020-26163391', '24/7', 4.2),
                    ('Sassoon General Hospital', 'hospital', 18.5194, 73.8553, 'JPN Road, Pune', '020-26128000', '24/7', 3.8),
                    ('Deenanath Mangeshkar Hospital', 'hospital', 18.5070, 73.8207, 'Erandwane, Pune', '020-49150101', '24/7', 4.4),
                    ('Jehangir Hospital', 'hospital', 18.5221, 73.8698, '32 Sassoon Road, Pune', '020-66810000', '24/7', 4.3),
                    ('Pune Police HQ', 'police', 18.5204, 73.8567, '2 Sadhu Vaswani Road', '020-26126262', '24/7', 3.5),
                    ('Deccan Gymkhana Police', 'police', 18.5167, 73.8394, 'Deccan Gymkhana', '020-25670330', '24/7', 3.7),
                    ('Camp Police Station', 'police', 18.5170, 73.8679, 'East Street, Camp', '020-26334400', '24/7', 3.6),
                    ('Shivajinagar Fire Station', 'fire', 18.5308, 73.8475, 'Shivajinagar, Pune', '020-25536000', '24/7', 4.1),
                    ('Swargate Fire Station', 'fire', 18.5013, 73.8603, 'Swargate, Pune', '020-24445555', '24/7', 4.0),
                    ('Apollo Pharmacy FC Road', 'pharmacy', 18.5285, 73.8543, 'FC Road, Pune', '1800-599-0101', '8am-10pm', 4.3),
                    ('MedPlus Camp', 'pharmacy', 18.5220, 73.8478, 'Camp, Pune', '040-67006700', '7am-11pm', 4.0),
                    ('Wellness Forever Kothrud', 'pharmacy', 18.5156, 73.8274, 'Kothrud, Pune', '1800-233-9255', '8am-11pm', 4.2),
                ]
                for s in services:
                    conn.execute("INSERT INTO emergency_services (id, name, type, lat, lng, address, phone, hours, rating) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (uid(), *s))

                # Seed sample incidents
                incidents = [
                    ('theft', 'Phone snatching near bus stop, suspect on motorcycle', 18.5245, 73.8540, 'FC Road, Pune', 'high', 1, 1, 12),
                    ('accident', 'Minor collision at JM Road signal, heavy congestion', 18.5312, 73.8476, 'JM Road, Pune', 'medium', 0, 0, 5),
                    ('flood', 'Severe waterlogging near Swargate, 2 cars stranded', 18.5178, 73.8554, 'Swargate, Pune', 'medium', 0, 1, 23),
                    ('harassment', 'Eve teasing reported near Deccan bus stop', 18.5290, 73.8420, 'Deccan, Pune', 'high', 1, 0, 8),
                    ('fire', 'Small fire near garbage dump, locals extinguished it', 18.5228, 73.8612, 'Camp Area, Pune', 'low', 0, 1, 3),
                    ('medical', 'Person collapsed near Laxmi Road market, ambulance called', 18.5180, 73.8601, 'Laxmi Road, Pune', 'high', 0, 1, 7),
                    ('infrastructure', 'Large pothole caused multiple tyre punctures overnight', 18.5102, 73.8341, 'Kothrud main road', 'low', 0, 0, 15),
                ]
                for i in incidents:
                    conn.execute("INSERT INTO incidents (id, category, description, lat, lng, address, severity, anonymous, verified, upvotes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (uid(), *i, now_ms(), now_ms()))

                # Seed missing person
                conn.execute("INSERT INTO missing_persons (id, name, age, gender, description, last_seen_location, last_seen_lat, last_seen_lng, contact_name, contact_phone, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (uid(), 'Rahul Sharma', 25, 'male', 'Last seen wearing blue shirt and jeans', 'FC Road, Pune', 18.5204, 73.8567, 'Priya Sharma', '9876543210', 'missing', now_ms(), now_ms()))
            conn.commit()
    except Exception as e:
        print(f"Seed error: {e}")

def expire_checkins_loop():
    while True:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                now = now_ms()
                conn.execute("UPDATE checkins SET status='expired' WHERE status='active' AND expires_at < ?", (now,))
                conn.commit()
            time.sleep(60)
        except:
            time.sleep(60)

# ─────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────
@app.route('/api/health')
def health():
    return ok({'status': 'ok', 'version': '1.0'})

@app.route('/api/stats')
def stats():
    inc_24 = qry("SELECT COUNT(*) as count FROM incidents WHERE created_at > ?", (now_ms() - 86400000,), True)['count']
    hi_24 = qry("SELECT COUNT(*) as count FROM incidents WHERE severity='high' AND created_at > ?", (now_ms() - 86400000,), True)['count']
    active_ck = qry("SELECT COUNT(*) as count FROM checkins WHERE status='active'", (), True)['count']
    miss_active = qry("SELECT COUNT(*) as count FROM missing_persons WHERE status='missing'", (), True)['count']
    svc_count = qry("SELECT COUNT(*) as count FROM emergency_services", (), True)['count']
    return ok(incidents_24h=inc_24, high_severity_24h=hi_24, active_checkins=active_ck, missing_active=miss_active, services_count=svc_count)

@app.route('/api/incidents', methods=['GET'])
def get_incidents():
    cat = request.args.get('category', 'all')
    sev = request.args.get('severity', 'all')
    hours = int(request.args.get('hours', '24'))
    lat_q = request.args.get('lat')
    lng_q = request.args.get('lng')
    radius = float(request.args.get('radius', '10'))

    sql = "SELECT * FROM incidents WHERE created_at > ?"
    params = [now_ms() - hours * 3600000]

    if cat != 'all':
        sql += " AND category = ?"
        params.append(cat)
    if sev != 'all':
        sql += " AND severity = ?"
        params.append(sev)

    sql += " ORDER BY created_at DESC"
    data = qry(sql, params)

    # Simple Python-side radius filtering if lat/lng provided
    if lat_q and lng_q:
        lat_q, lng_q = float(lat_q), float(lng_q)
        data = [i for i in data if haversine(lat_q, lng_q, i['lat'], i['lng']) <= radius]

    return ok(data)

@app.route('/api/incidents', methods=['POST'])
def create_incident():
    data = request.get_json()
    if not data or not data.get('lat') or not data.get('lng'):
        return err('Location required')

    inc_id = uid()
    photo_path = None
    # Handle base64 photo if present in JSON or handle multipart

    qry("INSERT INTO incidents (id, category, description, lat, lng, address, photo_path, severity, anonymous, verified, upvotes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (inc_id, data.get('category', 'other'), data.get('description', ''), data['lat'], data['lng'], data.get('address', ''), photo_path, data.get('severity', 'medium'), int(data.get('anonymous', False)), 0, 0, now_ms(), now_ms()))
    return ok({'id': inc_id})

@app.route('/api/incidents/<iid>/upvote', methods=['POST'])
def upvote(iid):
    qry("UPDATE incidents SET upvotes = upvotes + 1 WHERE id = ?", (iid,))
    return ok()

@app.route('/api/emergency-services', methods=['GET'])
def get_services():
    typ = request.args.get('type', 'all')
    lat_q = request.args.get('lat')
    lng_q = request.args.get('lng')

    sql = "SELECT * FROM emergency_services"
    params = []
    if typ != 'all':
        sql += " WHERE type = ?"
        params.append(typ)

    data = qry(sql, params)
    if lat_q and lng_q:
        lat_q, lng_q = float(lat_q), float(lng_q)
        for s in data:
            s['distance_km'] = round(haversine(lat_q, lng_q, s['lat'], s['lng']), 1)
        data.sort(key=lambda x: x['distance_km'])

    return ok(data)

@app.route('/api/sos-contacts', methods=['GET'])
def get_contacts():
    session = request.args.get('session', 'default')
    data = qry("SELECT * FROM sos_contacts WHERE session_id = ?", (session,))
    return ok(data)

@app.route('/api/sos-contacts', methods=['POST'])
def add_contact():
    data = request.get_json()
    if not data or not data.get('name') or not data.get('phone'):
        return err('Name and phone required')

    ct_id = uid()
    qry("INSERT INTO sos_contacts (id, session_id, name, phone, email, relationship, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ct_id, data.get('session', 'default'), data['name'], data['phone'], data.get('email', ''), data.get('relationship', 'other'), now_ms()))
    return ok({'id': ct_id})

@app.route('/api/sos-contacts/<cid>', methods=['DELETE'])
def del_contact(cid):
    qry("DELETE FROM sos_contacts WHERE id = ?", (cid,))
    return ok()

@app.route('/api/sos/trigger', methods=['POST'])
def trigger_sos():
    data = request.get_json()
    session = data.get('session', 'default')
    lat = data.get('lat')
    lng = data.get('lng')
    msg = data.get('message', 'I need help — ResQ Emergency Alert!')
    
    cts = qry("SELECT * FROM sos_contacts WHERE session_id = ?", (session,))
    maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}" if lat and lng else "Location unavailable"
    
    event_id = uid()
    qry("INSERT INTO sos_events (id, session_id, lat, lng, message, contacts_notified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (event_id, session, lat, lng, msg, len(cts), now_ms()))
    
    # Send real SMS via Android if running on device
    dispatched = []
    try:
        from com.resq.mobile import MainActivity
        activity = MainActivity.instance
        if activity:
            for c in cts:
                full_msg = f"🚨 ResQ SOS from {c['name']}: {msg}\n📍 Location: {maps_link}"
                activity.sendSMS(c['phone'], full_msg)
                dispatched.append({
                    'contact': c['name'],
                    'phone': c['phone'],
                    'message': full_msg,
                    'status': 'dispatched_to_android'
                })
        else:
            print("DEBUG: MainActivity instance not found, simulation mode")
    except Exception as e:
        print(f"DEBUG: SMS error: {e}")

    # Fallback/Simulation if not on android or no contacts
    if not dispatched:
        for c in cts:
            full_msg = f"🚨 ResQ SOS from {c['name']}: {msg}\n📍 Location: {maps_link}"
            dispatched.append({
                'contact': c['name'],
                'phone': c['phone'],
                'message': full_msg,
                'status': 'simulated'
            })
            print(f"DEBUG: (Simulated) Sending SOS to {c['name']} ({c['phone']}): {full_msg}")

    return ok({
        'id': event_id,
        'contacts_notified': len(cts),
        'dispatched': dispatched,
        'maps_link': maps_link
    })

@app.route('/api/checkins', methods=['POST'])
def create_checkin():
    data = request.get_json()
    if not data or not data.get('timer_minutes'):
        return err('Timer minutes required')

    ck_id = uid()
    expires = now_ms() + data['timer_minutes'] * 60000
    qry("INSERT INTO checkins (id, session_id, user_name, lat, lng, timer_minutes, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ck_id, data.get('session', 'default'), data.get('user_name', 'Anonymous'), data.get('lat'), data.get('lng'), data['timer_minutes'], 'active', now_ms(), expires))
    return ok({'id': ck_id, 'expires_at': expires})

@app.route('/api/missing-persons', methods=['GET'])
def get_missing():
    status = request.args.get('status', 'missing')
    q = request.args.get('q', '')
    sql = "SELECT * FROM missing_persons WHERE status = ?"
    params = [status]
    if q:
        sql += " AND (name LIKE ? OR last_seen_location LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%'])
    sql += " ORDER BY created_at DESC"
    data = qry(sql, params)
    return ok(data)

@app.route('/api/missing-persons', methods=['POST'])
def create_missing():
    data = request.get_json()
    if not data or not data.get('name'):
        return err('Name required')

    mp_id = uid()
    qry("INSERT INTO missing_persons (id, name, age, gender, description, last_seen_location, last_seen_lat, last_seen_lng, contact_name, contact_phone, photo_path, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (mp_id, data['name'], data.get('age'), data.get('gender', ''), data.get('description', ''), data.get('last_seen_location', ''), data.get('last_seen_lat'), data.get('last_seen_lng'), data.get('contact_name', ''), data.get('contact_phone', ''), None, 'missing', now_ms(), now_ms()))
    return ok({'id': mp_id})

@app.route('/api/safe-routes', methods=['POST'])
def analyse_route():
    data = request.get_json()
    if not data or not data.get('from_lat') or not data.get('to_lat'):
        return err('From and to locations required')

    f_lat, f_lng = data['from_lat'], data['from_lng']
    t_lat, t_lng = data['to_lat'], data['to_lng']
    mode = data.get('mode', 'walking')

    dist_km = haversine(f_lat, f_lng, t_lat, t_lng)
    eta = int((dist_km / {'walking': 5, 'cycling': 15, 'driving': 40}.get(mode, 5)) * 60)

    m_lat, m_lng = (f_lat + t_lat) / 2, (f_lng + t_lng) / 2
    # Simplified danger check
    nearby_data = qry("SELECT lat, lng, severity FROM incidents WHERE created_at > ?", (now_ms() - 43200000,))
    nearby_count = 0
    for i in nearby_data:
        if haversine(m_lat, m_lng, i['lat'], i['lng']) < 2:
            nearby_count += 1

    score = max(0, min(100, 100 - nearby_count * 10))
    route_id = uid()
    qry("INSERT INTO route_history (id, session_id, from_address, from_lat, from_lng, to_address, to_lat, to_lng, mode, safety_score, incidents_nearby, distance_km, estimated_minutes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (route_id, data.get('session', 'default'), data.get('from_address', ''), f_lat, f_lng, data.get('to_address', ''), t_lat, t_lng, mode, score, nearby_count, dist_km, eta, now_ms()))

    return ok({
        'id': route_id,
        'safety_score': score,
        'recommendation': 'Route appears safe' if score > 70 else 'Use caution' if score > 40 else 'Consider alternative route',
        'incidents_nearby': nearby_count,
        'distance_km': round(dist_km, 2),
        'estimated_minutes': eta,
        'google_maps_url': f"https://www.google.com/maps/dir/{f_lat},{f_lng}/{t_lat},{t_lng}/"
    })

# ─────────────────────────────────────────
# FRONTEND
# ─────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:p>')
def catch_all(p):
    if os.path.exists(os.path.join(STATIC_DIR, p)):
        return send_from_directory(STATIC_DIR, p)
    return send_from_directory(STATIC_DIR, 'index.html')

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def main():
    seed()
    t = threading.Thread(target=expire_checkins_loop, daemon=True)
    t.start()
    print("ResQ Android Server Starting on http://127.0.0.1:8000")
    app.run(host='127.0.0.1', port=8000, debug=False, threaded=True)

if __name__ == '__main__':
    main()
