import os
import uuid
import json
import requests
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, send_from_directory, send_file
try:
    import firebase_admin
    from firebase_admin import credentials, auth, db
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

# Initialize Firebase Admin SDK if available
FIREBASE_INITIALIZED = False
ref = None
if FIREBASE_AVAILABLE:
    try:
        service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
        if service_account_json:
            with open('/tmp/serviceAccountKey.json', 'w') as f:
                f.write(service_account_json)
            cred = credentials.Certificate('/tmp/serviceAccountKey.json')
        elif os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
        else:
            print("Warning: No service account key found. Running in demo mode.")
            raise Exception("Service account key missing")
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': os.environ.get('FIREBASE_DATABASE_URL')
        })
        ref = db.reference()
        FIREBASE_INITIALIZED = True
        print("✅ Firebase Admin SDK initialized successfully")
    except Exception as e:
        print(f"Warning: Firebase initialization failed: {e}")
        print("Running in demo mode without Firebase.")
        FIREBASE_INITIALIZED = False
        ref = None

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
                import requests
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

# ==================== DASHBOARD ROUTE ====================

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Get stats for dashboard
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
                members.sort(key=lambda x: x.get('name', ''))
        except Exception as e:
            print(f"Error fetching members: {e}")
    
    return render_template('members.html', members=members, user=session.get('email'))

@app.route('/api/members', methods=['POST'])
def add_member():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = str(uuid.uuid4())[:8]
    
    member_data = {
        'id': member_id,
        'member_id': data.get('memberId', member_id),
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
            return jsonify({'success': True, 'member_id': member_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        # Demo mode
        return jsonify({'success': True, 'member_id': member_id, 'demo': True})

@app.route('/api/members/<member_id>', methods=['PUT'])
def update_member(member_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    if FIREBASE_INITIALIZED:
        try:
            ref.child('members').child(member_id).update(data)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

@app.route('/api/members/<member_id>', methods=['DELETE'])
def delete_member(member_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('members').child(member_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True})

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
    start_date = request.args.get('start', (date.today() - timedelta(days=30)).isoformat())
    end_date = request.args.get('end', date.today().isoformat())
    
    records = []
    if FIREBASE_INITIALIZED:
        try:
            dates = pd.date_range(start=start_date, end=end_date)
            for d in dates:
                day_data = ref.child('attendance').child(d.strftime('%Y-%m-%d')).get()
                if day_data:
                    for member_id, record in day_data.items():
                        records.append({
                            'date': d.strftime('%Y-%m-%d'),
                            'member_id': member_id,
                            'timestamp': record.get('timestamp', '')
                        })
        except Exception as e:
            print(f"Error fetching attendance: {e}")
    
    return render_template('attendance.html', records=records, start=start_date, end=end_date, user=session.get('email'))

@app.route('/api/attendance/record', methods=['POST'])
def record_attendance():
    """Record attendance for a member (via QR scan or manual entry)"""
    data = request.get_json()
    member_id = data.get('member_id')
    service_type = data.get('service_type', 'sunday')
    today = date.today().isoformat()
    
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
    return jsonify({'success': True, 'demo': True})

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
    return jsonify({'success': True, 'demo': True})

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
    return jsonify({'success': True, 'demo': True})

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
    return jsonify({'success': True, 'demo': True})

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
    
    donation_data = {
        'id': donation_id,
        'member_id': data.get('member_id', ''),
        'amount': float(data.get('amount', 0)),
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
    return jsonify({'success': True, 'demo': True})

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
    return jsonify({'success': True})

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
    return jsonify({'success': True})

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
        'assigned_to': data.get('assigned_to', ''),
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
    return jsonify({'success': True, 'demo': True})

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
    
    return render_template('resources.html', inventory=inventory, bookings=bookings, user=session.get('email'))

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
    return jsonify({'success': True})

# ==================== BIBLE TOOLS ROUTES ====================

@app.route('/bible')
def bible_reader():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html',
        user=session.get('email'),
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

    data = request.get_json() or {}
    session_id = str(uuid.uuid4())
    proximity_limit = 3
    latitude = data.get('latitude', 0)
    longitude = data.get('longitude', 0)

    if FIREBASE_INITIALIZED:
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
            print(f"Warning: {e}")

    qr_data = json.dumps({
        'sid': session_id,
        'lat': latitude,
        'lng': longitude,
        'limit': proximity_limit
    })

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
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
            print("Demo mode — service data not saved")
        
        return jsonify({'success': True, 'message': 'Service update published'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/resources')
def resources_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    stats = {'total_inventory': 0, 'low_stock': 0, 'active_bookings': 0}
    inventory = []
    bookings = []
    
    if FIREBASE_INITIALIZED:
        try:
            inv = ref.child('inventory').get()
            if inv:
                inventory = [{'id': k, **v} for k, v in inv.items()]
                stats['total_inventory'] = len(inventory)
                stats['low_stock'] = sum(1 for i in inventory if i.get('quantity', 0) <= i.get('min_quantity', 999))
            
            b = ref.child('bookings').get()
            if b:
                bookings = [{'id': k, **v} for k, v in b.items()]
                today = date.today().isoformat()
                stats['active_bookings'] = sum(1 for b in bookings if b.get('date', '') >= today)
        except Exception as e:
            print(f"Error: {e}")
    
    return render_template('resources.html', 
        inventory=inventory, 
        bookings=bookings, 
        stats=stats,
        user=session.get('email'),
        firebase_api_key=os.environ.get('FIREBASE_API_KEY'),
        firebase_auth_domain=os.environ.get('FIREBASE_AUTH_DOMAIN'),
        firebase_database_url=os.environ.get('FIREBASE_DATABASE_URL'),
        firebase_project_id=os.environ.get('FIREBASE_PROJECT_ID'),
        firebase_storage_bucket=os.environ.get('FIREBASE_STORAGE_BUCKET'),
        firebase_messaging_sender_id=os.environ.get('FIREBASE_MESSAGING_SENDER_ID'),
        firebase_app_id=os.environ.get('FIREBASE_APP_ID')
    )

# Add routes for all new pages
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
                members.sort(key=lambda x: x.get('name', ''))
        except: pass
    return render_template('members.html', members=members, user=session.get('email'))

@app.route('/attendance')
def attendance_report():
    if 'user' not in session:
        return redirect(url_for('login'))
    start = request.args.get('start', (date.today() - timedelta(days=30)).isoformat())
    end = request.args.get('end', date.today().isoformat())
    records = []
    if FIREBASE_INITIALIZED:
        try:
            from datetime import timedelta
            import pandas as pd
            dates = pd.date_range(start=start, end=end)
            for d in dates:
                day = ref.child('attendance').child(d.strftime('%Y-%m-%d')).get()
                if day:
                    for mid, rec in day.items():
                        records.append({'date': d.strftime('%Y-%m-%d'), 'member_id': mid, 'timestamp': rec.get('timestamp','')})
        except: pass
    return render_template('attendance.html', records=records, start=start, end=end, user=session.get('email'))

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
                events.sort(key=lambda x: x.get('date',''), reverse=True)
        except: pass
    return render_template('events.html', events=events, user=session.get('email'))

@app.route('/groups')
def groups_list():
    if 'user' not in session:
        return redirect(url_for('login'))
    groups = []
    members_map = {}
    if FIREBASE_INITIALIZED:
        try:
            g = ref.child('groups').get()
            if g: groups = [{'id': k, **v} for k, v in g.items()]
            m = ref.child('members').get()
            if m: members_map = m
        except: pass
    return render_template('groups.html', groups=groups, members=members_map, user=session.get('email'))

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
                donations.sort(key=lambda x: x.get('date',''), reverse=True)
                summary['total'] = sum(d.get('amount',0) for d in donations)
                summary['count'] = len(donations)
        except: pass
    return render_template('donations.html', donations=donations, summary=summary, user=session.get('email'))

@app.route('/communications')
def communications_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    announcements = []
    prayer_requests = []
    if FIREBASE_INITIALIZED:
        try:
            a = ref.child('announcements').get()
            if a: announcements = [{'id': k, **v} for k, v in a.items()]
            p = ref.child('prayer_requests').get()
            if p: prayer_requests = [{'id': k, **v} for k, v in p.items()]
        except: pass
    return render_template('communications.html', announcements=announcements, prayer_requests=prayer_requests, user=session.get('email'))

@app.route('/volunteers')
def volunteers_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    schedules = []
    roles = ['Usher', 'Worship Leader', 'Sound Tech', "Children's Church", 'Greeter']
    if FIREBASE_INITIALIZED:
        try:
            s = ref.child('schedules').get()
            if s: schedules = [{'id': k, **v} for k, v in s.items()]
        except: pass
    return render_template('volunteers.html', schedules=schedules, roles=roles, user=session.get('email'))

# ==================== API ENDPOINTS ====================

@app.route('/api/members/import', methods=['POST'])
def import_members():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    try:
        import csv, io
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        imported = 0
        for row in reader:
            mid = str(uuid.uuid4())[:8]
            mdata = {
                'id': mid, 'member_id': row.get('member_id', mid),
                'first_name': row.get('first_name', ''), 'last_name': row.get('last_name', ''),
                'email': row.get('email', ''), 'phone': row.get('phone', ''),
                'status': 'active', 'created_at': datetime.now().isoformat()
            }
            if FIREBASE_INITIALIZED:
                ref.child('members').child(mid).set(mdata)
            imported += 1
        return jsonify({'success': True, 'imported': imported})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/attendance/record', methods=['POST'])
def record_attendance():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    mid = data.get('member_id')
    today = date.today().isoformat()
    if FIREBASE_INITIALIZED:
        try:
            ref.child('attendance').child(today).child(mid).set({
                'timestamp': datetime.now().isoformat(),
                'service_type': data.get('service_type', 'sunday')
            })
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

@app.route('/api/attendance/stats')
def attendance_stats():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    stats = {'last_7_days': [], 'by_service_type': {}, 'member_frequency': []}
    if FIREBASE_INITIALIZED:
        try:
            for i in range(7):
                d = date.today() - timedelta(days=i)
                day = ref.child('attendance').child(d.strftime('%Y-%m-%d')).get()
                count = len(day) if day else 0
                stats['last_7_days'].append({'date': d.strftime('%Y-%m-%d'), 'count': count})
            stats['last_7_days'].reverse()
        except Exception as e:
            print(f"Stats error: {e}")
    return jsonify(stats)

@app.route('/api/events', methods=['POST'])
def create_event():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    eid = str(uuid.uuid4())[:8]
    event = {
        'id': eid, 'title': data.get('title', ''), 'description': data.get('description', ''),
        'date': data.get('date', ''), 'time': data.get('time', ''), 'location': data.get('location', ''),
        'type': data.get('type', 'service'), 'created_by': session.get('email', ''),
        'created_at': datetime.now().isoformat()
    }
    if FIREBASE_INITIALIZED:
        try:
            ref.child('events').child(eid).set(event)
            return jsonify({'success': True, 'event_id': eid})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

@app.route('/api/groups', methods=['POST'])
def create_group():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    gid = str(uuid.uuid4())[:8]
    group = {
        'id': gid, 'name': data.get('name', ''), 'description': data.get('description', ''),
        'category': data.get('category', ''), 'leader_id': data.get('leaderId', ''),
        'meeting_day': data.get('meetingDay', ''), 'meeting_time': data.get('meetingTime', ''),
        'created_by': session.get('email', ''), 'created_at': datetime.now().isoformat()
    }
    if FIREBASE_INITIALIZED:
        try:
            ref.child('groups').child(gid).set(group)
            return jsonify({'success': True, 'group_id': gid})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

@app.route('/api/groups/<gid>/members', methods=['POST'])
def add_group_member(gid):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    mid = data.get('member_id')
    if FIREBASE_INITIALIZED:
        try:
            ref.child('groups').child(gid).child('members').child(mid).set({'added_at': datetime.now().isoformat()})
            ref.child('members').child(mid).child('groups').child(gid).set(True)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

@app.route('/api/donations', methods=['POST'])
def record_donation():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    did = str(uuid.uuid4())[:8]
    donation = {
        'id': did, 'member_id': data.get('member_id', ''), 'amount': float(data.get('amount', 0)),
        'type': data.get('type', 'tithe'), 'method': data.get('method', 'cash'),
        'date': data.get('date', date.today().isoformat()), 'notes': data.get('notes', ''),
        'recorded_by': session.get('email', ''), 'created_at': datetime.now().isoformat()
    }
    if FIREBASE_INITIALIZED:
        try:
            ref.child('donations').child(did).set(donation)
            return jsonify({'success': True, 'donation_id': did})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

@app.route('/api/donations/export')
def export_donations():
    if 'user' not in session:
        return redirect(url_for('login'))
    import csv, io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Date', 'Member ID', 'Amount', 'Type', 'Method', 'Notes'])
    if FIREBASE_INITIALIZED:
        try:
            d = ref.child('donations').get()
            if d:
                for v in d.values():
                    w.writerow([v.get('date',''), v.get('member_id',''), v.get('amount',0), v.get('type',''), v.get('method',''), v.get('notes','')])
        except: pass
    out.seek(0)
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=donations_{date.today()}.csv'})

@app.route('/api/inventory/export')
def export_inventory():
    if 'user' not in session:
        return redirect(url_for('login'))
    import csv, io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['ID', 'Name', 'Category', 'Quantity', 'Min Quantity', 'Location', 'Status'])
    if FIREBASE_INITIALIZED:
        try:
            inv = ref.child('inventory').get()
            if inv:
                for v in inv.values():
                    w.writerow([v.get('id',''), v.get('name',''), v.get('category',''), v.get('quantity',0),
                               v.get('min_quantity',0), v.get('location',''), 'Low Stock' if v.get('quantity',0) <= v.get('min_quantity',999) else 'In Stock'])
        except: pass
    out.seek(0)
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=inventory_{date.today()}.csv'})

@app.route('/api/announcements', methods=['POST'])
def create_announcement():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    aid = str(uuid.uuid4())[:8]
    ann = {
        'id': aid, 'title': data.get('title', ''), 'content': data.get('content', ''),
        'target': data.get('target', 'all'), 'priority': data.get('priority', 'normal'),
        'created_by': session.get('email', ''), 'created_at': datetime.now().isoformat(), 'sent': False
    }
    if FIREBASE_INITIALIZED:
        try:
            ref.child('announcements').child(aid).set(ann)
            return jsonify({'success': True, 'id': aid})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True})

@app.route('/api/prayer-requests', methods=['POST'])
def submit_prayer_request():
    data = request.get_json()
    pid = str(uuid.uuid4())[:8]
    pr = {
        'id': pid, 'name': data.get('name', 'Anonymous'), 'email': data.get('email', ''),
        'request': data.get('request', ''), 'urgent': data.get('urgent', False),
        'created_at': datetime.now().isoformat(), 'status': 'new'
    }
    if FIREBASE_INITIALIZED:
        try:
            ref.child('prayer_requests').child(pid).set(pr)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True})

@app.route('/api/volunteers/schedule', methods=['POST'])
def create_schedule():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    sid = str(uuid.uuid4())[:8]
    sched = {
        'id': sid, 'role': data.get('role', ''), 'date': data.get('date', ''),
        'assigned_to': data.get('assigned_to', ''), 'status': 'scheduled',
        'created_by': session.get('email', ''), 'created_at': datetime.now().isoformat()
    }
    if FIREBASE_INITIALIZED:
        try:
            ref.child('schedules').child(sid).set(sched)
            return jsonify({'success': True, 'schedule_id': sid})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

@app.route('/api/inventory', methods=['POST'])
def add_inventory():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    iid = str(uuid.uuid4())[:8]
    item = {
        'id': iid, 'name': data.get('name', ''), 'category': data.get('category', ''),
        'quantity': int(data.get('quantity', 0)), 'min_quantity': int(data.get('minQuantity', 0)),
        'location': data.get('location', ''), 'last_updated': datetime.now().isoformat()
    }
    if FIREBASE_INITIALIZED:
        try:
            ref.child('inventory').child(iid).set(item)
            return jsonify({'success': True, 'item_id': iid})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True})

@app.route('/api/members/<mid>', methods=['PUT', 'DELETE'])
def member_action(mid):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if request.method == 'PUT':
        data = request.get_json()
        if FIREBASE_INITIALIZED:
            try:
                ref.child('members').child(mid).update(data)
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        return jsonify({'success': True, 'demo': True})
    elif request.method == 'DELETE':
        if FIREBASE_INITIALIZED:
            try:
                ref.child('members').child(mid).delete()
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        return jsonify({'success': True})

@app.route('/api/inventory/<iid>', methods=['PUT', 'DELETE'])
def inventory_action(iid):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if request.method == 'PUT':
        data = request.get_json()
        if FIREBASE_INITIALIZED:
            try:
                ref.child('inventory').child(iid).update(data)
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        if FIREBASE_INITIALIZED:
            try:
                ref.child('inventory').child(iid).delete()
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        return jsonify({'success': True})

@app.route('/api/bookings/<bid>/cancel', methods=['POST'])
def cancel_booking(bid):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if FIREBASE_INITIALIZED:
        try:
            ref.child('bookings').child(bid).update({'status': 'cancelled'})
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True})

# ==================== STATIC ROUTES ====================

@app.route('/bible')
def bible_reader():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', user=session.get('email'),
        firebase_api_key=os.environ.get('FIREBASE_API_KEY'),
        firebase_auth_domain=os.environ.get('FIREBASE_AUTH_DOMAIN'),
        firebase_database_url=os.environ.get('FIREBASE_DATABASE_URL'),
        firebase_project_id=os.environ.get('FIREBASE_PROJECT_ID'),
        firebase_storage_bucket=os.environ.get('FIREBASE_STORAGE_BUCKET'),
        firebase_messaging_sender_id=os.environ.get('FIREBASE_MESSAGING_SENDER_ID'),
        firebase_app_id=os.environ.get('FIREBASE_APP_ID'))

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