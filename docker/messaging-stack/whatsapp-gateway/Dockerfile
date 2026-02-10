FROM node:20-slim

# whatsapp-web.js uses Puppeteer which needs Chromium
RUN apt-get update && \
    apt-get install -y chromium curl --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PUPPETEER_SKIP_DOWNLOAD=true

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY index.js .

EXPOSE 3000
CMD ["node", "index.js"]
