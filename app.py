import os
import uuid
import json
import requests
import tempfile
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, send_from_directory, send_file
try:
    import firebase_admin
    from firebase_admin import credentials, auth, db, storage
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("Warning: Firebase admin SDK not available. Running in demo mode.")

import qrcode
import io

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Serve static files from 'static' folder
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

# Serve favicon.ico
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico')

# Initialize Firebase Admin SDK if available
FIREBASE_INITIALIZED = False
ref = None
bucket = None
if FIREBASE_AVAILABLE:
    try:
        service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
        if service_account_json:
            # Write service account JSON to a temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write(service_account_json)
                temp_path = f.name
            try:
                cred = credentials.Certificate(temp_path)
            finally:
                # Clean up the temporary file
                os.unlink(temp_path)
        elif os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
        else:
            print("Warning: No service account key found. Running in demo mode.")
            raise Exception("Service account key missing")
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': os.environ.get('FIREBASE_DATABASE_URL'),
            'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET') or f"{os.environ.get('FIREBASE_PROJECT_ID')}.appspot.com"
        })
        ref = db.reference()
        bucket = storage.bucket()
        FIREBASE_INITIALIZED = True
        print("Firebase Admin SDK initialized successfully")
    except Exception as e:
        print(f"Warning: Firebase initialization failed: {e}")
        print("Running in demo mode without Firebase.")
        FIREBASE_INITIALIZED = False
        ref = None
        bucket = None

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# ==================== AUTH ROUTES ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        if FIREBASE_AVAILABLE and FIREBASE_INITIALIZED:
            try:
                api_key = os.environ.get('FIREBASE_API_KEY')
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
                payload = {"email": email, "password": password, "returnSecureToken": True}
                response = requests.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    id_token = data['idToken']
                    decoded_token = auth.verify_id_token(id_token)
                    session['user'] = decoded_token['uid']
                    session['email'] = email
                    return redirect(url_for('dashboard'))
                else:
                    return render_template('login.html', error="Invalid email or password")
            except Exception as e:
                return render_template('login.html', error=str(e))
        else:
            session['user'] = 'demo-user-id'
            session['email'] = email
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

def get_dashboard_stats():
    """Fetch and return stats for dashboard"""
    stats = {
        'total_members': 0,
        'attendance_today': 0,
        'upcoming_events': 0,
        'active_groups': 0
    }
    
    if FIREBASE_INITIALIZED:
        try:
            members = ref.child('members').get()
            if members:
                stats['total_members'] = len(members)
            
            today = date.today().isoformat()
            attendance_today = ref.child('attendance').child(today).get()
            if attendance_today:
                stats['attendance_today'] = len(attendance_today)
            
            events = ref.child('events').get()
            if events:
                upcoming = [e for e in events.values() if e.get('date', '') >= today]
                stats['upcoming_events'] = len(upcoming)
            
            groups = ref.child('groups').get()
            if groups:
                stats['active_groups'] = len(groups)
        except Exception as e:
            print(f"Error fetching stats: {e}")
    
    return stats

@app.route('/api/stats')
def get_stats():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    stats = get_dashboard_stats()
    return jsonify(stats)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    stats = get_dashboard_stats()
    
    return render_template('dashboard.html',
        user=session.get('email'),
        stats=stats,
        firebase_api_key=os.environ.get('FIREBASE_API_KEY'),
        firebase_auth_domain=os.environ.get('FIREBASE_AUTH_DOMAIN'),
        firebase_database_url=os.environ.get('FIREBASE_DATABASE_URL'),
        firebase_project_id=os.environ.get('FIREBASE_PROJECT_ID'),
        firebase_storage_bucket=os.environ.get('FIREBASE_STORAGE_BUCKET'),
        firebase_messaging_sender_id=os.environ.get('FIREBASE_MESSAGING_SENDER_ID'),
        firebase_app_id=os.environ.get('FIREBASE_APP_ID')
    )

def format_member_id(member_id_value):
    """Ensure member ID is in CHURCH-MEM-XXX format"""
    if not member_id_value:
        return member_id_value
    # If already in correct format, return as-is
    if member_id_value.startswith('CHURCH-MEM-'):
        return member_id_value
    # If it has CHURCH-MEM without hyphen, add it
    if member_id_value.startswith('CHURCH-MEM'):
        return f"CHURCH-MEM-{member_id_value.replace('CHURCH-MEM', '').strip()}"
    # Otherwise, prepend the prefix
    return f"CHURCH-MEM-{member_id_value}"

@app.route('/api/members/<member_id>/qrcode')
def get_member_qrcode(member_id):
    """Generate QR code for member ID card"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # Get member data
    member = None
    if FIREBASE_INITIALIZED:
        try:
            member_data = ref.child('members').child(member_id).get()
            if member_data:
                member = {'id': member_id, **member_data}
        except Exception as e:
            print(f"Error fetching member: {e}")

    if not member:
        return jsonify({'error': 'Member not found'}), 404

    # Get member_id or generate CHURCH-MEM format
    raw_member_id = member.get('member_id', member_id)
    member_id_value = format_member_id(raw_member_id)

    # Generate QR code encoding member ID in CHURCH-MEM-XXX format
    qr_data = json.dumps({
        'member_id': member_id_value,
        'name': f"{member.get('first_name', '')} {member.get('last_name', '')}".strip(),
        'type': 'member_card'
    })

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    try:
        from qrcode.image.svg import SvgImage
        img = qr.make_image(image_factory=SvgImage)
        svg_content = img.to_string()
        return Response(svg_content, mimetype='image/svg+xml')
    except Exception as e:
        print(f'QR generation error: {e}')
        return jsonify({'error': 'Failed to generate QR code'}), 500

@app.route('/api/members/<member_id>/card')
def get_member_card(member_id):
    """Generate printable HTML card for member"""
    if 'user' not in session:
        return redirect(url_for('login'))

    member = None
    if FIREBASE_INITIALIZED:
        try:
            member_data = ref.child('members').child(member_id).get()
            if member_data:
                member = {'id': member_id, **member_data}
        except Exception as e:
            print(f"Error fetching member: {e}")

    if not member:
        return render_template('error.html', message='Member not found'), 404

    return render_template('member_card.html', member=member, user=session.get('email'))

# ==================== REVERSE SCAN ====================

@app.route('/api/scan-member', methods=['POST'])
def scan_member():
    """
    Reverse scan endpoint for admin to scan member ID cards.
    Unlike regular attendance scan, this does NOT check GPS - admin's location is trusted.
    """
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json()
    qr_data = data.get('qr_data')  # Expecting decoded JSON from QR code

    if not qr_data:
        return jsonify({'error': 'Missing QR data'}), 400

    try:
        qr = json.loads(qr_data) if isinstance(qr_data, str) else qr_data
    except Exception:
        return jsonify({'error': 'Invalid QR code format'}), 400

    member_id = qr.get('member_id')
    if not member_id:
        return jsonify({'error': 'Invalid member ID'}), 400

    # Verify member exists by searching for member_id field
    member = None
    member_key = None
    if FIREBASE_INITIALIZED:
        try:
            members = ref.child('members').get()
            if members:
                for key, mdata in members.items():
                    if mdata.get('member_id') == member_id:
                        member = {'id': key, **mdata}
                        member_key = key
                        break
        except Exception as e:
            print(f"Error fetching member: {e}")

    if not member:
        return jsonify({'error': 'Member not found'}), 404

    # Record attendance for current session (if available) or for today's date
    today = date.today().isoformat()
    service_type = 'sunday'  # Could be determined by service running

    if FIREBASE_INITIALIZED:
        try:
            # Check if there's an active session first
            active_session = None
            try:
                sessions = ref.child('sessions').get()
                if sessions:
                    # Find an active session (most recent)
                    for sid, sdata in sessions.items():
                        if sdata.get('active', False):
                            active_session = sid
                            break
            except Exception:
                pass

            # Record attendance under that session or directly under date
            if active_session:
                attendance_ref = ref.child('attendance').child(active_session).child(member_key)
                attendance_ref.set({
                    'timestamp': datetime.now().isoformat(),
                    'service_type': service_type,
                    'mode': 'admin_scan'
                })
            else:
                attendance_ref = ref.child('attendance').child(today).child(member_key)
                attendance_ref.set({
                    'timestamp': datetime.now().isoformat(),
                    'service_type': service_type,
                    'mode': 'admin_scan'
                })
        except Exception as e:
            print(f"Error recording attendance: {e}")

    member_name = f"{member.get('first_name', '')} {member.get('last_name', '')}".strip()
    return jsonify({
        'success': True,
        'member': {
            'id': member_id,
            'name': member_name,
            'status': member.get('status', 'active')
        }
    })

# ==================== MEMBER MANAGEMENT ====================

@app.route('/members')
def members_list():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    members = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('members').get()
            if data:
                members = [{'id': k, **v} for k, v in data.items()]
                members.sort(key=lambda x: (x.get('last_name', '').lower(), x.get('first_name', '').lower()))
        except Exception as e:
            print(f"Error fetching members: {e}")
    
    return render_template('members.html', members=members, user=session.get('email'))

# Global counter for generating CHURCH-MEM IDs
last_member_num = 0

def generate_member_id():
    """Generate a unique CHURCH-MEM-XXX format member ID"""
    global last_member_num
    if FIREBASE_INITIALIZED:
        try:
            # Find the highest numbered member
            members = ref.child('members').get()
            max_num = 0
            if members:
                for m in members.values():
                    mid = m.get('member_id', '')
                    if mid and mid.startswith('CHURCH-MEM-'):
                        try:
                            num = int(mid.replace('CHURCH-MEM-', ''))
                            max_num = max(max_num, num)
                        except ValueError:
                            pass
            last_member_num = max_num + 1
        except Exception:
            last_member_num += 1
    else:
        last_member_num += 1
    return f"CHURCH-MEM-{last_member_num:03d}"

@app.route('/api/members', methods=['POST'])
def add_member():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = str(uuid.uuid4())[:8]
    
    # Generate CHURCH-MEM format ID if not provided
    provided_member_id = data.get('memberId', '')
    if provided_member_id and provided_member_id.startswith('CHURCH-MEM-'):
        formatted_member_id = provided_member_id
    else:
        formatted_member_id = generate_member_id()
    
    member_data = {
        'id': member_id,
        'member_id': formatted_member_id,
        'first_name': data.get('firstName', ''),
        'last_name': data.get('lastName', ''),
        'email': data.get('email', ''),
        'phone': data.get('phone', ''),
        'date_of_birth': data.get('dateOfBirth', ''),
        'address': data.get('address', ''),
        'family_id': data.get('familyId', ''),
        'baptized': data.get('baptized', False),
        'join_date': data.get('joinDate', datetime.now().isoformat()),
        'status': 'active',
        'created_by': session.get('email', ''),
        'created_at': datetime.now().isoformat()
    }
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('members').child(member_id).set(member_data)
            return jsonify({'success': True, 'member_id': formatted_member_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/members', methods=['GET'])
def get_members():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    members = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('members').get()
            if data:
                members = [{'id': k, **v} for k, v in data.items()]
                members.sort(key=lambda x: (x.get('last_name', '').lower(), x.get('first_name', '').lower()))
        except Exception as e:
            print(f"Error fetching members: {e}")

    return jsonify({'members': members})

@app.route('/api/members/<member_id>', methods=['PUT'])
def update_member(member_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    if FIREBASE_INITIALIZED:
        try:
            ref.child('members').child(member_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/members/<member_id>', methods=['DELETE'])
def delete_member(member_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    if FIREBASE_INITIALIZED:
        try:
            # Get member data before deleting
            member_data = ref.child('members').child(member_id).get()
            if member_data:
                # Move to trash
                trash_item = {
                    'type': 'member',
                    'original_id': member_id,
                    'data': member_data,
                    'deleted_by': session.get('email', ''),
                    'deleted_at': datetime.now().isoformat()
                }
                trash_id = f"member_{member_id}_{int(datetime.now().timestamp())}"
                ref.child('trash').child(trash_id).set(trash_item)
                # Delete original
                ref.child('members').child(member_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/members/import', methods=['POST'])
def import_members():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # CSV import logic (simplified)
    try:
        import csv
        import io
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        imported = 0
        for row in reader:
            member_id = str(uuid.uuid4())[:8]
            member_data = {
                'id': member_id,
                'member_id': row.get('member_id', member_id),
                'first_name': row.get('first_name', ''),
                'last_name': row.get('last_name', ''),
                'email': row.get('email', ''),
                'phone': row.get('phone', ''),
                'status': 'active',
                'created_at': datetime.now().isoformat()
            }
            if FIREBASE_INITIALIZED:
                ref.child('members').child(member_id).set(member_data)
            imported += 1
        return jsonify({'success': True, 'imported': imported})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ATTENDANCE & REPORTS ====================

@app.route('/attendance')
def attendance_report():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Get date range from query params
    start = request.args.get('start', (date.today() - timedelta(days=30)).isoformat())
    end = request.args.get('end', date.today().isoformat())

    # Generate list of dates
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    records = []
    if FIREBASE_INITIALIZED:
        try:
            for d in dates:
                day_data = ref.child('attendance').child(d.isoformat()).get()
                if day_data:
                    for member_id, record in day_data.items():
                        records.append({
                            'date': d.isoformat(),
                            'member_id': member_id,
                            'timestamp': record.get('timestamp', ''),
                            'service_type': record.get('service_type', 'sunday')
                        })
        except Exception as e:
            print(f"Error fetching attendance: {e}")

    return render_template('attendance.html', records=records, start=start, end=end, user=session.get('email'))

@app.route('/api/attendance/records')
def get_attendance_records():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    start = request.args.get('start', (date.today() - timedelta(days=30)).isoformat())
    end = request.args.get('end', date.today().isoformat())

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    records = []
    if FIREBASE_INITIALIZED:
        try:
            for d in dates:
                day_data = ref.child('attendance').child(d.isoformat()).get()
                if day_data:
                    for member_id, record in day_data.items():
                        records.append({
                            'date': d.isoformat(),
                            'member_id': member_id,
                            'timestamp': record.get('timestamp', ''),
                            'service_type': record.get('service_type', 'sunday')
                        })
        except Exception as e:
            print(f"Error fetching attendance: {e}")

    return jsonify({'records': records})

@app.route('/api/attendance/record', methods=['POST'])
def record_attendance():
    """Record attendance for a member (via QR scan or manual entry)"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = data.get('member_id')
    service_type = data.get('service_type', 'sunday')
    today = date.today().isoformat()
    
    if not member_id:
        return jsonify({'error': 'member_id is required'}), 400
    
    if FIREBASE_INITIALIZED:
        try:
            attendance_ref = ref.child('attendance').child(today).child(member_id)
            attendance_ref.set({
                'timestamp': datetime.now().isoformat(),
                'service_type': service_type
            })
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/attendance/stats')
def attendance_stats():
    """Get attendance statistics for charts"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    stats = {
        'last_7_days': [],
        'by_service_type': {},
        'member_frequency': []
    }
    
    if FIREBASE_INITIALIZED:
        try:
            # Last 7 days
            for i in range(7):
                d = date.today() - timedelta(days=i)
                day_data = ref.child('attendance').child(d.strftime('%Y-%m-%d')).get()
                count = len(day_data) if day_data else 0
                stats['last_7_days'].append({'date': d.strftime('%Y-%m-%d'), 'count': count})
            
            stats['last_7_days'].reverse()
            
            # Service type breakdown (last 30 days)
            for i in range(30):
                d = date.today() - timedelta(days=i)
                day_data = ref.child('attendance').child(d.strftime('%Y-%m-%d')).get()
                if day_data:
                    for record in day_data.values():
                        service = record.get('service_type', 'unknown')
                        stats['by_service_type'][service] = stats['by_service_type'].get(service, 0) + 1
        except Exception as e:
            print(f"Error: {e}")
    
    return jsonify(stats)

# ==================== EVENTS ====================

@app.route('/events')
def events_list():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    events = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('events').get()
            if data:
                events = [{'id': k, **v} for k, v in data.items()]
                events.sort(key=lambda x: x.get('date', ''), reverse=True)
        except Exception as e:
            print(f"Error fetching events: {e}")
    
    return render_template('events.html', events=events, user=session.get('email'))

@app.route('/api/events', methods=['POST'])
def create_event():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    event_id = str(uuid.uuid4())[:8]
    
    event_data = {
        'id': event_id,
        'title': data.get('title', ''),
        'description': data.get('description', ''),
        'date': data.get('date', ''),
        'time': data.get('time', ''),
        'location': data.get('location', ''),
        'type': data.get('type', 'service'),
        'created_by': session.get('email', ''),
        'created_at': datetime.now().isoformat(),
        'notifications_sent': False
    }
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('events').child(event_id).set(event_data)
            return jsonify({'success': True, 'event_id': event_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/events', methods=['GET'])
def get_events():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    events = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('events').get()
            if data:
                events = [{'id': k, **v} for k, v in data.items()]
                events.sort(key=lambda x: x.get('date', ''), reverse=True)
        except Exception as e:
            print(f"Error fetching events: {e}")

    return jsonify({'events': events})

@app.route('/api/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if FIREBASE_INITIALIZED:
        try:
            ref.child('events').child(event_id).update(data)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    if FIREBASE_INITIALIZED:
        try:
            # Get event data before deleting
            event_data = ref.child('events').child(event_id).get()
            if event_data:
                # Move to trash
                trash_item = {
                    'type': 'event',
                    'original_id': event_id,
                    'data': event_data,
                    'deleted_by': session.get('email', ''),
                    'deleted_at': datetime.now().isoformat()
                }
                trash_id = f"event_{event_id}_{int(datetime.now().timestamp())}"
                ref.child('trash').child(trash_id).set(trash_item)
                # Delete original
                ref.child('events').child(event_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

# ==================== SMALL GROUPS ====================

@app.route('/groups')
def groups_list():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    groups = []
    members_map = {}
    if FIREBASE_INITIALIZED:
        try:
            g = ref.child('groups').get()
            if g:
                groups = [{'id': k, **v} for k, v in g.items()]
            
            m = ref.child('members').get()
            if m:
                members_map = m
        except Exception as e:
            print(f"Error: {e}")
    
    return render_template('groups.html', groups=groups, members=members_map, user=session.get('email'))

@app.route('/api/groups', methods=['POST'])
def create_group():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    group_id = str(uuid.uuid4())[:8]
    
    group_data = {
        'id': group_id,
        'name': data.get('name', ''),
        'description': data.get('description', ''),
        'category': data.get('category', ''),
        'leader_id': data.get('leaderId', ''),
        'meeting_day': data.get('meetingDay', ''),
        'meeting_time': data.get('meetingTime', ''),
        'created_by': session.get('email', ''),
        'created_at': datetime.now().isoformat()
    }
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('groups').child(group_id).set(group_data)
            return jsonify({'success': True, 'group_id': group_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/groups/<group_id>/members', methods=['POST'])
def add_group_member(group_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = data.get('member_id')
    
    if FIREBASE_INITIALIZED:
        try:
            # Add to group members list
            ref.child('groups').child(group_id).child('members').child(member_id).set({
                'added_at': datetime.now().isoformat()
            })
            # Also add group to member's record
            ref.child('members').child(member_id).child('groups').child(group_id).set(True)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/groups/<group_id>/members/<member_id>', methods=['DELETE'])
def remove_group_member(group_id, member_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if FIREBASE_INITIALIZED:
        try:
            ref.child('groups').child(group_id).child('members').child(member_id).delete()
            ref.child('members').child(member_id).child('groups').child(group_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/groups/<group_id>', methods=['DELETE'])
def delete_group(group_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    if FIREBASE_INITIALIZED:
        try:
            # Get group data before deleting
            group_data = ref.child('groups').child(group_id).get()
            if group_data:
                # Move to trash
                trash_item = {
                    'type': 'group',
                    'original_id': group_id,
                    'data': group_data,
                    'deleted_by': session.get('email', ''),
                    'deleted_at': datetime.now().isoformat()
                }
                trash_id = f"group_{group_id}_{int(datetime.now().timestamp())}"
                ref.child('trash').child(trash_id).set(trash_item)
                # Delete original
                ref.child('groups').child(group_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

# ==================== DONATIONS ====================

@app.route('/donations')
def donations_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    donations = []
    summary = {'total': 0, 'count': 0}
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('donations').get()
            if data:
                donations = [{'id': k, **v} for k, v in data.items()]
                donations.sort(key=lambda x: x.get('date', ''), reverse=True)
                summary['total'] = sum(d.get('amount', 0) for d in donations)
                summary['count'] = len(donations)
        except Exception as e:
            print(f"Error: {e}")
    
    return render_template('donations.html', donations=donations, summary=summary, user=session.get('email'))

@app.route('/api/donations', methods=['POST'])
def record_donation():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    donation_id = str(uuid.uuid4())[:8]
    
    amount = float(data.get('amount', 0))
    if amount <= 0:
        return jsonify({'error': 'Amount must be greater than 0'}), 400
    
    donation_data = {
        'id': donation_id,
        'member_id': data.get('member_id', ''),
        'amount': amount,
        'type': data.get('type', 'tithe'),
        'method': data.get('method', 'cash'),
        'date': data.get('date', date.today().isoformat()),
        'notes': data.get('notes', ''),
        'recorded_by': session.get('email', ''),
        'created_at': datetime.now().isoformat()
    }
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('donations').child(donation_id).set(donation_data)
            return jsonify({'success': True, 'donation_id': donation_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/donations', methods=['GET'])
def get_donations():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    donations = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('donations').get()
            if data:
                donations = [{'id': k, **v} for k, v in data.items()]
                donations.sort(key=lambda x: x.get('date', ''), reverse=True)
        except Exception as e:
            print(f"Error fetching donations: {e}")

    return jsonify({'donations': donations})

@app.route('/api/donations/export')
def export_donations():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Export as CSV
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Member ID', 'Amount', 'Type', 'Method', 'Notes'])
    
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('donations').get()
            if data:
                for d in data.values():
                    writer.writerow([
                        d.get('date', ''),
                        d.get('member_id', ''),
                        d.get('amount', 0),
                        d.get('type', ''),
                        d.get('method', ''),
                        d.get('notes', '')
                    ])
        except Exception as e:
            print(f"Error: {e}")
    
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition': f'attachment; filename=donations_{date.today()}.csv'
    })

@app.route('/api/donations/<donation_id>', methods=['DELETE'])
def delete_donation(donation_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    if FIREBASE_INITIALIZED:
        try:
            # Get donation data before deleting
            donation_data = ref.child('donations').child(donation_id).get()
            if donation_data:
                # Move to trash
                trash_item = {
                    'type': 'donation',
                    'original_id': donation_id,
                    'data': donation_data,
                    'deleted_by': session.get('email', ''),
                    'deleted_at': datetime.now().isoformat()
                }
                trash_id = f"donation_{donation_id}_{int(datetime.now().timestamp())}"
                ref.child('trash').child(trash_id).set(trash_item)
                # Delete original
                ref.child('donations').child(donation_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

# ==================== SERMONS ====================

@app.route('/sermons')
def sermons_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    sermons = []
    today_str = date.today().isoformat()
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('sermons').get()
            if data:
                sermons = [{'id': k, **v} for k, v in data.items()]
                sermons.sort(key=lambda x: x.get('date', ''), reverse=True)
        except Exception as e:
            print(f"Error fetching sermons: {e}")
    
    return render_template('sermons.html', sermons=sermons, user=session.get('email'), date=today_str)

# ==================== COMMUNICATIONS ====================

@app.route('/communications')
def communications_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    announcements = []
    prayer_requests = []
    
    if FIREBASE_INITIALIZED:
        try:
            a = ref.child('announcements').get()
            if a:
                announcements = [{'id': k, **v} for k, v in a.items()]
                announcements.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            p = ref.child('prayer_requests').get()
            if p:
                prayer_requests = [{'id': k, **v} for k, v in p.items()]
                prayer_requests.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        except Exception as e:
            print(f"Error: {e}")
    
    return render_template('communications.html', announcements=announcements, prayer_requests=prayer_requests, user=session.get('email'))

@app.route('/api/announcements', methods=['POST'])
def create_announcement():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    ann_id = str(uuid.uuid4())[:8]
    
    announcement = {
        'id': ann_id,
        'title': data.get('title', ''),
        'content': data.get('content', ''),
        'target': data.get('target', 'all'),
        'priority': data.get('priority', 'normal'),
        'created_by': session.get('email', ''),
        'created_at': datetime.now().isoformat(),
        'sent': False
    }
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('announcements').child(ann_id).set(announcement)
            return jsonify({'success': True, 'id': ann_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/announcements', methods=['GET'])
def get_announcements():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    announcements = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('announcements').get()
            if data:
                announcements = [{'id': k, **v} for k, v in data.items()]
                announcements.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        except Exception as e:
            print(f"Error: {e}")

    return jsonify({'announcements': announcements})

@app.route('/api/announcements/<ann_id>', methods=['DELETE'])
def delete_announcement(ann_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    if FIREBASE_INITIALIZED:
        try:
            # Get announcement data before deleting
            ann_data = ref.child('announcements').child(ann_id).get()
            if ann_data:
                # Move to trash
                trash_item = {
                    'type': 'announcement',
                    'original_id': ann_id,
                    'data': ann_data,
                    'deleted_by': session.get('email', ''),
                    'deleted_at': datetime.now().isoformat()
                }
                trash_id = f"announcement_{ann_id}_{int(datetime.now().timestamp())}"
                ref.child('trash').child(trash_id).set(trash_item)
                # Delete original
                ref.child('announcements').child(ann_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/prayer-requests', methods=['GET'])
def get_prayer_requests():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    prayer_requests = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('prayer_requests').get()
            if data:
                prayer_requests = [{'id': k, **v} for k, v in data.items()]
                prayer_requests.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        except Exception as e:
            print(f"Error: {e}")

    return jsonify({'prayer_requests': prayer_requests})

@app.route('/api/prayer-requests', methods=['POST'])
def submit_prayer_request():
    data = request.get_json()
    req_id = str(uuid.uuid4())[:8]
    
    prayer_data = {
        'id': req_id,
        'name': data.get('name', 'Anonymous'),
        'email': data.get('email', ''),
        'request': data.get('request', ''),
        'urgent': data.get('urgent', False),
        'created_at': datetime.now().isoformat(),
        'status': 'new'
    }
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('prayer_requests').child(req_id).set(prayer_data)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

# ==================== MEMBER CARDS ====================

@app.route('/member-cards')
def member_cards():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    members = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('members').get()
            if data:
                members = [{'id': k, **v} for k, v in data.items()]
                # Sort by last_name then first_name
                members.sort(key=lambda x: (x.get('last_name', '').lower(), x.get('first_name', '').lower()))
        except Exception as e:
            print(f"Error fetching members: {e}")
    
    return render_template('member_cards.html', members=members, user=session.get('email'))

# ==================== VOLUNTEER SCHEDULING ====================

@app.route('/volunteers')
def volunteers_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    schedules = []
    roles = ['Usher', 'Worship Leader', 'Sound Tech', 'Children\'s Church', 'Greeter']
    
    if FIREBASE_INITIALIZED:
        try:
            s = ref.child('schedules').get()
            if s:
                schedules = [{'id': k, **v} for k, v in s.items()]
        except Exception as e:
            print(f"Error: {e}")
    
    return render_template('volunteers.html', schedules=schedules, roles=roles, user=session.get('email'))

@app.route('/api/volunteers/schedule', methods=['POST'])
def create_schedule():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    schedule_id = str(uuid.uuid4())[:8]

    schedule_data = {
        'id': schedule_id,
        'role': data.get('role', ''),
        'date': data.get('date', ''),
        'time': data.get('time', ''),
        'assigned_to': data.get('member_id', ''),
        'status': 'scheduled',
        'created_by': session.get('email', ''),
        'created_at': datetime.now().isoformat()
    }

    if FIREBASE_INITIALIZED:
        try:
            ref.child('schedules').child(schedule_id).set(schedule_data)
            return jsonify({'success': True, 'schedule_id': schedule_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/volunteers/schedule', methods=['GET'])
def get_schedules():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    schedules = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('schedules').get()
            if data:
                schedules = [{'id': k, **v} for k, v in data.items()]
                schedules.sort(key=lambda x: x.get('date', ''), reverse=True)
        except Exception as e:
            print(f"Error fetching schedules: {e}")

    return jsonify({'schedules': schedules})

@app.route('/api/volunteers/schedule/<schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if FIREBASE_INITIALIZED:
        try:
            update_data = {
                'role': data.get('role'),
                'date': data.get('date'),
                'time': data.get('time'),
                'assigned_to': data.get('member_id')
            }
            # Remove None values
            update_data = {k: v for k, v in update_data.items() if v is not None}
            ref.child('schedules').child(schedule_id).update(update_data)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/volunteers/schedule/<schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    if FIREBASE_INITIALIZED:
        try:
            # Get schedule data before deleting
            schedule_data = ref.child('schedules').child(schedule_id).get()
            if schedule_data:
                # Move to trash
                trash_item = {
                    'type': 'schedule',
                    'original_id': schedule_id,
                    'data': schedule_data,
                    'deleted_by': session.get('email', ''),
                    'deleted_at': datetime.now().isoformat()
                }
                trash_id = f"schedule_{schedule_id}_{int(datetime.now().timestamp())}"
                ref.child('trash').child(trash_id).set(trash_item)
                # Delete original
                ref.child('schedules').child(schedule_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

# ==================== RESOURCE MANAGEMENT ====================

@app.route('/resources')
def resources_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    inventory = []
    bookings = []
    
    if FIREBASE_INITIALIZED:
        try:
            inv = ref.child('inventory').get()
            if inv:
                inventory = [{'id': k, **v} for k, v in inv.items()]
            
            b = ref.child('bookings').get()
            if b:
                bookings = [{'id': k, **v} for k, v in b.items()]
        except Exception as e:
            print(f"Error: {e}")
    
    # Compute stats for the template
    stats = {
        'total_inventory': len(inventory),
        'low_stock': sum(1 for item in inventory if item.get('quantity', 0) <= item.get('min_quantity', 0)),
        'active_bookings': len(bookings)
    }
    
    return render_template('resources.html', inventory=inventory, bookings=bookings, stats=stats, user=session.get('email'))

@app.route('/api/inventory', methods=['POST'])
def add_inventory():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    item_id = str(uuid.uuid4())[:8]
    
    item_data = {
        'id': item_id,
        'name': data.get('name', ''),
        'category': data.get('category', ''),
        'quantity': int(data.get('quantity', 0)),
        'min_quantity': int(data.get('minQuantity', 0)),
        'location': data.get('location', ''),
        'last_updated': datetime.now().isoformat()
    }
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('inventory').child(item_id).set(item_data)
            return jsonify({'success': True, 'item_id': item_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Firebase not initialized'}), 503

# ==================== BIBLE TOOLS ROUTES ====================

@app.route('/bible')
def bible_reader():
    if 'user' not in session:
        return redirect(url_for('login'))
    stats = get_dashboard_stats()
    return render_template('dashboard.html',
        user=session.get('email'),
        stats=stats,
        firebase_api_key=os.environ.get('FIREBASE_API_KEY'),
        firebase_auth_domain=os.environ.get('FIREBASE_AUTH_DOMAIN'),
        firebase_database_url=os.environ.get('FIREBASE_DATABASE_URL'),
        firebase_project_id=os.environ.get('FIREBASE_PROJECT_ID'),
        firebase_storage_bucket=os.environ.get('FIREBASE_STORAGE_BUCKET'),
        firebase_messaging_sender_id=os.environ.get('FIREBASE_MESSAGING_SENDER_ID'),
        firebase_app_id=os.environ.get('FIREBASE_APP_ID')
    )

@app.route('/notes')
def notes():
    return redirect(url_for('bible_reader'))

@app.route('/history')
def history():
    return redirect(url_for('bible_reader'))

@app.route('/bookmarks')
def bookmarks():
    return redirect(url_for('bible_reader'))

@app.route('/highlights')
def highlights():
    return redirect(url_for('bible_reader'))

@app.route('/search')
def search():
    return redirect(url_for('bible_reader'))

@app.route('/service-update')
def service_update():
    return redirect(url_for('bible_reader'))

# ==================== QR & ATTENDANCE ====================

@app.route('/start_service', methods=['POST'])
def start_service():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if not FIREBASE_INITIALIZED:
        return jsonify({'error': 'Firebase not initialized'}), 503

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}
    session_id = str(uuid.uuid4())
    proximity_limit = 3
    latitude = data.get('latitude', 0)
    longitude = data.get('longitude', 0)

    try:
        session_data = {
            'session_id': session_id,
            'latitude': latitude,
            'longitude': longitude,
            'limit': proximity_limit,
            'timestamp': datetime.now().isoformat(),
            'created_by': session['user'],
            'active': True
        }
        ref.child('sessions').child(session_id).set(session_data)
    except Exception as e:
        return jsonify({'error': f'Failed to create session: {str(e)}'}), 500
    from urllib.parse import quote
    base_url = request.url_root.rstrip('/')
    qr_url = f"{base_url}/scan?sid={session_id}&limit={proximity_limit}"
    
    # Generate QR code with the scan URL
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(qr_url)
    qr.make(fit=True)

    try:
        from qrcode.image.svg import SvgImage
        img = qr.make_image(image_factory=SvgImage)
        svg_content = img.to_string()
        return Response(svg_content, mimetype='image/svg+xml')
    except Exception as e:
        print(f'QR generation error: {e}')
        return jsonify({'error': 'Failed to generate QR code'}), 500

@app.route('/scan')
def member_scan_page():
    """Page members see when scanning the service QR code"""
    session_id = request.args.get('sid')
    limit = request.args.get('limit', '3')
    
    return render_template('member_scan.html', 
        session_id=session_id, 
        limit=limit)

@app.route('/api/attendance/scan', methods=['POST'])
def scan_attendance():
    data = request.get_json()
    session_id = data.get('session_id')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    member_name = data.get('name')
    member_type = data.get('member_type', 'Member')

    if not session_id or latitude is None or longitude is None:
        return jsonify({'error': 'Missing required fields'}), 400

    session_data = None
    if FIREBASE_INITIALIZED:
        try:
            session_data = ref.child('sessions').child(session_id).get()
            if not session_data:
                return jsonify({'error': 'Invalid session'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    if not session_data:
        return jsonify({'error': 'Session not found'}), 404

    import math
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    distance = haversine(latitude, longitude, session_data.get('latitude', 0), session_data.get('longitude', 0))
    limit = session_data.get('limit', 3)

    if distance > limit:
        return jsonify({'error': f'Too far! Please move closer to the Admin. (Distance: {distance:.1f}m)'}), 403

    if FIREBASE_INITIALIZED:
        try:
            checkin_id = str(uuid.uuid4())[:8]
            checkin_data = {
                'id': checkin_id,
                'session_id': session_id,
                'member_name': member_name,
                'member_type': member_type,
                'distance': round(distance, 1),
                'timestamp': datetime.now().isoformat(),
                'latitude': latitude,
                'longitude': longitude
            }
            ref.child('checkins').child(checkin_id).set(checkin_data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'success': True, 'message': f'Check-in successful! Distance: {distance:.1f}m'})

@app.route('/publish_service', methods=['POST'])
def publish_service():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        data = request.get_json()
        required_fields = ['occasion', 'date', 'theme']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        service_data = {
            'occasion': data.get('occasion', ''),
            'date': data.get('date', ''),
            'theme': data.get('theme', ''),
            'pastor': data.get('pastor', ''),
            'order_of_service': data.get('order', []),
            'presbyters_on_duty': data.get('presbyters', ''),
            'weekly_meetings': data.get('meetings', ''),
            'bible_text_week': data.get('bibleTextWeek', ''),
            'updated_at': data.get('updatedAt', datetime.now().isoformat()),
            'updated_by': session.get('email', 'unknown')
        }
        
        if FIREBASE_INITIALIZED:
            try:
                ref.child('weekly_service').child('current').set(service_data)
                print(f"Service update written by {session.get('email')}")
            except Exception as e:
                print(f"Firebase write error: {e}")
                return jsonify({'error': 'Failed to write to database'}), 500
        else:
            return jsonify({'error': 'Firebase not initialized'}), 503

        return jsonify({'success': True, 'message': 'Service update published'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Admin emails (comma-separated list in environment variable)
ADMIN_EMAILS = os.environ.get('ADMIN_EMAILS', '').split(',')
ADMIN_EMAILS = [e.strip() for e in ADMIN_EMAILS if e.strip()]

def is_admin():
    """Check if current user is an admin"""
    if 'user' not in session:
        return False
    email = session.get('email')
    return email in ADMIN_EMAILS

@app.route('/api/notifications/send', methods=['POST'])
def send_notification():
    """Send push notification to members (admin only)"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json()
    title = data.get('title', '')
    body = data.get('body', '')
    target = data.get('target', 'all')  # all, members, groups
    
    if FIREBASE_INITIALIZED:
        try:
            # Store notification for mobile app to pick up
            notif_id = str(uuid.uuid4())[:8]
            ref.child('notifications').child(notif_id).set({
                'title': title,
                'body': body,
                'target': target,
                'sent_at': datetime.now().isoformat(),
                'sent_by': session.get('email'),
                'delivered': False
            })
            return jsonify({'success': True, 'notification_id': notif_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/sermons', methods=['POST'])
def add_sermon():
    """Add new sermon (admin only)"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json()
    sermon_id = str(uuid.uuid4())[:8]
    
    sermon_data = {
        'id': sermon_id,
        'title': data.get('title', ''),
        'speaker': data.get('speaker', ''),
        'date': data.get('date', date.today().isoformat()),
        'scripture': data.get('scripture', ''),
        'audio_url': data.get('audio_url', ''),
        'video_url': data.get('video_url', ''),
        'notes': data.get('notes', ''),
        'created_by': session.get('email'),
        'created_at': datetime.now().isoformat()
    }
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('sermons').child(sermon_id).set(sermon_data)
            return jsonify({'success': True, 'sermon_id': sermon_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/sermons', methods=['GET'])
def get_sermons():
    """Get sermon library"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    sermons = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('sermons').get()
            if data:
                sermons = [{'id': k, **v} for k, v in data.items()]
                sermons.sort(key=lambda x: x.get('date', ''), reverse=True)
        except Exception as e:
            print(f"Sermons fetch error: {e}")
    
    return jsonify({'sermons': sermons})

@app.route('/api/sermons/upload', methods=['POST'])
def upload_sermon():
    """Upload sermon recording (audio/video) - admin only"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    
    # Check if file is present
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Get metadata from form data
    title = request.form.get('title', '')
    speaker = request.form.get('speaker', '')
    date_str = request.form.get('date', date.today().isoformat())
    scripture = request.form.get('scripture', '')
    notes = request.form.get('notes', '')
    
    sermon_id = str(uuid.uuid4())[:8]
    
    # Determine file type
    file_ext = os.path.splitext(file.filename)[1].lower()
    allowed_audio = ['.mp3', '.wav', '.m4a', '.ogg', '.aac']
    allowed_video = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
    
    file_type = 'audio' if file_ext in allowed_audio else 'video' if file_ext in allowed_video else 'other'
    
    if file_type == 'other':
        return jsonify({'error': f'Unsupported file type: {file_ext}'}), 400
    
    # Prepare sermon data
    sermon_data = {
        'id': sermon_id,
        'title': title,
        'speaker': speaker,
        'date': date_str,
        'scripture': scripture,
        'notes': notes,
        'file_type': file_type,
        'file_original_name': file.filename,
        'created_by': session.get('email'),
        'created_at': datetime.now().isoformat()
    }
    
    # Upload file to Firebase Storage if available
    file_url = ''
    if FIREBASE_INITIALIZED and bucket:
        try:
            # Create storage path: sermons/YYYY-MM-DD/sermon_id_filename
            storage_path = f"sermons/{date_str}/{sermon_id}_{file.filename}"
            blob = bucket.blob(storage_path)

            # Upload file
            file.seek(0)  # Reset file pointer
            blob.upload_from_file(file, content_type=file.content_type)

            # Make publicly readable
            blob.make_public()
            file_url = blob.public_url

            sermon_data['file_url'] = file_url
            sermon_data['storage_path'] = storage_path

            print(f"Sermon file uploaded to: {storage_path}")
        except Exception as e:
            print(f"Storage upload error: {e}")
            return jsonify({'error': f'Failed to upload file: {str(e)}'}), 500
    else:
        return jsonify({'error': 'Storage not available'}), 500

    # Save sermon metadata to Realtime Database
    if not FIREBASE_INITIALIZED:
        return jsonify({'error': 'Firebase not initialized'}), 503
    try:
        ref.child('sermons').child(sermon_id).set(sermon_data)
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({'error': 'Failed to save sermon metadata'}), 500

    return jsonify({
        'success': True,
        'sermon_id': sermon_id,
        'file_url': file_url,
        'message': 'Sermon uploaded successfully'
    })

@app.route('/api/sermons/<sermon_id>', methods=['DELETE'], endpoint='delete_sermon_api')
def delete_sermon(sermon_id):
    """Delete sermon - admin only (soft delete to trash)"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    if FIREBASE_INITIALIZED:
        try:
            # Get sermon data first
            sermon_data = ref.child('sermons').child(sermon_id).get()
            if sermon_data:
                # Move to trash (keep storage_path for later)
                trash_item = {
                    'type': 'sermon',
                    'original_id': sermon_id,
                    'data': sermon_data,
                    'deleted_by': session.get('email', ''),
                    'deleted_at': datetime.now().isoformat()
                }
                trash_id = f"sermon_{sermon_id}_{int(datetime.now().timestamp())}"
                ref.child('trash').child(trash_id).set(trash_item)

                # Delete record from database
                ref.child('sermons').child(sermon_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/sermons/<sermon_id>', methods=['GET'])
def get_sermon(sermon_id):
    """Get single sermon details"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if FIREBASE_INITIALIZED:
        try:
            sermon_data = ref.child('sermons').child(sermon_id).get()
            if sermon_data:
                return jsonify({'sermon': {'id': sermon_id, **sermon_data}})
        except Exception as e:
            print(f"Sermon fetch error: {e}")
    
    return jsonify({'error': 'Sermon not found'}), 404

# ==================== TRASH / RECYCLE BIN ====================

@app.route('/api/trash', methods=['GET'])
def get_trash():
    """List all deleted items in trash"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    trash_items = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('trash').get()
            if data:
                trash_items = [{'id': k, **v} for k, v in data.items()]
                trash_items.sort(key=lambda x: x.get('deleted_at', ''), reverse=True)
        except Exception as e:
            print(f"Error fetching trash: {e}")

    return jsonify({'trash': trash_items})

@app.route('/api/trash/restore/<item_id>', methods=['POST'])
def restore_trash_item(item_id):
    """Restore a deleted item from trash"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if FIREBASE_INITIALIZED:
        try:
            # Get trash item
            trash_item = ref.child('trash').child(item_id).get()
            if not trash_item:
                return jsonify({'error': 'Item not found in trash'}), 404

            item_type = trash_item.get('type')
            original_id = trash_item.get('original_id')
            original_data = trash_item.get('data', {})

            # Restore to original collection
            if item_type == 'member':
                ref.child('members').child(original_id).set(original_data)
            elif item_type == 'event':
                ref.child('events').child(original_id).set(original_data)
            elif item_type == 'announcement':
                ref.child('announcements').child(original_id).set(original_data)
            elif item_type == 'donation':
                ref.child('donations').child(original_id).set(original_data)
            elif item_type == 'schedule':
                ref.child('schedules').child(original_id).set(original_data)
            elif item_type == 'group':
                ref.child('groups').child(original_id).set(original_data)
            elif item_type == 'sermon':
                ref.child('sermons').child(original_id).set(original_data)
            else:
                return jsonify({'error': f'Unknown item type: {item_type}'}), 400

            # Remove from trash
            ref.child('trash').child(item_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/trash/purge/<item_id>', methods=['DELETE'])
def purge_trash_item(item_id):
    """Permanently delete an item from trash"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if FIREBASE_INITIALIZED:
        try:
            # Get trash item first to check for associated files
            trash_item = ref.child('trash').child(item_id).get()
            if trash_item and 'data' in trash_item:
                # If it's a sermon, delete the associated file from storage
                if trash_item.get('type') == 'sermon':
                    storage_path = trash_item['data'].get('storage_path')
                    if storage_path and bucket:
                        try:
                            blob = bucket.blob(storage_path)
                            blob.delete()
                            print(f"Purged sermon file: {storage_path}")
                        except Exception as e:
                            print(f"Warning: Could not delete sermon file: {e}")

            # Delete from trash
            ref.child('trash').child(item_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/api/trash/clear-all', methods=['DELETE'])
def clear_all_trash():
    """Permanently delete all items from trash"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if FIREBASE_INITIALIZED:
        try:
            # Get all trash items first to handle file cleanup
            trash_data = ref.child('trash').get()
            if trash_data:
                for trash_id, trash_item in trash_data.items():
                    # If it's a sermon, delete the associated file from storage
                    if trash_item.get('type') == 'sermon':
                        storage_path = trash_item.get('data', {}).get('storage_path')
                        if storage_path and bucket:
                            try:
                                blob = bucket.blob(storage_path)
                                blob.delete()
                                print(f"Purged sermon file: {storage_path}")
                            except Exception as e:
                                print(f"Warning: Could not delete sermon file: {e}")

                # Clear entire trash collection
                ref.child('trash').delete()
                return jsonify({'success': True, 'purged_count': len(trash_data)})
            return jsonify({'success': True, 'purged_count': 0})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Firebase not initialized'}), 503

@app.route('/trash')
def trash_page():
    if 'user' not in session:
        return redirect(url_for('login'))

    return render_template('trash.html', user=session.get('email'))

# ==================== ANALYTICS ====================
def get_analytics():
    """Get analytics data for dashboard"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    analytics = {
        'attendance_trends': [],
        'giving_summary': {'total': 0, 'by_type': {}},
        'membership_growth': []
    }
    
    if FIREBASE_INITIALIZED:
        try:
            # Attendance trends (last 30 days)
            attendance_data = []
            for i in range(30):
                d = date.today() - timedelta(days=i)
                day_str = d.isoformat()
                day_data = ref.child('attendance').child(day_str).get()
                count = len(day_data) if day_data else 0
                attendance_data.append({'date': day_str, 'count': count})
            analytics['attendance_trends'] = attendance_data[::-1]
            
            # Giving summary
            donations = ref.child('donations').get()
            if donations:
                total = sum(d.get('amount', 0) for d in donations.values())
                by_type = {}
                for d in donations.values():
                    t = d.get('type', 'other')
                    by_type[t] = by_type.get(t, 0) + d.get('amount', 0)
                analytics['giving_summary'] = {'total': total, 'by_type': by_type}
            
            # Membership growth (last 12 months)
            members = ref.child('members').get()
            if members:
                growth = []
                for i in range(12):
                    d = date.today() - timedelta(days=i*30)
                    count = sum(1 for m in members.values() 
                                if m.get('join_date', '')[:7] <= d.strftime('%Y-%m'))
                    growth.append({'month': d.strftime('%Y-%m'), 'count': count})
                analytics['membership_growth'] = growth[::-1]
        except Exception as e:
            print(f"Analytics error: {e}")
    
    return jsonify(analytics)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))


