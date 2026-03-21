# Craftworld Tools (Render Deployment Guide for Beginners)

This README is written as a **step-by-step, no-assumptions guide**.
If this is your first deploy ever, follow this exactly.

---

## 1) What this app is

This is a Flask web app (`app.py`) that:
- serves the UI and API routes,
- stores local app data in SQLite,
- optionally reads `CRAFTWORLD_JWT` from environment variables for token-based Craft World API calls.

---

## 2) Render setup (exact values)

Create a **Render Web Service** from this repo.

Use these settings:

- **Environment**: `Python 3`
- **Build Command**:
  ```bash
  pip install -r requirements.txt
  ```
- **Start Command**:
  ```bash
  gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
  ```

Why this start command?
- Render injects `PORT` automatically.
- `app:app` means: file `app.py`, Flask app object named `app`.

---

## 3) Persistent disk (IMPORTANT)

If you want saved users/sessions/boosts to survive deploys, attach a persistent disk.

In Render:
1. Open your service.
2. Go to **Disks**.
3. Add a disk (any size you want).
4. Mount path: **`/var/data`** (recommended).

Then set env var:

- `DB_PATH=/var/data/craftworld_tools.db`

### Why this matters
- The app defaults to `/data/craftworld_tools.db` if `DB_PATH` is not set.
- On Render, you should point DB to your mounted disk path (`/var/data/...`) so data persists.

---

## 4) Environment variables (all of them)

Set these in Render **Environment** tab.

### Required

1. `DB_PATH`
   - Recommended value on Render:
     ```
     /var/data/craftworld_tools.db
     ```
   - This is your SQLite file location.

### Optional (only if you want server-side JWT fallback)

2. `CRAFTWORLD_JWT`
   - Value: your Craft World JWT token.
   - If not set, features that require `get_jwt()` fallback can fail unless token is supplied per request.

### Provided by Render automatically (do not manually set)

3. `PORT`
   - Render injects this automatically.
   - Gunicorn binds to this value in the start command.

---

## 5) One-click copy/paste values

If you just want the shortest version:

- Build:
  ```bash
  pip install -r requirements.txt
  ```
- Start:
  ```bash
  gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
  ```
- Disk mount path:
  ```
  /var/data
  ```
- Env:
  ```
  DB_PATH=/var/data/craftworld_tools.db
  CRAFTWORLD_JWT=<optional>
  ```

---

## 6) Local run (if you want to test before deploy)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DB_PATH="$(pwd)/craftworld_tools.db"
python app.py
```

Then open:
- `http://127.0.0.1:5000`

---

## 7) Common mistakes and fixes

### Mistake: “App deployed but data resets every deploy”
Fix:
- Attach persistent disk.
- Set `DB_PATH=/var/data/craftworld_tools.db`.

### Mistake: “Service starts locally but fails on Render”
Fix:
- Use Gunicorn start command (not `python app.py`).
- Make sure start command binds to `$PORT`.

### Mistake: “JWT-related calls fail”
Fix:
- Set `CRAFTWORLD_JWT` in Render env vars, or
- pass per-user bearer tokens in requests where applicable.

---

## 8) Runtime behavior notes

- SQLite DB tables are auto-created on startup.
- App has a hardcoded Flask `secret_key` in source right now (works, but for production security you should move this to an environment variable in code in a future update).
- Flask debug mode appears only when running `python app.py` directly; Render uses Gunicorn in production mode.

---

## 9) Deployment checklist

Before clicking deploy, verify:

- [ ] Build command is exactly `pip install -r requirements.txt`
- [ ] Start command is exactly `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
- [ ] Persistent disk is attached
- [ ] Disk mount path is `/var/data`
- [ ] `DB_PATH=/var/data/craftworld_tools.db` is set
- [ ] (Optional) `CRAFTWORLD_JWT` is set

If all 6 are correct, you should be good.
