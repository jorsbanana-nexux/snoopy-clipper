# Snoopy Clipper — siap deploy ke VPS mana pun (1 image, tanpa build step frontend)
FROM python:3.11-slim

# ffmpeg = render/subtitle/preview; fonts = burn-in caption ASS tidak pakai font acak
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-liberation git && apt-get clean

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY tests ./tests

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
