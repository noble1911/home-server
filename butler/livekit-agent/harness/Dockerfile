# The production agent image (../Dockerfile) plus what the harness needs: local
# Whisper standing in for Groq, and PyJWT for the fake Butler API, which mints
# LiveKit tokens with the real butler/api/auth.py. Code is mounted, not copied.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt faster-whisper pyjwt
