import os
import json

# This script handles Vercel deployment configuration
# Set the FIREBASE_SERVICE_ACCOUNT_JSON environment variable with the full JSON content

content = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
if content:
    try:
        key = json.loads(content)
        print(f"✅ Firebase service account loaded for project: {key.get('project_id', 'unknown')}")
    except json.JSONDecodeError:
        print("❌ Invalid JSON in FIREBASE_SERVICE_ACCOUNT_JSON")
else:
    print("ℹ️  FIREBASE_SERVICE_ACCOUNT_JSON not set - will use serviceAccountKey.json if present")

print("Vercel config verified")
