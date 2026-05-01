# Redemption Presby Congregation - Attendance System

A Flask-based web application for managing attendance at Redemption Presby Congregation, built with Firebase backend integration.

## Features

- Secure adminlogin with Firebase Authentication
- Generate QR codes for attendance sessions
- Real-time attendance tracking via Firebase Realtime Database
- Presbyterian Church of Ghana themed design

## Tech Stack

- **Backend**: Flask (Python)
- **Authentication**: Firebase Authentication
- **Database**: Firebase Realtime Database
- **Frontend**: HTML, Bootstrap 5, Custom CSS
- **Hosting**: Vercel

## Local Development

### Prerequisites

- Python 3.10+
- Firebase project with Authentication and Realtime Database enabled
- Service account key JSON file

### Setup

1. Clone the repository
2. Copy `.env.example` to `.env` and fill in values:
   ```
   FLASK_SECRET_KEY=your-secret-key
   FIREBASE_API_KEY=your-api-key
   FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
   FIREBASE_DATABASE_URL=https://your-project-default-rtdb.firebaseio.com
   FIREBASE_PROJECT_ID=your-project-id
   FIREBASE_STORAGE_BUCKET=your-project.appspot.com
   FIREBASE_MESSAGING_SENDER_ID=your-sender-id
   FIREBASE_APP_ID=your-app-id
   ```
3. Download Firebase service account key and save as `serviceAccountKey.json` in project root
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python app.py`
6. Visit: http://localhost:5000/login

## Deploy to Vercel

### One-Click Deploy

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new)

### Manual Deployment

1. Push code to GitHub repository
2. Import project in Vercel dashboard
3. Configure Environment Variables in Vercel (same as `.env`)
4. Add `serviceAccountKey.json` as a Vercel Secret/Environment variable:
   - Option A: Use Vercel secrets to store the JSON (recommended)
   - Option B: Upload the file via Vercel dashboard (if allowed)
5. Deploy

### Vercel Environment Variables

Add these in Vercel Project Settings → Environment Variables:

| Key | Value |
|-----|-------|
| `FLASK_SECRET_KEY` | Your secret key |
| `FIREBASE_API_KEY` | Firebase API key |
| `FIREBASE_AUTH_DOMAIN` | Firebase auth domain |
| `FIREBASE_DATABASE_URL` | Firebase database URL |
| `FIREBASE_PROJECT_ID` | Firebase project ID |
| `FIREBASE_STORAGE_BUCKET` | Firebase storage bucket |
| `FIREBASE_MESSAGING_SENDER_ID` | Firebase sender ID |
| `FIREBASE_APP_ID` | Firebase app ID |

## Project Structure

```
attendance/
├── app.py                 # Flask application
├── requirements.txt        # Python dependencies
├── vercel.json            # Vercel configuration
├── serviceAccountKey.json # Firebase service account (not in git)
├── .env                   # Environment variables (not in git)
├── static/
│   ├── styles.css        # Custom CSS
│   └── presby logo.png    # Church logo
└── templates/
    ├── login.html        # Login page
    └── dashboard.html    # Admin dashboard
```

## Usage

1. Login with Firebase admin credentials
2. Click "Start Service" to generate a QR code
3. Members scan QR to mark attendance
4. View real-time attendance records on dashboard

## Demo Mode

If Firebase credentials are not configured, the app runs in demo mode allowing any login.

## License

Proprietary - Redemption Presby Congregation
