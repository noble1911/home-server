# Calibre's ebook-convert behind a tiny HTTP API (server.py), for Send to Kindle.
# Kept out of butler-api's image: Calibre pulls in Qt and weighs several hundred MB.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends calibre python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Calibre needs a Qt platform even for command-line conversions.
ENV QT_QPA_PLATFORM=offscreen PYTHONUNBUFFERED=1

WORKDIR /app
COPY server.py .

USER nobody
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"

CMD ["python3", "server.py"]
