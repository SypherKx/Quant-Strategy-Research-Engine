# 🚀 Free Cloud Deployment Guide

> Deploy your Quant Research Engine to Render.com for FREE permanent hosting.

---

## 🎯 Overview

**What This Does:**
- Runs your system 24/7 on the cloud
- Auto-starts/stops based on Indian market hours
- Accessible from anywhere via URL
- Completely FREE (Render's free tier)

**Free Tier Limits:**
- 750 hours/month (enough for 24/7)
- Sleeps after 15 min inactivity (wakes on request)
- 512 MB RAM
- Shared CPU

---

## 📋 Step-by-Step Deployment

### Step 1: Create GitHub Repository

1. Go to [github.com](https://github.com) and sign in
2. Click **"New Repository"**
3. Name it: `quant-research-engine`
4. Set to **Public** (or Private if you upgrade Render)
5. Click **"Create Repository"**

```bash
# In your project folder, run:
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/quant-research-engine.git
git push -u origin main
```

### Step 2: Create Render Account

1. Go to [render.com](https://render.com)
2. Click **"Get Started for Free"**
3. Sign up with GitHub (easiest)

### Step 3: Deploy to Render

**Option A: Blueprint (Recommended)**

1. Go to your Render Dashboard
2. Click **"New +"** → **"Blueprint"**
3. Connect your GitHub repo
4. Render will auto-detect `render.yaml`
5. Click **"Apply"**

**Option B: Manual Setup**

1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub repo
3. Configure:
   - **Name:** `quant-research-engine`
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python run.py`
   - **Plan:** Free

### Step 4: Set Environment Variables

In Render Dashboard → Your Service → **Environment**:

| Key | Value |
|-----|-------|
| `UPSTOX_API_KEY` | (your key) |
| `UPSTOX_API_SECRET` | (your secret) |
| `UPSTOX_TOTP_SECRET` | (your TOTP secret) |
| `SYMBOLS` | `RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK` |
| `INITIAL_CAPITAL` | `100000` |

> **Note:** Leave API fields empty to run in Mock Mode (testing only)

### Step 5: Deploy!

1. Click **"Manual Deploy"** → **"Deploy latest commit"**
2. Wait 2-3 minutes for build
3. Your app will be live at: `https://quant-research-engine.onrender.com`

---

## ⏰ Keeping It Running (Cron Jobs)

Render free tier sleeps after 15 minutes of inactivity.
To keep it awake during market hours (9:15 AM - 3:30 PM IST):

### Option 1: UptimeRobot (FREE)

1. Go to [uptimerobot.com](https://uptimerobot.com)
2. Create free account
3. Add new monitor:
   - **Monitor Type:** HTTP(s)
   - **URL:** `https://your-app.onrender.com/api/status`
   - **Interval:** 5 minutes
4. This pings your app every 5 minutes, keeping it awake!

### Option 2: Cron-Job.org (FREE)

1. Go to [cron-job.org](https://cron-job.org)
2. Create free account
3. Create cron job:
   - **URL:** `https://your-app.onrender.com/api/status`
   - **Schedule:** Every 5 minutes
   - **Only during:** Mon-Fri, 9:00-16:00 IST

---

## 📊 Accessing Your Dashboard

Once deployed:

| URL | What It Shows |
|-----|---------------|
| `https://your-app.onrender.com` | Main Dashboard |
| `https://your-app.onrender.com/docs` | API Documentation |
| `https://your-app.onrender.com/api/report` | Generate Weekly Report |

---

## 🔧 Troubleshooting

### "App not starting"
- Check **Logs** in Render Dashboard
- Usually missing environment variables

### "API errors"
- Verify Upstox credentials
- Check if market is open

### "Free tier usage exceeded"
- 750 hours/month = ~31 days continuous
- Should be enough, but monitor usage

---

## 🔄 Updating Your App

When you push changes to GitHub:

```bash
git add .
git commit -m "Your changes"
git push
```

Render auto-deploys on every push!

---

## 💡 Pro Tips

1. **Start with Mock Mode**: Leave API keys empty initially
2. **Monitor Logs**: Check Render logs daily for issues
3. **Set Alerts**: Configure Render alerts for failed deployments
4. **Weekly Reports**: Visit `/api/report` every week for analysis

---

## 🎓 Why This Works

```
┌─────────────────────────────────────────────────────────────┐
│                     YOUR LOCAL MACHINE                       │
│                           ↓                                  │
│                        GitHub                                │
│                           ↓                                  │
│        ┌─────────────────────────────────────┐              │
│        │         RENDER.COM (FREE)            │              │
│        │   ┌───────────────────────────┐     │              │
│        │   │ Python + FastAPI + SQLite │     │              │
│        │   │ Running 24/7 (mostly)     │     │              │
│        │   └───────────────────────────┘     │              │
│        └─────────────────────────────────────┘              │
│                           ↓                                  │
│                     YOUR BROWSER                             │
│              (Access from anywhere!)                         │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ Deployment Checklist

- [ ] Code pushed to GitHub
- [ ] Render account created
- [ ] Web service deployed
- [ ] Environment variables set
- [ ] UptimeRobot/Cron monitoring setup
- [ ] Dashboard accessible
- [ ] Weekly report generating

---

*That's it! Your quant research engine is now live on the cloud.*
