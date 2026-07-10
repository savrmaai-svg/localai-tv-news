# 📺 LocalAI TV — Telugu News Video Generator

Turn a NotebookLM "Brief" clip into a broadcast-style **Telugu news video** in one click.

Upload a video and the tool:
- **Auto-detects the section cards** (the big number cards 1–5) and inserts a **2-sec filler** before each — no timestamps needed
- Overlays a **slanted red label + non-stop scrolling ticker** (Telugu shaped by Chrome/Playwright for crisp, correct rendering; libass fallback)
- Adds a **top-right animated logo** (PNG or looping video/GIF)
- **Auto-removes** NotebookLM's `notebooklm.google.com` endcard
- Keeps the **fillers clean** (strip/ticker only on content), exactly like a real news channel

Output: continuous **1920×1080** news video.

---

## Run locally

**Windows** (a full ffmpeg build with libass is auto-detected if placed under `Downloads/ffmpeg-*`; otherwise system `ffmpeg` on PATH is used):

```bash
pip install -r requirements.txt
python -m playwright install chromium      # for the Chrome-rendered ticker (optional; libass fallback otherwise)
streamlit run news_app.py --server.port 8502
```

**Linux / VPS:**

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
pip install -r requirements.txt
python -m playwright install --with-deps chromium
streamlit run news_app.py --server.port 8502 --server.address 0.0.0.0
```

Open `http://localhost:8502`.

---

## Deploy 24/7

This app is **CPU/RAM heavy** (multi-minute ffmpeg renders + a headless browser).

- **Recommended — a VPS / AWS box** (2–4 GB RAM): reliable 24/7. Install ffmpeg + `playwright install --with-deps chromium`, then run behind `systemd` or `pm2`, optionally with a reverse proxy. This is the right host for full 9-minute renders.
- **Streamlit Community Cloud** (free): works for **light/demo** use — `packages.txt` installs ffmpeg and the app auto-falls back to libass (Noto font is bundled) if Chromium isn't available. Full 9-minute renders may be slow or hit the free-tier resource limits.

Bundled font: `fonts/NotoSansTelugu-Bold.ttf` (SIL OFL). Chrome renders the ticker; the libass fallback uses this same Noto font, so Telugu shapes correctly on Linux too.

---

## Files
- `news_app.py` — Streamlit UI + the whole render pipeline (ffmpeg)
- `pw_render.py` — renders the strip's Telugu (red label + ticker) with Chrome/Playwright
- `fonts/` — Noto Sans Telugu Bold
- `requirements.txt`, `packages.txt`, `.streamlit/config.toml` — deploy config
