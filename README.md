# Nepal Chunab 2082 — Deployment Guide
## Live on Render.com in ~10 minutes, completely free

---

## What you need
- A free GitHub account → https://github.com
- A free Render account → https://render.com (sign up with GitHub)

---

## Step 1 — Create a GitHub repository

1. Go to https://github.com/new
2. Name it `nepal-chunab-2082` (or anything you like)
3. Set it to **Public**
4. Click **Create repository**

---

## Step 2 — Upload the project files

On the new repository page, click **uploading an existing file** and upload ALL these files at once:

```
Dockerfile
render.yaml
requirements.txt
server.py
dashboard.html
balen.jpg
oli.jpg
rsp_logo.png
uml_logo.jpg
```

Click **Commit changes**.

---

## Step 3 — Deploy on Render

1. Go to https://dashboard.render.com
2. Click **New +** → **Web Service**
3. Click **Connect a repository** → select your `nepal-chunab-2082` repo
4. Render will auto-detect the `Dockerfile` — just confirm these settings:
   - **Name:** nepal-chunab-2082
   - **Region:** Singapore (closest to Nepal)
   - **Branch:** main
   - **Plan:** Free
5. Click **Deploy Web Service**

---

## Step 4 — Wait for the build (~5 minutes)

Render will:
1. Build the Docker image (installs Python, Flask, Playwright, Chromium)
2. Start the server
3. Begin scraping election data

You can watch the build log in real time on the Render dashboard.

---

## Step 5 — Open your website

Once deployed, Render gives you a free URL like:
```
https://nepal-chunab-2082.onrender.com
```

Open this on any device — phone, tablet, laptop — and share it with anyone!

---

## Important notes

**Free tier sleep:** Render's free tier sleeps after 15 minutes of no traffic.
The first visit after sleep takes ~30 seconds to wake up. Once someone is
actively viewing the dashboard (it pings every 5 minutes), it stays awake.

**Re-deploy after changes:** Any time you push new files to GitHub, Render
automatically rebuilds and redeploys — no manual action needed.

**Logs:** View live server logs at:
Render Dashboard → your service → **Logs** tab

---

## Your URLs once deployed

| URL | What it does |
|-----|-------------|
| `https://your-app.onrender.com/` | The live election dashboard |
| `https://your-app.onrender.com/api/status` | Server health check |
| `https://your-app.onrender.com/api/summary` | National seat tally (JSON) |
| `https://your-app.onrender.com/api/regions` | All constituency data (JSON) |
