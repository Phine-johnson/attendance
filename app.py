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

# Admin emails (comma-separated list in environment variable)
ADMIN_EMAILS = os.environ.get('ADMIN_EMAILS', '').split(',')
ADMIN_EMAILS = [e.strip() for e in ADMIN_EMAILS if e.strip()]

def is_admin():
    """Check if current user is an admin"""
    if 'user' not in session:
        return False
    email = session.get('email')
    return email in ADMIN_EMAILS

# Serve static files from 'static' folder
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

@app.before_request
def require_login_and_admin():
    """Require login and admin access for all routes except login, logout, and static"""
    # List of routes that don't require authentication
    allowed_routes = ['login', 'logout', 'static']
    
    # Check if current route is in allowed list
    if request.endpoint not in allowed_routes:
        # Require login
        if 'user' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Require admin access
        if not is_admin():
            return jsonify({'error': 'Admin access required'}), 403

@app.route('/api/notifications/send', methods=['POST'])
def send_notification():
    """Send push notification to members"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
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
    
    return jsonify({'success': True, 'demo': True})

@app.route('/api/sermons', methods=['POST'])
def add_sermon():
    """Add new sermon"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
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
    
    return jsonify({'success': True, 'demo': True})

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

@app.route('/api/analytics/dashboard', methods=['GET'])
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