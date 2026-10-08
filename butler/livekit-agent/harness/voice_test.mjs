// Presses the app's mic like a person: hold, start "talking" at the same instant,
// let go. Reports what Butler actually heard on each press (from the fake API).
//   SPEECH=short.wav EXPECT=turn,off,kitchen,lights LATENCY_MS=50 node voice_test.mjs
import { chromium } from 'playwright-core'

const APP = process.env.APP_URL || 'http://localhost:15173/'
const FAKE = process.env.FAKE_URL || 'http://localhost:18000'
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const SPEECH = process.env.SPEECH || 'speech.wav'
const EXPECTED = (process.env.EXPECT || '1,2,3,4,5,6,7,8').split(',')
const LATENCY_MS = Number(process.env.LATENCY_MS || 0)

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--autoplay-policy=no-user-gesture-required', '--use-fake-ui-for-media-stream'],
})
const ctx = await browser.newContext({ permissions: ['microphone'] })
await ctx.addInitScript(({ fake, speech, debug }) => {
  localStorage.setItem('butler-auth', JSON.stringify({
    state: { tokens: { accessToken: 'test', refreshToken: 'test', expiresAt: Date.now() + 864e5 },
             isAuthenticated: true, hasCompletedOnboarding: true, role: 'admin' }, version: 0 }))
  localStorage.setItem('butler-device-settings', JSON.stringify({
    state: { voiceMode: 'push-to-talk', audioInputDevice: null, audioOutputDevice: null, speakReplies: true }, version: 0 }))
  if (debug) for (const n of ['livekit', 'livekit-participant', 'livekit-room']) localStorage.setItem('loglevel:' + n, 'DEBUG')
  // A fake microphone: silence until __speak() plays the test sentence into it
  let ac, dest, buf
  const ready = (async () => {
    ac = new AudioContext({ sampleRate: 48000 })
    dest = ac.createMediaStreamDestination()
    dest.channelCount = 1 // a real mic is mono
    buf = await ac.decodeAudioData(await (await fetch(`${fake}/harness/${speech}`)).arrayBuffer())
  })()
  window.__speak = async () => { await ready; const s = ac.createBufferSource(); s.buffer = buf; s.connect(dest); s.start(); return buf.duration }
  const real = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
  navigator.mediaDevices.getUserMedia = async (c) => {
    if (!c?.audio) return real(c)
    await ready
    return new MediaStream([dest.stream.getAudioTracks()[0].clone()])
  }
}, { fake: FAKE, speech: SPEECH, debug: !!process.env.DEBUG_LK })

const page = await ctx.newPage()
page.on('pageerror', e => console.log('  [page error]', e.message))
page.on('console', m => { if (m.type() === 'error' || (process.env.DEBUG_LK && /preconnect|agent/i.test(m.text()))) console.log('  [page]', m.text().slice(0, 160)) })
if (LATENCY_MS) {
  // Like reaching the Mini over the internet: delays the token fetch and LiveKit signalling
  const cdp = await ctx.newCDPSession(page)
  await cdp.send('Network.enable')
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: LATENCY_MS, downloadThroughput: -1, uploadThroughput: -1 })
}
await page.goto(APP)
const mic = page.getByRole('button', { name: /Start voice|Stop listening/ })
await mic.waitFor({ timeout: 30000 })
await page.waitForTimeout(1500)

const getHeard = async () => (await fetch(`${FAKE}/harness/heard`)).json()

async function press(label) {
  const before = (await getHeard()).length
  const box = await mic.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  const t0 = Date.now()
  await page.mouse.down()
  const dur = await page.evaluate(() => window.__speak())
  await page.waitForTimeout(dur * 1000 + 400)
  await page.mouse.up()
  let heard = null
  for (let i = 0; i < 100 && !heard; i++) {
    await page.waitForTimeout(200)
    const all = await getHeard()
    if (all.length > before) heard = all.slice(before)
  }
  await page.waitForTimeout(2500) // let any second request (a split turn) show up
  heard = (await getHeard()).slice(before)
  const text = heard.map(h => h.text).join(' | ')
  const words = text.toLowerCase().match(/[a-z0-9]+/g) || []
  const missing = EXPECTED.filter(w => !words.includes(w))
  const reply = heard.length ? ((heard[0].t * 1000 - t0) / 1000 - dur).toFixed(1) + 's after you stopped' : 'never'
  const ok = !missing.length && heard.length === 1
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: heard ${JSON.stringify(text)}` +
    `${missing.length ? ` | missing ${missing.join(',')}` : ''}${heard.length > 1 ? ` | split into ${heard.length} requests` : ''} | ${reply}`)
  await page.waitForTimeout(2000)
  return ok
}

const results = [await press('press 1 (cold)')]
if (!process.env.COLD_ONLY) results.push(await press('press 2 (warm)'), await press('press 3 (warm)'))
await browser.close()
process.exit(results.every(Boolean) ? 0 : 1)
