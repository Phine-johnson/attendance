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
    
    # Get filter parameters
    search_query = request.args.get('search', '').lower()
    filter_status = request.args.get('status', 'all')
    filter_baptized = request.args.get('baptized', 'all')
    filter_family = request.args.get('family', '')
    
    members = []
    families = set()
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('members').get()
            if data:
                members = [{'id': k, **v} for k, v in data.items()]
                # Collect unique families
                for m in members:
                    fam = m.get('family_id', '')
                    if fam:
                        families.add(fam)
                # Apply filters
                if search_query:
                    members = [m for m in members if 
                              search_query in m.get('first_name', '').lower() or
                              search_query in m.get('last_name', '').lower() or
                              search_query in m.get('email', '').lower() or
                              search_query in m.get('phone', '').lower()]
                if filter_status != 'all':
                    members = [m for m in members if m.get('status', '') == filter_status]
                if filter_baptized != 'all':
                    baptized_val = filter_baptized == 'true'
                    members = [m for m in members if m.get('baptized', False) == baptized_val]
                if filter_family:
                    members = [m for m in members if m.get('family_id', '') == filter_family]
                members.sort(key=lambda x: x.get('last_name', '').lower())
        except Exception as e:
            print(f"Error fetching members: {e}")
    
    return render_template('members.html', 
                         members=members, 
                         families=sorted(list(families)),
                         search_query=search_query,
                         filter_status=filter_status,
                         filter_baptized=filter_baptized,
                         filter_family=filter_family,
                         user=session.get('email'))

# Family/Household Management - Feature 4
@app.route('/families')
def families_list():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    families = {}
    members_map = {}
    if FIREBASE_INITIALIZED:
        try:
            # Get all members
            m = ref.child('members').get()
            if m:
                members_map = m
                # Group by family_id
                for mid, member in m.items():
                    fam_id = member.get('family_id', '') or 'No Family'
                    if fam_id not in families:
                        families[fam_id] = {
                            'id': fam_id,
                            'members': [],
                            'head_of_household': None
                        }
                    families[fam_id]['members'].append({'id': mid, **member})
                
                # Determine head of household (first adult or longest member)
                for fid, fam in families.items():
                    adult_members = [m for m in fam['members'] if m.get('date_of_birth')]
                    if adult_members:
                        # Sort by join_date, earliest first
                        adult_members.sort(key=lambda x: x.get('join_date', '9999'))
                        fam['head_of_household'] = adult_members[0].get('first_name', '') + ' ' + adult_members[0].get('last_name', '')
        except Exception as e:
            print(f"Error fetching families: {e}")
    
    return render_template('families.html', families=families, members=members_map, user=session.get('email'))

@app.route('/api/families/<fam_id>/members', methods=['POST'])
def add_family_member(fam_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = data.get('member_id')
    
    if FIREBASE_INITIALIZED:
        try:
            ref.child('members').child(member_id).update({'family_id': fam_id})
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

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

# ===== API ENDPOINTS =====

# Feature 2: Financial Reports & Donation Analytics
@app.route('/donations/reports')
def donation_reports():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    start_date = request.args.get('start', (date.today() - timedelta(days=365)).isoformat())
    end_date = request.args.get('end', date.today().isoformat())
    
    donations = []
    summary = {'total': 0, 'count': 0, 'tithe': 0, 'offering': 0, 'other': 0}
    monthly_stats = {}
    donor_stats = {}
    method_stats = {'cash': 0, 'check': 0, 'mobile_money': 0, 'bank_transfer': 0, 'online': 0}
    
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('donations').get()
            if data:
                for d in data.values():
                    ddate = d.get('date', '')
                    if start_date <= ddate <= end_date:
                        donations.append({'id': d.get('id', ''), **d})
                        amount = float(d.get('amount', 0))
                        dtype = d.get('type', 'other')
                        method = d.get('method', 'cash')
                        member_id = d.get('member_id', '')
                        
                        summary['total'] += amount
                        summary['count'] += 1
                        
                        if dtype == 'tithe':
                            summary['tithe'] += amount
                        elif dtype == 'offering':
                            summary['offering'] += amount
                        else:
                            summary['other'] += amount
                        
                        month_key = ddate[:7]
                        if month_key not in monthly_stats:
                            monthly_stats[month_key] = {'total': 0, 'count': 0}
                        monthly_stats[month_key]['total'] += amount
                        monthly_stats[month_key]['count'] += 1
                        
                        if member_id:
                            if member_id not in donor_stats:
                                donor_stats[member_id] = {'total': 0, 'count': 0}
                            donor_stats[member_id]['total'] += amount
                            donor_stats[member_id]['count'] += 1
                        
                        if method in method_stats:
                            method_stats[method] += amount
                
                donations.sort(key=lambda x: x.get('date', ''), reverse=True)
        except Exception as e:
            print(f"Error fetching donations: {e}")
    
    monthly_sorted = sorted(monthly_stats.items())
    top_donors = sorted(donor_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:10]
    
    return render_template('donation_reports.html',
                         donations=donations,
                         summary=summary,
                         monthly_stats=monthly_sorted,
                         top_donors=top_donors,
                         method_stats=method_stats,
                         start_date=start_date,
                         end_date=end_date,
                         user=session.get('email'))

@app.route('/api/donations/stats')
def donation_stats():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    start = request.args.get('start', (date.today() - timedelta(days=365)).isoformat())
    end = request.args.get('end', date.today().isoformat())
    
    stats = {'total': 0, 'count': 0, 'monthly': [], 'by_type': {}, 'by_method': {}}
    
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('donations').get()
            if data:
                monthly = {}
                by_type = {}
                by_method = {}
                
                for d in data.values():
                    ddate = d.get('date', '')
                    if start <= ddate <= end:
                        amount = float(d.get('amount', 0))
                        dtype = d.get('type', 'other')
                        method = d.get('method', 'cash')
                        month_key = ddate[:7]
                        
                        stats['total'] += amount
                        stats['count'] += 1
                        
                        monthly[month_key] = monthly.get(month_key, 0) + amount
                        by_type[dtype] = by_type.get(dtype, 0) + amount
                        by_method[method] = by_method.get(method, 0) + amount
                
                stats['monthly'] = [{'month': k, 'total': v} for k, v in sorted(monthly.items())]
                stats['by_type'] = by_type
                stats['by_method'] = by_method
        except Exception as e:
            print(f"Error: {e}")
    
    return jsonify(stats)

# Feature 3: Small Group Management with Attendance Tracking
@app.route('/api/groups/<group_id>/attendance', methods=['GET'])
def group_attendance(group_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    start_date = request.args.get('start', (date.today() - timedelta(days=30)).isoformat())
    end_date = request.args.get('end', date.today().isoformat())
    attendance_records = []
    member_stats = {}
    if FIREBASE_INITIALIZED:
        try:
            group_members = ref.child('groups').child(group_id).child('members').get()
            if group_members:
                for member_id in group_members.keys():
                    member_stats[member_id] = {'total': 0, 'dates': []}
                    current = datetime.strptime(start_date, '%Y-%m-%d')
                    end = datetime.strptime(end_date, '%Y-%m-%d')
                    while current <= end:
                        day_str = current.strftime('%Y-%m-%d')
                        day_attendance = ref.child('attendance').child(day_str).child(member_id).get()
                        if day_attendance:
                            attendance_records.append({
                                'date': day_str,
                                'member_id': member_id,
                                'timestamp': day_attendance.get('timestamp', ''),
                                'service_type': day_attendance.get('service_type', 'sunday')
                            })
                            member_stats[member_id]['total'] += 1
                            member_stats[member_id]['dates'].append(day_str)
                        current += timedelta(days=1)
        except Exception as e:
            print(f"Error fetching group attendance: {e}")
    return jsonify({'attendance': attendance_records, 'stats': member_stats})

@app.route('/api/groups/<group_id>/attendance/record', methods=['POST'])
def record_group_attendance(group_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    member_ids = data.get('member_ids', [])
    service_type = data.get('service_type', 'sunday')
    today = date.today().isoformat()
    recorded = []
    if FIREBASE_INITIALIZED:
        try:
            for member_id in member_ids:
                ref.child('attendance').child(today).child(member_id).set({
                    'timestamp': datetime.now().isoformat(),
                    'service_type': service_type,
                    'group_id': group_id
                })
                recorded.append(member_id)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'recorded': recorded, 'count': len(recorded)})

# Feature 10: Pastoral Care Visit Tracking System
@app.route('/visits')
def visits_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    visits = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('pastoral_visits').get()
            if data:
                visits = [{'id': k, **v} for k, v in data.items()]
                visits.sort(key=lambda x: x.get('visit_date', ''), reverse=True)
        except: pass
    return render_template('visits.html', visits=visits, user=session.get('email'))

@app.route('/api/visits', methods=['POST'])
def record_visit():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    visit_id = str(uuid.uuid4())[:8]
    visit_data = {
        'id': visit_id,
        'member_id': data.get('member_id', ''),
        'visit_date': data.get('visit_date', date.today().isoformat()),
        'visit_type': data.get('visit_type', 'hospital'),
        'notes': data.get('notes', ''),
        'visited_by': session.get('email', ''),
        'created_at': datetime.now().isoformat()
    }
    if FIREBASE_INITIALIZED:
        try:
            ref.child('pastoral_visits').child(visit_id).set(visit_data)
            return jsonify({'success': True, 'visit_id': visit_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

@app.route('/api/visits/<visit_id>', methods=['DELETE'])
def delete_visit(visit_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if FIREBASE_INITIALIZED:
        try:
            ref.child('pastoral_visits').child(visit_id).delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True})

# Feature 11: Baptism & Membership Milestone Tracking
@app.route('/milestones')
def milestones_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    milestones = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('milestones').get()
            if data:
                milestones = [{'id': k, **v} for k, v in data.items()]
                milestones.sort(key=lambda x: x.get('date', ''), reverse=True)
        except: pass
    return render_template('milestones.html', milestones=milestones, user=session.get('email'))

@app.route('/api/milestones', methods=['POST'])
def add_milestone():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    milestone_id = str(uuid.uuid4())[:8]
    milestone_data = {
        'id': milestone_id,
        'member_id': data.get('member_id', ''),
        'type': data.get('type', 'baptism'),
        'date': data.get('date', date.today().isoformat()),
        'description': data.get('description', ''),
        'recorded_by': session.get('email', ''),
        'created_at': datetime.now().isoformat()
    }
    if FIREBASE_INITIALIZED:
        try:
            ref.child('milestones').child(milestone_id).set(milestone_data)
            return jsonify({'success': True, 'milestone_id': milestone_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'success': True, 'demo': True})

# Feature 12: Volunteer Scheduling Calendar
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
        'assigned_to': data.get('assigned_to', ''),
        'status': data.get('status', 'scheduled'),
        'reminder_sent': False,
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

@app.route('/api/volunteers/calendar')
def volunteer_calendar():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    start = request.args.get('start', date.today().isoformat())
    end = request.args.get('end', (date.today() + timedelta(days=30)).isoformat())
    events = []
    if FIREBASE_INITIALIZED:
        try:
            data = ref.child('schedules').get()
            if data:
                for k, v in data.items():
                    if start <= v.get('date', '') <= end:
                        events.append({
                            'id': k,
                            'title': v.get('role', '') + (' - ' + v.get('assigned_to', '') if v.get('assigned_to') else ''),
                            'start': v.get('date', ''),
                            'end': v.get('date', ''),
                            'extendedProps': {
                                'time': v.get('time', ''),
                                'status': v.get('status', 'scheduled')
                            }
                        })
        except: pass
    return jsonify(events)

# Feature 13: Custom Report Builder
@app.route('/reports')
def reports_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('reports.html', user=session.get('email'))

@app.route('/api/reports/generate', methods=['POST'])
def generate_report():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    report_type = data.get('type', 'summary')
    start_date = data.get('start', (date.today() - timedelta(days=30)).isoformat())
    end_date = data.get('end', date.today().isoformat())
    
    report = {'type': report_type, 'start': start_date, 'end': end_date}
    
    if FIREBASE_INITIALIZED:
        try:
            if report_type == 'membership':
                members = ref.child('members').get() or {}
                active = sum(1 for m in members.values() if m.get('status') == 'active')
                report['data'] = {'total': len(members), 'active': active, 'inactive': len(members) - active}
            elif report_type == 'attendance':
                total_attendance = 0
                current = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d')
                while current <= end:
                    day = ref.child('attendance').child(current.strftime('%Y-%m-%d')).get()
                    if day:
                        total_attendance += len(day)
                    current += timedelta(days=1)
                report['data'] = {'total_attendance': total_attendance}
            elif report_type == 'financial':
                donations = ref.child('donations').get() or {}
                total = sum(float(d.get('amount', 0)) for d in donations.values() if start_date <= d.get('date', '') <= end_date)
                report['data'] = {'total_donations': total, 'count': len([d for d in donations.values() if start_date <= d.get('date', '') <= end_date])}
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
        return jsonify(report)


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