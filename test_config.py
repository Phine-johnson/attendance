# Test script to verify environment variables are loaded correctly
import os
from dotenv import load_dotenv

load_dotenv()

print("Environment Variables:")
print(f"FLASK_SECRET_KEY: {'SET' if os.environ.get('FLASK_SECRET_KEY') else 'NOT SET'}")
print(f"FIREBASE_API_KEY: {'SET' if os.environ.get('FIREBASE_API_KEY') else 'NOT SET'}")
print(f"FIREBASE_AUTH_DOMAIN: {os.environ.get('FIREBASE_AUTH_DOMAIN', 'NOT SET')}")
print(f"FIREBASE_DATABASE_URL: {os.environ.get('FIREBASE_DATABASE_URL', 'NOT SET')}")
print(f"FIREBASE_PROJECT_ID: {os.environ.get('FIREBASE_PROJECT_ID', 'NOT SET')}")
print(f"FIREBASE_STORAGE_BUCKET: {os.environ.get('FIREBASE_STORAGE_BUCKET', 'NOT SET')}")
print(f"FIREBASE_MESSAGING_SENDER_ID: {os.environ.get('FIREBASE_MESSAGING_SENDER_ID', 'NOT SET')}")
print(f"FIREBASE_APP_ID: {os.environ.get('FIREBASE_APP_ID', 'NOT SET')}")

# Test Firebase Admin SDK initialization
try:
    import firebase_admin
    from firebase_admin import credentials
    
    print("\nFirebase Admin SDK: AVAILABLE")
    
    if os.path.exists("serviceAccountKey.json"):
        print("serviceAccountKey.json: FOUND")
        try:
            cred = credentials.Certificate("serviceAccountKey.json")
            print("Service Account Certificate: VALID")
        except Exception as e:
            print(f"Service Account Certificate: INVALID - {e}")
    else:
        print("serviceAccountKey.json: NOT FOUND")
        
except ImportError:
    print("Firebase Admin SDK: NOT AVAILABLE")