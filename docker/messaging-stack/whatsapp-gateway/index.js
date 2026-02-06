const express = require("express");
const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");

const PORT = process.env.PORT || 3000;
const DATA_DIR = process.env.DATA_DIR || "/data";
const QUEUE_MAX_AGE_MS = 60 * 60 * 1000; // 1 hour
const QUEUE_RETRY_INTERVAL_MS = 30 * 1000; // 30 seconds

// --- State ---

let connected = false;
let latestQr = null;
let clientInfo = null;
const messageQueue = []; // { to, message, addedAt }

// --- WhatsApp Client ---

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: `${DATA_DIR}/.wwebjs_auth` }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  },
});

client.on("qr", (qr) => {
  latestQr = qr;
  console.log("[whatsapp] QR code received — scan with your phone:");
  qrcode.generate(qr, { small: true });
});

client.on("ready", () => {
  connected = true;
  latestQr = null;
  clientInfo = client.info || {};
  console.log(`[whatsapp] Connected as ${clientInfo.pushname || "unknown"}`);
});

client.on("authenticated", () => {
  console.log("[whatsapp] Session authenticated");
});

client.on("auth_failure", (msg) => {
  console.error("[whatsapp] Authentication failed:", msg);
});

client.on("disconnected", (reason) => {
  connected = false;
  clientInfo = null;
  console.warn("[whatsapp] Disconnected:", reason);
});

client.initialize().catch((err) => {
  console.error("[whatsapp] Failed to initialize:", err);
});

// --- Message Queue ---

function formatPhoneNumber(phone) {
  // Strip everything except digits
  const digits = phone.replace(/\D/g, "");
  return `${digits}@c.us`;
}

async function sendMessage(to, message) {
  const chatId = formatPhoneNumber(to);
  const result = await client.sendMessage(chatId, message);
  return result.id._serialized;
}

async function processQueue() {
  if (!connected || messageQueue.length === 0) return;

  const now = Date.now();
  // Process from front of queue
  while (messageQueue.length > 0) {
    const item = messageQueue[0];

    // Drop messages older than max age
    if (now - item.addedAt > QUEUE_MAX_AGE_MS) {
      messageQueue.shift();
      console.warn(`[queue] Dropped expired message to ${item.to}`);
      continue;
    }

    try {
      await sendMessage(item.to, item.message);
      messageQueue.shift();
      console.log(`[queue] Delivered queued message to ${item.to}`);
    } catch (err) {
      console.warn(`[queue] Retry failed for ${item.to}: ${err.message}`);
      break; // Stop processing, will retry next interval
    }
  }
}

setInterval(processQueue, QUEUE_RETRY_INTERVAL_MS);

// --- Express API ---

const app = express();
app.use(express.json());

app.get("/health", (_req, res) => {
  res.json({ status: "ok", connected, queueSize: messageQueue.length });
});

app.get("/status", (_req, res) => {
  res.json({
    connected,
    info: clientInfo
      ? { pushname: clientInfo.pushname, phone: clientInfo.wid?.user }
      : null,
    queueSize: messageQueue.length,
  });
});

app.get("/qr", (_req, res) => {
  if (connected) {
    return res.status(404).json({ error: "Already authenticated" });
  }
  if (!latestQr) {
    return res
      .status(404)
      .json({ error: "No QR code available yet — client is initializing" });
  }
  // Return QR string (caller can render however they want)
  res.json({ qr: latestQr });
});

app.post("/send", async (req, res) => {
  const { to, message } = req.body || {};

  if (!to || !message) {
    return res.status(400).json({ ok: false, error: "'to' and 'message' are required" });
  }

  // If disconnected, queue for later delivery
  if (!connected) {
    messageQueue.push({ to, message, addedAt: Date.now() });
    console.log(`[queue] Client disconnected — queued message to ${to}`);
    return res.json({
      ok: true,
      queued: true,
      message: "Client disconnected — message queued for delivery",
    });
  }

  try {
    const messageId = await sendMessage(to, message);
    console.log(`[send] Message sent to ${to} (${messageId})`);
    res.json({ ok: true, messageId });
  } catch (err) {
    console.error(`[send] Failed to send to ${to}:`, err.message);
    // Queue on failure (e.g. transient error)
    messageQueue.push({ to, message, addedAt: Date.now() });
    res.status(500).json({ ok: false, error: err.message, queued: true });
  }
});

app.listen(PORT, () => {
  console.log(`[gateway] WhatsApp gateway listening on port ${PORT}`);
});
