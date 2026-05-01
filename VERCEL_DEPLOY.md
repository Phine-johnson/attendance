# Vercel Deployment Checklist

## ✅ Ready to Deploy

Your Redemption Presby attendance system is ready for Vercel deployment.

## Pre-Deployment

1. **Create a GitHub repository** (private recommended)
   ```bash
   git init
   git add .
   git commit -m "Initial commit - Redemption Presby Attendance System"
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

2. **Get Firebase service account JSON**
   - In Firebase Console → Project Settings → Service Accounts
   - Click "Generate new private key"
   - Save as `serviceAccountKey.json` (already in project)

## Vercel Deployment Steps

### Option A: One-Click (Easiest)
1. Go to [vercel.com/new](https://vercel.com/new)
2. Import your GitHub repository
3. Configure environment variables (see below)
4. Deploy

### Option B: Vercel CLI
```bash
npm i -g vercel
vercel --prod
```

## Vercel Environment Variables

In Vercel Dashboard → Project Settings → Environment Variables, add:

### Required (Production)
| Variable | Value |
|----------|-------|
| `FLASK_SECRET_KEY` | Any random 32+ character string |
| `FIREBASE_API_KEY` | From Firebase project settings |
| `FIREBASE_AUTH_DOMAIN` | `your-project.firebaseapp.com` |
| `FIREBASE_DATABASE_URL` | `https://your-project-default-rtdb.firebaseio.com` |
| `FIREBASE_PROJECT_ID` | Your Firebase project ID |
| `FIREBASE_STORAGE_BUCKET` | `your-project.appspot.com` |
| `FIREBASE_MESSAGING_SENDER_ID` | From Firebase project settings |
| `FIREBASE_APP_ID` | From Firebase project settings |

### Optional (for service account)
| Variable | Value |
|----------|-------|
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Full contents of serviceAccountKey.json |

## Important Notes

⚠️ **Security**: Vercel stores environment variables securely. Do NOT commit `serviceAccountKey.json` or `.env` to git.

✅ **Demo Mode**: Without Firebase credentials, app runs in demo mode (accepts any login).

📁 **Static Files**: CSS and logo are automatically served from `/static/`

🌐 **After Deployment**:
- Vercel provides a `*.vercel.app` URL
- Access: `https://your-project.vercel.app/login`
- Update any Firebase auth domain rules if needed

## Troubleshooting

**Build fails**: Ensure `requirements.txt` includes `flask`, `firebase-admin`, `python-dotenv`

**Firebase auth errors**: Check that Firebase Auth is enabled in console

**Images not loading**: Ensure `static/presby logo.png` is included in build (not in .gitignore)

Need help? Check Vercel logs in dashboard for error details.
