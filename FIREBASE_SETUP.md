# Firebase Setup Guide for Attendance System

## Step 1: Create Firebase Project
1. Go to https://console.firebase.google.com/
2. Click "Add project" and follow the setup wizard
3. Note your project ID (you'll need it later)

## Step 2: Enable Services
1. In your Firebase project console:
   - Enable Authentication (Email/Password provider)
   - Enable Realtime Database (start in test mode for development)
   - Enable Firestore if needed (though we're using Realtime Database)

## Step 3: Get Service Account Key
1. In Firebase console, go to Project Settings (gear icon)
2. Select the "Service accounts" tab
3. Click "Generate new private key"
4. Save the JSON file as `serviceAccountKey.json` in your project root
5. This replaces the placeholder file we created

## Step 4: Get Firebase Configuration Values
1. In Firebase console, go to Project Settings
2. Select the "General" tab
3. Under "Your apps", click the web icon (</>) to register a web app
4. Register the app and copy the configuration values
5. You'll need:
   - apiKey
   - authDomain
   - projectId
   - storageBucket
   - messagingSenderId
   - appId
   - databaseURL (found in Realtime Database section)

## Step 5: Update Environment Variables
Edit your `.env` file with the actual values:
```
FLASK_SECRET_KEY=your-secret-key-here-change-in-production
FIREBASE_API_KEY=your_actual_api_key
FIREBASE_AUTH_DOMAIN=your-project-id.firebaseapp.com
FIREBASE_DATABASE_URL=https://your-project-id-default-rtdb.firebaseio.com
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_STORAGE_BUCKET=your-project-id.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your-messaging-sender-id
FIREBASE_APP_ID=1:your-project-id:web:your-app-id
```

## Step 6: Set Up Firebase Authentication Users
1. In Firebase console, go to Authentication > Users
2. Click "Add user" and create an admin account with email/password
3. Note: You can also allow new user sign-ups in the Authentication settings

## Step 7: Test the Application
1. Make sure your serviceAccountKey.json and .env are properly configured
2. Run: `python app.py`
3. Visit http://localhost:5000
4. Login with the email/password you created in Firebase
5. Click "Start Service" to generate a session and QR code

## Troubleshooting:
- If you see Firebase initialization errors, double-check your serviceAccountKey.json format
- Ensure your Realtime Database is in test mode or has appropriate rules
- Check that the databaseURL in your .env matches your Firebase instance
- For authentication issues, verify the email/password exists in Firebase Auth

## Security Notes:
- Never commit serviceAccountKey.json or .env to version control
- In production, use proper secret management
- Restrict database rules appropriately for your use case