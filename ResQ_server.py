#!/usr/bin/env python3
"""
ResQ — Citizen Safety & Emergency Management
Full backend server: Flask + SQLite + all API endpoints
Run: python3 server.py
Serves frontend at http://localhost:8000
"""

import os, json, uuid, sqlite3, math, time, base64, io, threading
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, g, send_file

# ─────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, 'resq.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ─────────────────────────────────────────
# CORS
# ─────────────────────────────────────────
@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin']  = '*'
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

def uid():   return str(uuid.uuid4()).replace('-','')[:16]
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
    return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1-x))

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
CREATE INDEX IF NOT EXISTS idx_inc_ts  ON incidents(created_at);
CREATE INDEX IF NOT EXISTS idx_ck_sess ON checkins(session_id);
CREATE INDEX IF NOT EXISTS idx_miss_st ON missing_persons(status);
"""

# ─────────────────────────────────────────
# SEED DATA
# ─────────────────────────────────────────
SERVICES = [
    # Hospitals
    ('Ruby Hall Clinic','hospital',18.5314,73.8446,'Sassoon Road, Pune','020-26163391','24/7',4.2),
    ('Sassoon General Hospital','hospital',18.5194,73.8553,'JPN Road, Pune','020-26128000','24/7',3.8),
    ('Deenanath Mangeshkar Hospital','hospital',18.5070,73.8207,'Erandwane, Pune','020-49150101','24/7',4.4),
    ('Jehangir Hospital','hospital',18.5221,73.8698,'32 Sassoon Road, Pune','020-66810000','24/7',4.3),
    ('KEM Hospital','hospital',18.5038,73.8553,'Rasta Peth, Pune','020-26125600','24/7',4.0),
    ('Poona Hospital','hospital',18.5158,73.8534,'27 Sadashiv Peth, Pune','020-24330011','24/7',3.9),
    # Police
    ('Pune Police Commissioner Office','police',18.5204,73.8567,'2 Sadhu Vaswani Road','020-26126262','24/7',3.5),
    ('Deccan Gymkhana Police Station','police',18.5167,73.8394,'Deccan Gymkhana','020-25670330','24/7',3.7),
    ('Camp Police Station','police',18.5170,73.8679,'East Street, Camp','020-26334400','24/7',3.6),
    ('Swargate Police Station','police',18.5037,73.8583,'Swargate','020-24442040','24/7',3.4),
    ('Shivajinagar Police Station','police',18.5308,73.8413,'Shivajinagar','020-25530200','24/7',3.8),
    # Fire
    ('Shivajinagar Fire Station','fire',18.5308,73.8475,'Shivajinagar, Pune','020-25536000','24/7',4.1),
    ('Swargate Fire Station','fire',18.5013,73.8603,'Swargate, Pune','020-24445555','24/7',4.0),
    ('Kothrud Fire Station','fire',18.5028,73.8133,'Kothrud, Pune','020-25384111','24/7',3.9),
    # Pharmacy
    ('Apollo Pharmacy FC Road','pharmacy',18.5285,73.8543,'FC Road, Pune','1800-599-0101','8am-10pm',4.3),
    ('MedPlus Camp','pharmacy',18.5220,73.8478,'Camp, Pune','040-67006700','7am-11pm',4.0),
    ('Wellness Forever Kothrud','pharmacy',18.5156,73.8274,'Kothrud, Pune','1800-233-9255','8am-11pm',4.2),
    ('Noble Pharmacy','pharmacy',18.5345,73.8789,'Kalyani Nagar, Pune','020-26680999','9am-10pm',4.1),
]

def seed():
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()
        if db.execute("SELECT COUNT(*) FROM emergency_services").fetchone()[0] == 0:
            for s in SERVICES:
                db.execute(
                    "INSERT INTO emergency_services (id,name,type,lat,lng,address,phone,hours,rating) VALUES (?,?,?,?,?,?,?,?,?)",
                    (uid(),) + s
                )
            db.commit()
            print(f"✓ Seeded {len(SERVICES)} emergency services")
        if db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0:
            t = now_ms()
            samples = [
                (uid(),'theft','Phone snatching near bus stop — suspect fled on motorcycle',18.5245,73.8540,'FC Road, Pune','high',1,1,12,t-3600000),
                (uid(),'accident','Minor collision at JM Road signal, heavy congestion reported',18.5312,73.8476,'JM Road, Pune','medium',0,0,5,t-7200000),
                (uid(),'flood','Severe waterlogging near Swargate — 2 vehicles stranded',18.5178,73.8554,'Swargate, Pune','medium',0,1,23,t-1800000),
                (uid(),'harassment','Eve teasing near Deccan bus stop, group of 3',18.5290,73.8420,'Deccan, Pune','high',1,0,8,t-5400000),
                (uid(),'fire','Small fire near garbage dump — residents extinguished it',18.5228,73.8612,'Camp Area, Pune','low',0,1,3,t-900000),
                (uid(),'medical','Person collapsed near Laxmi Road market — ambulance called',18.5180,73.8601,'Laxmi Road, Pune','high',0,1,7,t-2700000),
                (uid(),'infrastructure','Large pothole causing multiple tyre punctures',18.5102,73.8341,'Kothrud main road','low',0,0,15,t-10800000),
            ]
            for s in samples:
                db.execute("INSERT INTO incidents (id,category,description,lat,lng,address,severity,anonymous,verified,upvotes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", s+(s[-1],))
            db.commit()
            print(f"✓ Seeded 7 sample incidents")
        if db.execute("SELECT COUNT(*) FROM missing_persons").fetchone()[0] == 0:
            t = now_ms()
            db.execute("INSERT INTO missing_persons (id,name,age,gender,description,last_seen_location,contact_name,contact_phone,status,views,tips_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,0,0,?,?)",
                (uid(),'Rajesh Kumar',45,'Male','Medium height, blue shirt, grey pants, has a beard. IT professional.','Near Hinjewadi Phase 2 bus stop — seen around 9 PM','Priya Kumar (wife)','+91 98765 43210','missing',t-86400000,t-86400000))
            db.commit()
            print("✓ Seeded 1 missing person")

# ─────────────────────────────────────────
# BACKGROUND TASK: expire checkins
# ─────────────────────────────────────────
def expire_checkins_loop():
    while True:
        try:
            with app.app_context():
                db = get_db()
                expired = db.execute(
                    "SELECT id,user_name,session_id FROM checkins WHERE status='active' AND expires_at < ?",
                    (now_ms(),)
                ).fetchall()
                for row in expired:
                    db.execute("UPDATE checkins SET status='expired' WHERE id=?", (row['id'],))
                    db.commit()
                    print(f"⚠ Check-in expired: {row['user_name']} — alerting contacts")
        except Exception as e:
            pass
        time.sleep(20)

# ═══════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════

# ── HEALTH ──────────────────────────────────
@app.route('/api/health')
def health():
    return ok({'status':'running','time':now_ms(),'version':'2.0.0','app':'ResQ'})

# ── STATS ────────────────────────────────────
@app.route('/api/stats')
def stats():
    t24 = now_ms() - 86400000
    by_cat = qry("SELECT category, COUNT(*) cnt FROM incidents WHERE created_at>? GROUP BY category ORDER BY cnt DESC",(t24,))
    return ok({
        'incidents_24h':     qry("SELECT COUNT(*) c FROM incidents WHERE created_at>?",(t24,),one=True)['c'],
        'high_severity_24h': qry("SELECT COUNT(*) c FROM incidents WHERE severity='high' AND created_at>?",(t24,),one=True)['c'],
        'total_incidents':   qry("SELECT COUNT(*) c FROM incidents",one=True)['c'],
        'active_checkins':   qry("SELECT COUNT(*) c FROM checkins WHERE status='active'",one=True)['c'],
        'missing_active':    qry("SELECT COUNT(*) c FROM missing_persons WHERE status='missing'",one=True)['c'],
        'sos_today':         qry("SELECT COUNT(*) c FROM sos_events WHERE created_at>?",(t24,),one=True)['c'],
        'services_count':    qry("SELECT COUNT(*) c FROM emergency_services",one=True)['c'],
        'by_category':       by_cat,
    })

# ── INCIDENTS ────────────────────────────────
@app.route('/api/incidents', methods=['GET'])
def get_incidents():
    hours  = int(request.args.get('hours', 24))
    cat    = request.args.get('category','all')
    sev    = request.args.get('severity','all')
    lat    = request.args.get('lat', type=float)
    lng    = request.args.get('lng', type=float)
    radius = request.args.get('radius', 20, type=float)
    limit  = min(int(request.args.get('limit',200)),500)
    cutoff = now_ms() - hours*3600000

    sql = "SELECT * FROM incidents WHERE created_at>?"
    p   = [cutoff]
    if cat and cat != 'all': sql += " AND category=?";  p.append(cat)
    if sev and sev != 'all': sql += " AND severity=?";  p.append(sev)
    sql += " ORDER BY created_at DESC LIMIT ?"; p.append(limit)

    rows = qry(sql, p)
    t = now_ms()
    result = []
    for r in rows:
        r['anonymous'] = bool(r['anonymous'])
        r['verified']  = bool(r['verified'])
        age_h = (t - r['created_at']) / 3600000
        r['age_hours']   = round(age_h, 1)
        r['decay_score'] = round(math.exp(-age_h / 6), 3)
        if lat and lng:
            d = haversine(lat, lng, r['lat'], r['lng'])
            if d <= radius:
                r['distance_km'] = round(d, 2)
                result.append(r)
        else:
            result.append(r)
    return ok(result, total=len(result))

@app.route('/api/incidents', methods=['POST'])
def create_incident():
    d = request.get_json(silent=True) or {}
    # Also handle multipart (photo upload)
    if request.files:
        d = request.form.to_dict()
    cat = (d.get('category') or '').strip()
    try:
        lat = float(d.get('lat', 0))
        lng = float(d.get('lng', 0))
    except:
        return err('lat/lng must be numbers')
    if not cat: return err('category is required')
    if not lat or not lng: return err('lat and lng are required')

    photo_path = None
    if request.files and 'photo' in request.files:
        f = request.files['photo']
        if f.filename:
            fname = uid() + '_' + f.filename.replace(' ','_')
            fpath = os.path.join(UPLOAD_DIR, fname)
            f.save(fpath)
            photo_path = '/api/uploads/' + fname
    # base64 photo
    elif d.get('photo_base64'):
        try:
            raw = base64.b64decode(d['photo_base64'].split(',')[-1])
            fname = uid() + '.jpg'
            with open(os.path.join(UPLOAD_DIR, fname), 'wb') as f:
                f.write(raw)
            photo_path = '/api/uploads/' + fname
        except: pass

    iid = uid()
    t   = now_ms()
    run("""INSERT INTO incidents (id,category,description,lat,lng,address,photo_path,severity,anonymous,verified,upvotes,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,0,0,?,?)""",
        (iid, cat, (d.get('description') or '')[:2000],
         lat, lng, (d.get('address') or '')[:300],
         photo_path, d.get('severity','medium'),
         1 if str(d.get('anonymous','')).lower() in ('true','1','yes') else 0,
         t, t))
    return ok({'id': iid, 'created_at': t, 'photo_url': photo_path}), 201

@app.route('/api/incidents/<iid>', methods=['GET'])
def get_incident(iid):
    r = qry("SELECT * FROM incidents WHERE id=?", (iid,), one=True)
    if not r: return err('Not found', 404)
    return ok(r)

@app.route('/api/incidents/<iid>/upvote', methods=['POST'])
def upvote(iid):
    if not qry("SELECT id FROM incidents WHERE id=?", (iid,), one=True):
        return err('Not found', 404)
    run("UPDATE incidents SET upvotes=upvotes+1,updated_at=? WHERE id=?", (now_ms(), iid))
    r = qry("SELECT upvotes FROM incidents WHERE id=?", (iid,), one=True)
    return ok({'upvotes': r['upvotes']})

@app.route('/api/incidents/<iid>/verify', methods=['POST'])
def verify_inc(iid):
    run("UPDATE incidents SET verified=1,updated_at=? WHERE id=?", (now_ms(), iid))
    return ok({'verified': True})

@app.route('/api/incidents/<iid>', methods=['DELETE'])
def delete_inc(iid):
    run("DELETE FROM incidents WHERE id=?", (iid,))
    return ok({'deleted': True})

# ── UPLOADS ──────────────────────────────────
@app.route('/api/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ── EMERGENCY SERVICES ───────────────────────
@app.route('/api/emergency-services', methods=['GET'])
def get_services():
    stype = request.args.get('type','all')
    lat   = request.args.get('lat', type=float)
    lng   = request.args.get('lng', type=float)
    sql   = "SELECT * FROM emergency_services"
    p     = []
    if stype and stype != 'all': sql += " WHERE type=?"; p.append(stype)
    rows = qry(sql, p)
    if lat and lng:
        for r in rows:
            r['distance_km'] = round(haversine(lat, lng, r['lat'], r['lng']), 2)
        rows.sort(key=lambda x: x.get('distance_km', 999))
    return ok(rows)

@app.route('/api/emergency-services', methods=['POST'])
def add_service():
    d = request.get_json(silent=True) or {}
    if not d.get('name') or not d.get('type'): return err('name and type required')
    sid = uid()
    run("INSERT INTO emergency_services (id,name,type,lat,lng,address,phone,hours,rating) VALUES (?,?,?,?,?,?,?,?,?)",
        (sid, d['name'], d['type'], float(d.get('lat',0)), float(d.get('lng',0)),
         d.get('address',''), d.get('phone',''), d.get('hours',''), float(d.get('rating',0))))
    return ok({'id': sid}), 201

# ── SOS CONTACTS ─────────────────────────────
@app.route('/api/sos-contacts', methods=['GET'])
def get_contacts():
    session = request.args.get('session', request.headers.get('X-Session','default'))
    return ok(qry("SELECT * FROM sos_contacts WHERE session_id=? ORDER BY created_at", (session,)))

@app.route('/api/sos-contacts', methods=['POST'])
def add_contact():
    d = request.get_json(silent=True) or {}
    if not d.get('name') or not d.get('phone'): return err('name and phone required')
    session = d.get('session', d.get('session_id', 'default'))
    cid = uid()
    run("INSERT INTO sos_contacts (id,session_id,name,phone,email,relationship,created_at) VALUES (?,?,?,?,?,?,?)",
        (cid, session, d['name'], d['phone'], d.get('email',''), d.get('relationship','other'), now_ms()))
    return ok({'id': cid, 'name': d['name'], 'phone': d['phone']}), 201

@app.route('/api/sos-contacts/<cid>', methods=['DELETE'])
def del_contact(cid):
    run("DELETE FROM sos_contacts WHERE id=?", (cid,))
    return ok({'deleted': True})

# ── SOS TRIGGER ──────────────────────────────
@app.route('/api/sos/trigger', methods=['POST'])
def trigger_sos():
    d = request.get_json(silent=True) or {}
    session = d.get('session', 'default')
    lat  = d.get('lat')
    lng  = d.get('lng')
    msg  = d.get('message', 'I need help — ResQ Emergency Alert!')
    cts  = qry("SELECT * FROM sos_contacts WHERE session_id=?", (session,))
    maps = f"https://maps.google.com/?q={lat},{lng}" if lat and lng else 'Location unavailable'

    eid = uid()
    run("INSERT INTO sos_events (id,session_id,lat,lng,message,contacts_notified,created_at) VALUES (?,?,?,?,?,?,?)",
        (eid, session, lat, lng, msg, len(cts), now_ms()))

    # In production: send via Twilio SMS/WhatsApp
    # Simulate dispatch
    dispatched = []
    for c in cts:
        dispatched.append({
            'contact':  c['name'],
            'phone':    c['phone'],
            'platform': 'SMS + WhatsApp',
            'message':  f"🚨 ResQ SOS from {c['name']}: {msg}\n📍 Location: {maps}",
            'status':   'dispatched'
        })
        print(f"📲 SOS → {c['name']} ({c['phone']}): {maps}")

    return ok({
        'event_id':          eid,
        'contacts_notified': len(cts),
        'dispatched':        dispatched,
        'maps_link':         maps,
        'emergency_numbers': {'police':'100','fire':'101','ambulance':'108','national':'112'},
    })

@app.route('/api/sos/events', methods=['GET'])
def get_sos_events():
    session = request.args.get('session','default')
    rows = qry("SELECT * FROM sos_events WHERE session_id=? ORDER BY created_at DESC LIMIT 10", (session,))
    return ok(rows)

# ── CHECK-INS ────────────────────────────────
@app.route('/api/checkins', methods=['GET'])
def get_checkins():
    session = request.args.get('session','default')
    rows = qry("SELECT * FROM checkins WHERE session_id=? ORDER BY created_at DESC LIMIT 20", (session,))
    return ok(rows)

@app.route('/api/checkins', methods=['POST'])
def create_checkin():
    d = request.get_json(silent=True) or {}
    if not d.get('timer_minutes'): return err('timer_minutes required')
    mins = int(d['timer_minutes'])
    t    = now_ms()
    cid  = uid()
    run("INSERT INTO checkins (id,session_id,user_name,lat,lng,timer_minutes,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (cid, d.get('session','default'), d.get('user_name','Anonymous'),
         d.get('lat'), d.get('lng'), mins, 'active', t, t + mins*60000))
    return ok({'id': cid, 'expires_at': t + mins*60000, 'timer_minutes': mins}), 201

@app.route('/api/checkins/<cid>/confirm', methods=['POST'])
def confirm_checkin(cid):
    run("UPDATE checkins SET status='confirmed',confirmed_at=? WHERE id=?", (now_ms(), cid))
    return ok({'status': 'confirmed', 'message': "You're safe — ResQ check-in confirmed!"})

@app.route('/api/checkins/<cid>/cancel', methods=['POST'])
def cancel_checkin(cid):
    run("UPDATE checkins SET status='cancelled' WHERE id=?", (cid,))
    return ok({'status': 'cancelled'})

@app.route('/api/checkins/<cid>', methods=['GET'])
def get_checkin(cid):
    r = qry("SELECT * FROM checkins WHERE id=?", (cid,), one=True)
    if not r: return err('Not found', 404)
    return ok(r)

# ── MISSING PERSONS ──────────────────────────
@app.route('/api/missing-persons', methods=['GET'])
def get_missing():
    status = request.args.get('status','missing')
    q      = (request.args.get('q') or '').strip()
    sql    = "SELECT id,name,age,gender,description,last_seen_location,last_seen_lat,last_seen_lng,last_seen_date,contact_name,contact_phone,status,views,tips_count,created_at,updated_at FROM missing_persons WHERE status=?"
    p      = [status]
    if q:
        sql += " AND (name LIKE ? OR last_seen_location LIKE ? OR description LIKE ?)"
        p   += [f'%{q}%', f'%{q}%', f'%{q}%']
    sql += " ORDER BY created_at DESC"
    rows = qry(sql, p)
    return ok(rows, total=len(rows))

@app.route('/api/missing-persons', methods=['POST'])
def create_missing():
    d = request.get_json(silent=True) or {}
    if request.files: d = request.form.to_dict()
    if not (d.get('name') or '').strip(): return err('name required')

    photo_path = None
    if request.files and 'photo' in request.files:
        f = request.files['photo']
        if f.filename:
            fname = uid() + '_' + f.filename.replace(' ','_')
            f.save(os.path.join(UPLOAD_DIR, fname))
            photo_path = '/api/uploads/' + fname

    pid = uid(); t = now_ms()
    run("""INSERT INTO missing_persons
        (id,name,age,gender,description,last_seen_location,last_seen_lat,last_seen_lng,
         last_seen_date,contact_name,contact_phone,photo_path,status,views,tips_count,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)""",
        (pid, d['name'].strip(),
         int(d['age']) if d.get('age') and str(d['age']).isdigit() else None,
         d.get('gender',''), (d.get('description') or '')[:3000],
         d.get('last_seen_location',''),
         float(d['last_seen_lat']) if d.get('last_seen_lat') else None,
         float(d['last_seen_lng']) if d.get('last_seen_lng') else None,
         d.get('last_seen_date',''),
         d.get('contact_name',''), d.get('contact_phone',''),
         photo_path, 'missing', t, t))
    return ok({'id': pid}), 201

@app.route('/api/missing-persons/<pid>', methods=['GET'])
def get_missing_one(pid):
    r = qry("SELECT * FROM missing_persons WHERE id=?", (pid,), one=True)
    if not r: return err('Not found', 404)
    run("UPDATE missing_persons SET views=views+1 WHERE id=?", (pid,))
    return ok(r)

@app.route('/api/missing-persons/<pid>/found', methods=['PATCH','POST'])
def mark_found(pid):
    run("UPDATE missing_persons SET status='found',updated_at=? WHERE id=?", (now_ms(), pid))
    return ok({'status': 'found'})

@app.route('/api/missing-persons/<pid>/tips', methods=['POST'])
def add_tip(pid):
    d = request.get_json(silent=True) or {}
    if not d.get('tip'): return err('tip text required')
    tid = uid()
    run("INSERT INTO missing_tips (id,person_id,tip,location,anonymous,contact_info,created_at) VALUES (?,?,?,?,?,?,?)",
        (tid, pid, d['tip'][:2000], d.get('location',''),
         1 if d.get('anonymous', True) else 0,
         d.get('contact_info',''), now_ms()))
    run("UPDATE missing_persons SET tips_count=tips_count+1 WHERE id=?", (pid,))
    return ok({'id': tid}), 201

@app.route('/api/missing-persons/<pid>/tips', methods=['GET'])
def get_tips(pid):
    return ok(qry("SELECT * FROM missing_tips WHERE person_id=? ORDER BY created_at DESC", (pid,)))

# ── SAFE ROUTES ──────────────────────────────
@app.route('/api/safe-routes', methods=['POST'])
def analyse_route():
    d = request.get_json(silent=True) or {}
    try:
        fLat = float(d['from_lat']); fLng = float(d['from_lng'])
        tLat = float(d['to_lat']);   tLng = float(d['to_lng'])
    except (KeyError, ValueError, TypeError):
        return err('from_lat, from_lng, to_lat, to_lng required as numbers')
    mode = d.get('mode','walking')

    # Sample multiple points along route for danger scoring
    cutoff = now_ms() - 12*3600000
    incidents = qry("SELECT lat,lng,severity,category,description,created_at FROM incidents WHERE created_at>?", (cutoff,))

    danger = 0.0
    near = []
    steps = 7
    for i in range(steps + 1):
        t_   = i / steps
        pLat = fLat + (tLat - fLat) * t_
        pLng = fLng + (tLng - fLng) * t_
        for inc in incidents:
            d_km = haversine(pLat, pLng, inc['lat'], inc['lng'])
            if d_km < 1.5:
                sev  = {'high':3,'medium':2,'low':1}.get(inc['severity'],1)
                age_h = (now_ms() - inc['created_at']) / 3600000
                decay = math.exp(-age_h / 6)
                danger += sev * math.exp(-d_km * 2) * decay / (steps + 1)
                if inc not in near:
                    near.append({**inc, 'distance_km': round(d_km, 2)})

    score    = max(0, min(100, 100 - danger * 18))
    dist_km  = haversine(fLat, fLng, tLat, tLng)
    speed    = {'walking':5,'cycling':15,'driving':40}.get(mode,5)
    eta_min  = round((dist_km / speed) * 60)
    rec      = ('Route appears safe based on ResQ community reports.' if score > 70
                else 'Some incidents reported nearby — stay on busy, well-lit streets.' if score > 40
                else 'Multiple safety incidents on this route. ResQ recommends an alternative path.')

    rid = uid()
    run("INSERT INTO route_history (id,session_id,from_address,from_lat,from_lng,to_address,to_lat,to_lng,mode,safety_score,incidents_nearby,distance_km,estimated_minutes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, d.get('session','default'), d.get('from_address',''), fLat, fLng,
         d.get('to_address',''), tLat, tLng, mode,
         round(score, 1), len(near), round(dist_km, 2), eta_min, now_ms()))

    return ok({
        'id':               rid,
        'safety_score':     round(score),
        'danger_score':     round(danger, 3),
        'incidents_nearby': len(near),
        'near_incidents':   near[:5],
        'recommendation':   rec,
        'distance_km':      round(dist_km, 2),
        'estimated_minutes':eta_min,
        'mode':             mode,
        'google_maps_url':  f"https://www.google.com/maps/dir/{fLat},{fLng}/{tLat},{tLng}/",
    })

@app.route('/api/safe-routes/history', methods=['GET'])
def route_history():
    session = request.args.get('session','default')
    rows = qry("SELECT * FROM route_history WHERE session_id=? ORDER BY created_at DESC LIMIT 10", (session,))
    return ok(rows)

# ── FRONTEND ──────────────────────────────────
@app.route('/')
def index():
    html_path = os.path.join(BASE_DIR, 'static', 'index.html')
    if os.path.exists(html_path):
        return send_file(html_path)
    return "<h1>ResQ Backend Running</h1><p>API: <a href='/api/health'>/api/health</a></p><p>Place index.html in the static/ folder</p>"

@app.route('/<path:p>')
def catch_all(p):
    fp = os.path.join(STATIC_DIR, p)
    if os.path.exists(fp):
        return send_file(fp)
    html_path = os.path.join(STATIC_DIR, 'index.html')
    if os.path.exists(html_path):
        return send_file(html_path)
    return '', 404

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
if __name__ == '__main__':
    seed()
    t = threading.Thread(target=expire_checkins_loop, daemon=True)
    t.start()
    print("\n" + "═"*52)
    print("  ResQ — Citizen Safety Platform")
    print("  Backend v2.0 — Flask + SQLite")
    print("═"*52)
    print(f"  Frontend : http://localhost:8000")
    print(f"  API Base : http://localhost:8000/api")
    print(f"  Health   : http://localhost:8000/api/health")
    print(f"  Database : {DB_PATH}")
    print("═"*52 + "\n")
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)
