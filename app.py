import os
import uuid
import json
import requests
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, send_from_directory, send_file

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Optional heavy dependencies - import with fallbacks to reduce cold-start impact
try:
    import pandas as pd
except Exception:  # Catch any error during import (missing deps, binary incompat)
    pd = None
    print("Warning: pandas not available. Attendance reports will be limited.")

try:
    import firebase_admin
    from firebase_admin import credentials, auth, db
    FIREBASE_AVAILABLE = True
except Exception:
    FIREBASE_AVAILABLE = False
    print("Warning: Firebase admin SDK not available. Running in demo mode.")

try:
    import qrcode
    QRCODE_AVAILABLE = True
except Exception:
    QRCODE_AVAILABLE = False
    print("Warning: qrcode not available. QR code generation disabled.")

import io

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Serve static files from 'static' folder
@app.route('/static/<path:filename>', endpoint='static_files')
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

@app.route('/', endpoint='index')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# ==================== AUTH ROUTES ====================

@app.route('/login', methods=['GET', 'POST'], endpoint='login')
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

@app.route('/logout', endpoint='logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==================== DASHBOARD ROUTE ====================

@app.route('/dashboard', endpoint='dashboard')
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

@app.route('/members', endpoint='members_list')
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

@app.route('/api/members', methods=['POST'], endpoint='add_member')
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

@app.route('/api/members/<member_id>', methods=['PUT'], endpoint='update_member')
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

@app.route('/api/members/<member_id>', methods=['DELETE'], endpoint='delete_member')
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

@app.route('/api/members/import', methods=['POST'], endpoint='import_members')
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

@app.route('/attendance', endpoint='attendance_report')
def attendance_report():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Get date range from query params
    start_date = request.args.get('start', (date.today() - timedelta(days=30)).isoformat())
    end_date = request.args.get('end', date.today().isoformat())
    
    records = []
    if FIREBASE_INITIALIZED:
        try:
            # Generate date list with pandas if available, else use datetime fallback
            if pd is not None:
                dates = pd.date_range(start=start_date, end=end_date)
                date_list = [d.strftime('%Y-%m-%d') for d in dates]
            else:
                # Fallback: generate dates manually
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                date_list = []
                current = start_dt
                while current <= end_dt:
                    date_list.append(current.isoformat())
                    current += timedelta(days=1)
            
            for d in date_list:
                day_data = ref.child('attendance').child(d).get()
                if day_data:
                    for member_id, record in day_data.items():
                        records.append({
                            'date': d,
                            'member_id': member_id,
                            'timestamp': record.get('timestamp', '')
                        })
        except Exception as e:
            print(f"Error fetching attendance: {e}")
    
    return render_template('attendance.html', records=records, start=start_date, end=end_date, user=session.get('email'))

@app.route('/api/attendance/record', methods=['POST'], endpoint='record_attendance')
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

@app.route('/api/attendance/stats', endpoint='attendance_stats')
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

@app.route('/events', endpoint='events_list')
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

@app.route('/api/events', methods=['POST'], endpoint='create_event')
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

@app.route('/groups', endpoint='groups_list')
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

@app.route('/api/groups', methods=['POST'], endpoint='create_group')
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

@app.route('/api/groups/<group_id>/members', methods=['POST'], endpoint='add_group_member')
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

@app.route('/donations', endpoint='donations_page')
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

@app.route('/api/donations', methods=['POST'], endpoint='record_donation')
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

@app.route('/api/donations/export', endpoint='export_donations')
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

@app.route('/communications', endpoint='communications_page')
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

@app.route('/api/announcements', methods=['POST'], endpoint='create_announcement')
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

@app.route('/api/prayer-requests', methods=['POST'], endpoint='submit_prayer_request')
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

@app.route('/volunteers', endpoint='volunteers_page')
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

@app.route('/api/volunteers/schedule', methods=['POST'], endpoint='create_schedule')
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

@app.route('/resources', endpoint='resources_page')
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

@app.route('/api/inventory', methods=['POST'], endpoint='add_inventory')
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

@app.route('/bible', endpoint='bible_reader')
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

@app.route('/notes', endpoint='notes')
def notes():
    return redirect(url_for('bible_reader'))

@app.route('/history', endpoint='history')
def history():
    return redirect(url_for('bible_reader'))

@app.route('/bookmarks', endpoint='bookmarks')
def bookmarks():
    return redirect(url_for('bible_reader'))

@app.route('/highlights', endpoint='highlights')
def highlights():
    return redirect(url_for('bible_reader'))

@app.route('/search', endpoint='search')
def search():
    return redirect(url_for('bible_reader'))

@app.route('/service-update', endpoint='service_update')
def service_update():
    return redirect(url_for('bible_reader'))

# ==================== QR & ATTENDANCE ====================

@app.route('/start_service', methods=['POST'], endpoint='start_service')
def start_service():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not QRCODE_AVAILABLE:
        return jsonify({'error': 'QR code generation not available'}), 500
    
    # Get service location from request (admin's GPS when starting service)
    data = request.get_json() or {}
    latitude = data.get('latitude', 0)
    longitude = data.get('longitude', 0)
    
    session_id = str(uuid.uuid4())
    
    if FIREBASE_INITIALIZED:
        try:
            session_data = {
                'session_id': session_id,
                'latitude': latitude,
                'longitude': longitude,
                'timestamp': datetime.now().isoformat(),
                'created_by': session['user'],
                'active': True
            }
            ref.child('sessions').child(session_id).set(session_data)
        except Exception as e:
            print(f"Warning: {e}")
    
    try:
        # Generate QR code as SVG (pure Python, no PIL needed)
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr_url = request.host_url.rstrip('/') + f'/scan?session_id={session_id}'
        qr.add_data(qr_url)
        qr.make(fit=True)
        
        from qrcode.image.svg import SvgImage
        img = qr.make_image(image_factory=SvgImage)
        svg_content = img.to_string()
        
        return Response(svg_content, mimetype='image/svg+xml')
    except Exception as e:
        print(f"QR generation error: {e}")
        return jsonify({'error': 'Failed to generate QR code'}), 500

@app.route('/test_route_test', methods=['GET'], endpoint='test_route')
def test_route():
    return jsonify({'status': 'ok', 'message': 'Test route works'})

# ==================== QR & ATTENDANCE ====================

@app.route('/start_service', methods=['POST'], endpoint='start_service')
def start_service():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not QRCODE_AVAILABLE:
        return jsonify({'error': 'QR code generation not available'}), 500
    
    session_id = str(uuid.uuid4())
    latitude = 0  # Will be set from frontend
    longitude = 0
    
    if FIREBASE_INITIALIZED:
        try:
            session_data = {
                'session_id': session_id,
                'latitude': latitude,
                'longitude': longitude,
                'timestamp': datetime.now().isoformat(),
                'created_by': session['user'],
                'active': True
            }
            ref.child('sessions').child(session_id).set(session_data)
        except Exception as e:
            print(f"Warning: {e}")
    
    try:
        # Generate QR code as SVG (pure Python, no PIL needed)
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        # Encode a URL that members will visit when they scan
        qr_url = f"/scan?session_id={session_id}"
        qr.add_data(qr_url)
        qr.make(fit=True)
        
        from qrcode.image.svg import SvgImage
        img = qr.make_image(image_factory=SvgImage)
        svg_content = img.to_string()
        
        return Response(svg_content, mimetype='image/svg+xml')
    except Exception as e:
        print(f"QR generation error: {e}")
        return jsonify({'error': 'Failed to generate QR code'}), 500

@app.route('/scan', methods=['GET'], endpoint='scan_form')
def scan_form():
    """Display attendance capture form for members scanning QR"""
    session_id = request.args.get('session_id', '')
    return render_template('scan.html', session_id=session_id)

@app.route('/api/attendance/scan', methods=['POST'], endpoint='scan_attendance')
def scan_attendance():
    """Handle attendance submission from QR scan form"""
    data = request.get_json()
    session_id = data.get('session_id')
    member_name = data.get('name', '').strip()
    church_group = data.get('church_group', '').strip()
    member_id = data.get('member_id', '').strip()
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    if not member_name or not church_group:
        return jsonify({'error': 'Name and church group are required'}), 400
    
    # Get service location from Firebase
    service_lat = 0
    service_lon = 0
    if FIREBASE_INITIALIZED:
        try:
            session_data = ref.child('sessions').child(session_id).get()
            if session_data:
                service_lat = session_data.get('latitude', 0)
                service_lon = session_data.get('longitude', 0)
        except Exception as e:
            print(f"Error fetching session: {e}")
    
    # Calculate distance (Haversine formula)
    distance_m = 0
    if latitude and longitude and service_lat and service_lon:
        from math import radians, sin, cos, sqrt, atan2
        R = 6371000  # Earth radius in meters
        lat1, lon1 = radians(service_lat), radians(service_lon)
        lat2, lon2 = radians(latitude), radians(longitude)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance_m = R * c
    
    # Check if within 5 meters
    if distance_m > 5:
        return jsonify({
            'error': f'You are {int(distance_m)}m away. Please get within 5m of the service location.',
            'distance': round(distance_m, 1)
        }), 403
    
    today = date.today().isoformat()
    
    if FIREBASE_INITIALIZED:
        try:
            # Generate member/attendance ID
            attendance_id = str(uuid.uuid4())[:8]
            attendance_data = {
                'id': attendance_id,
                'session_id': session_id,
                'member_id': member_id or attendance_id,
                'member_name': member_name,
                'church_group': church_group,
                'latitude': latitude,
                'longitude': longitude,
                'distance_m': round(distance_m, 2),
                'timestamp': datetime.now().isoformat(),
                'date': today,
                'service_type': 'sunday'
            }
            ref.child('attendance').child(today).child(attendance_id).set(attendance_data)
            return jsonify({'success': True, 'attendance_id': attendance_id, 'distance': round(distance_m, 2)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        # Demo mode
        return jsonify({'success': True, 'demo': True, 'distance': round(distance_m, 2)})



