# Snoopy Clipper — siap deploy ke VPS mana pun (1 image, tanpa build step frontend)
FROM python:3.11-slim

# ffmpeg = render/subtitle/preview; fonts = burn-in caption ASS tidak pakai font acak
# curl+unzip = memasang deno (runtime JS untuk challenge YouTube).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-liberation git curl unzip ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Runtime JS (EJS) — WAJIB untuk YouTube sejak yt-dlp 2025+.
# Tanpa ini, client android_vr menjawab UNPLAYABLE dan yt-dlp mati dengan
# "This video is not available" (khas video "Made for Kids"). Fatal juga di
# container: install-nya senyap, jadi tidak ada yang sadar sampai job gagal.
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh \
    && deno --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY tests ./tests

ENV PYTHONUNBUFFERED=1
# deno di /usr/local/bin sudah ada di PATH image ini; set eksplisit biar aman.
ENV PATH="/usr/local/bin:${PATH}"
ENV JS_RUNTIMES=deno
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
