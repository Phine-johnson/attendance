import os
import uuid
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, send_from_directory
try:
    import firebase_admin
    from firebase_admin import credentials, auth, db
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("Warning: Firebase admin SDK not available. Running in demo mode.")

import qrcode
import io
from datetime import datetime

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
if FIREBASE_AVAILABLE:
    try:
        import os
        import json
        
        # Try loading service account key from environment variable first
        service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
        
        if service_account_json:
            # Write to temp file for Firebase admin SDK
            with open('/tmp/serviceAccountKey.json', 'w') as f:
                f.write(service_account_json)
            cred = credentials.Certificate('/tmp/serviceAccountKey.json')
        elif os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
        else:
            print("Warning: No service account key found. Running in demo mode.")
            FIREBASE_INITIALIZED = False
            ref = None
            raise Exception("Service account key missing")
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': os.environ.get('FIREBASE_DATABASE_URL')
        })
        ref = db.reference()
        FIREBASE_INITIALIZED = True
    except Exception as e:
        print(f"Warning: Firebase initialization failed: {e}")
        print("Running in demo mode without Firebase.")
        FIREBASE_INITIALIZED = False
        ref = None
else:
    FIREBASE_INITIALIZED = False
    ref = None

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Demo mode: accept any email/password for demonstration
        if FIREBASE_AVAILABLE and FIREBASE_INITIALIZED:
            try:
                # Verify email and password using Firebase Auth REST API
                import requests
                api_key = os.environ.get('FIREBASE_API_KEY')
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
                payload = {
                    "email": email,
                    "password": password,
                    "returnSecureToken": True
                }
                response = requests.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    id_token = data['idToken']
                    # Verify the ID token
                    decoded_token = auth.verify_id_token(id_token)
                    session['user'] = decoded_token['uid']
                    session['email'] = email
                    return redirect(url_for('dashboard'))
                else:
                    return render_template('login.html', error="Invalid email or password")
            except Exception as e:
                return render_template('login.html', error=str(e))
        else:
            # Demo mode: simple authentication
            session['user'] = 'demo-user-id'
            session['email'] = email
            return redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
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
                         firebase_app_id=os.environ.get('FIREBASE_APP_ID'))

@app.route('/start_service', methods=['POST'])
def start_service():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # Generate a unique session ID
    session_id = str(uuid.uuid4())

    # Hardcoded GPS coordinates for example (replace with actual logic)
    latitude = 40.7128  # Example: New York City
    longitude = -74.0060

    # Store session data in Firebase if available
    if FIREBASE_AVAILABLE and FIREBASE_INITIALIZED:
        try:
            session_ref = ref.child('sessions').child(session_id)
            session_ref.set({
                'latitude': latitude,
                'longitude': longitude,
                'timestamp': datetime.now().isoformat(),
                'created_by': session['user']
            })
        except Exception as e:
            print(f"Warning: Failed to store session in Firebase: {e}")
            # Continue anyway for demo purposes

    # Generate QR code data
    qr_data = f"{session_id}|{latitude}|{longitude}"

    # Generate QR code image
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color='black', back_color='white')

    # Save QR code to a bytes buffer
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)

    # Return QR code as image response
    return Response(img_buffer.getvalue(), mimetype='image/png')

@app.route('/publish_service', methods=['POST'])
def publish_service():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()

        # Basic validation
        required_fields = ['occasion', 'date', 'theme']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Prepare service object
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

        # Write to Firebase Realtime Database at /weekly_service/current
        if FIREBASE_AVAILABLE and FIREBASE_INITIALIZED:
            try:
                service_ref = ref.child('weekly_service').child('current')
                service_ref.set(service_data)
                print(f"Service update written to Firebase by {session.get('email')}")
            except Exception as e:
                print(f"Firebase write error: {e}")
                return jsonify({'error': 'Failed to write to database'}), 500
        else:
            # Demo mode: just log
            print("Demo mode — service data not saved to Firebase")
            print("Service data:", json.dumps(service_data, indent=2))

        return jsonify({'success': True, 'message': 'Service update published'}), 200

    except Exception as e:
        print(f"Publish service error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Placeholder routes for Bible Tools - will be implemented later
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

@app.route('/get_qr_data')
def get_qr_data():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # In a real app, you would retrieve the current session from Firebase or session storage
    # For simplicity, we'll return a placeholder - the frontend should handle this via WebSocket or polling
    return jsonify({'session_id': 'not_started'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)