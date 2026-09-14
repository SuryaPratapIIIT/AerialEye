# Hugging Face Backend Keep-Alive Guide

Hugging Face Spaces (CPU / Docker tier) automatically pause (sleep) after ~15-30 minutes of inactivity. When a request comes in to a sleeping Space, it undergoes a cold start (15-40 seconds).

To ensure **AerialEye Backend** (`https://prfct-suraj-aerialeye-backend.hf.space`) stays awake 24/7 without ever going to sleep, the following automated solutions have been set up.

---

## ⚡ Method 1: GitHub Actions Cron (Recommended & Automated)

A GitHub Actions workflow is included at `.github/workflows/keep_alive.yml`.

### How it works:
1. Every **12 minutes**, GitHub Actions automatically executes a lightweight `curl` ping to `https://prfct-suraj-aerialeye-backend.hf.space/api/health`.
2. This runs **completely free in the cloud 24/7** without needing your local computer or any server to stay on.

### Setup:
- Simply `git push` this repository to your GitHub repository.
- GitHub will automatically enable the `.github/workflows/keep_alive.yml` workflow.
- You can manually test it anytime by going to your GitHub Repo -> **Actions** tab -> **Keep Hugging Face Backend Awake** -> **Run workflow**.

---

## 🐍 Method 2: Standalone Python Keep-Alive Daemon Script

A standalone Python script is provided at `scripts/keep_alive.py`. It uses standard Python libraries (no `pip install` required).

### Commands:

```bash
# 1. Run continuously as a background daemon (pings every 10 minutes)
python scripts/keep_alive.py

# 2. Run once (ideal for OS crontab or task scheduler)
python scripts/keep_alive.py --single

# 3. Customize interval (e.g. ping every 5 minutes = 300 seconds)
python scripts/keep_alive.py --interval 300

# 4. Custom endpoint
python scripts/keep_alive.py --url https://prfct-suraj-aerialeye-backend.hf.space/api/health
```

---

## 🌐 Method 3: Free Web Cron Services (Zero Setup Backup)

If you'd like a 3rd party web service to ping your Space:

1. **[cron-job.org](https://cron-job.org)** (Free)
   - Sign up for a free account.
   - Create a new Cronjob.
   - **URL**: `https://prfct-suraj-aerialeye-backend.hf.space/api/health`
   - **Execution Schedule**: Every 10 or 12 minutes.

2. **[UptimeRobot](https://uptimerobot.com)** (Free)
   - Create a free account.
   - Add New Monitor -> Type: **HTTP(s)**.
   - **URL**: `https://prfct-suraj-aerialeye-backend.hf.space/api/health`
   - **Monitoring Interval**: 5 minutes.

---

## 💻 Method 4: Frontend Pre-Warm on Web App Load

When users visit the AerialEye web application, `App.tsx` automatically calls `pingBackendHealth()` upon initial mount to wake up the backend space in case it was paused.
