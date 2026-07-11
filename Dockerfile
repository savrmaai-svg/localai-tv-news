# LocalAI TV — Telugu News Generator on Hugging Face Spaces (Docker SDK, free CPU / 16 GB RAM)
FROM python:3.11-slim

# System deps: ffmpeg + system Chromium (the app launches /usr/bin/chromium via Playwright)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg chromium \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (better layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code (news_app.py, pw_render.py, fonts/, .streamlit/, etc.)
COPY . .

# Writable caches for Streamlit / Playwright (HF runs the container non-root-friendly)
ENV HOME=/tmp \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    XDG_CACHE_HOME=/tmp/.cache

# HF Spaces serves the app on port 7860
EXPOSE 7860
CMD ["streamlit", "run", "news_app.py", \
     "--server.port=7860", "--server.address=0.0.0.0", "--server.enableCORS=false"]
