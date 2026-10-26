// Regenerates the README screenshots and the GitHub social card from synthetic demo data.
//
//   npm run screenshots        (from frontend/, with the garmates CLI on PATH)
//
// Starts its own server against a throwaway data directory, so real data is never touched.
// Uses an installed browser: Edge on Windows, Chrome elsewhere (PLAYWRIGHT_CHANNEL overrides;
// set it to "chromium" after `npx playwright install chromium`).

import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..', '..')
const out = path.join(root, 'docs', 'images')
const port = Number(process.env.SCREENSHOT_PORT ?? 8765)
const base = `http://127.0.0.1:${port}`
const channel = process.env.PLAYWRIGHT_CHANNEL ?? (process.platform === 'win32' ? 'msedge' : 'chrome')
const headers = { 'X-Garmates-Request': '1' }

const DESKTOP = { width: 1440, height: 900 }
const MOBILE = { width: 390, height: 844 }

const isoDay = (offset = 0) => {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function startServer(dataDir) {
  if (!existsSync(path.join(root, 'frontend', 'dist', 'index.html'))) {
    throw new Error('Build the frontend first: npm run build')
  }
  const env = {
    ...process.env,
    GARMATES_DATA_DIR: dataDir,
    GARMATES_SYNC_INTERVAL_MINUTES: '0',
    GARMATES_HOST: '127.0.0.1',
    GARMATES_PORT: String(port),
  }
  delete env.GARMATES_SECRET_KEY
  const server = spawn('garmates', ['serve'], { env, cwd: root, shell: process.platform === 'win32' })
  server.stderr.on('data', (chunk) => {
    if (/error|traceback/i.test(String(chunk))) process.stderr.write(chunk)
  })
  return server
}

async function waitForServer() {
  for (let i = 0; i < 120; i++) {
    try {
      const res = await fetch(`${base}/api/auth/state`)
      if (res.ok) return
    } catch {
      // not up yet
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`Server didn't start on ${base}`)
}

async function seed(request) {
  const setup = await request.post('/api/auth/setup', {
    headers,
    data: { name: 'Admin', username: 'admin', password: 'screenshots-only' },
  })
  if (!setup.ok()) throw new Error(`Setup failed: ${await setup.text()}`)
  const admin = (await setup.json()).id
  const demo = await request.post('/api/demo', { headers })
  const [alex, sam] = (await demo.json()).ids
  // Match the logo: the two people take the first two palette colours.
  for (const [id, slot] of [[admin, 7], [alex, 0], [sam, 1]]) {
    if (id) await request.patch(`/api/people/${id}`, { headers, data: { color_slot: slot } })
  }

  for (const goal of [
    { person_id: alex, metric_key: 'steps', target: 70000, period: 'week' },
    { person_id: alex, metric_key: 'sleep_hours', target: 7, period: 'week' },
    { person_id: sam, metric_key: 'workouts', target: 4, period: 'week' },
    { person_id: sam, metric_key: 'intensity_minutes', target: 150, period: 'week' },
  ]) {
    await request.post('/api/goals', { headers, data: goal })
  }
  await request.post('/api/challenges', {
    headers,
    data: {
      name: 'October step-off',
      metric_key: 'steps',
      scoring: 'total',
      start_date: isoDay(-20),
      end_date: isoDay(10),
      participant_ids: [alex, sam],
    },
  })

  const activities = await (await request.get(`/api/activities?people=${alex}&start=${isoDay(-30)}&end=${isoDay()}`)).json()
  const run = activities.activities.find((a) => a.sport === 'run' && a.distance_m > 8000)
    ?? activities.activities.find((a) => a.distance_m)
  return { run: run?.activity_id }
}

async function settle(page) {
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(1800) // chart animations
}

async function shoot(context, url, file, { dark = false } = {}) {
  const page = await context.newPage()
  await page.emulateMedia({ colorScheme: dark ? 'dark' : 'light' })
  await page.goto(url)
  await settle(page)
  await page.screenshot({ path: path.join(out, file) })
  await page.close()
  console.log(`  ${file}`)
}

async function socialCard(browser) {
  const hero = readFileSync(path.join(out, 'overview-dark.png')).toString('base64')
  const logo = readFileSync(path.join(root, 'docs', 'images', 'logo.svg'), 'utf8')
  const html = readFileSync(path.join(here, 'social-card.html'), 'utf8')
    .replace('{{LOGO}}', logo)
    .replace('{{HERO}}', `data:image/png;base64,${hero}`)
  const page = await browser.newPage({ viewport: { width: 1280, height: 640 } })
  await page.setContent(html, { waitUntil: 'load' })
  await page.screenshot({ path: path.join(out, 'social-preview.png') })
  await page.close()
  const kb = Math.round(statSync(path.join(out, 'social-preview.png')).size / 1024)
  console.log(`  social-preview.png (${kb} KB${kb > 1000 ? ' - over GitHub\'s 1 MB limit!' : ''})`)
}

const dataDir = mkdtempSync(path.join(tmpdir(), 'garmates-screenshots-'))
const server = startServer(dataDir)
let browser
try {
  await waitForServer()
  mkdirSync(out, { recursive: true })
  browser = await chromium.launch({ channel })
  const context = await browser.newContext({ baseURL: base, viewport: DESKTOP })
  const { run } = await seed(context.request)

  console.log('Writing to docs/images/')
  await shoot(context, '/', 'overview-light.png')
  await shoot(context, '/', 'overview-dark.png', { dark: true })
  await shoot(context, '/compare', 'compare.png')
  await shoot(context, '/sleep?range=90d', 'sleep.png')
  await shoot(context, '/digest', 'digest.png')
  await shoot(context, '/goals', 'goals.png')
  await shoot(context, `/day?date=${isoDay(-1)}`, 'day.png')
  if (run) await shoot(context, `/workouts/${run}`, 'activity.png')

  const mobile = await browser.newContext({ baseURL: base, viewport: MOBILE, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
  await mobile.addCookies(await context.cookies())
  await shoot(mobile, '/', 'mobile.png')

  await socialCard(browser)
} finally {
  await browser?.close()
  if (process.platform === 'win32') spawn('taskkill', ['/pid', String(server.pid), '/t', '/f'])
  else server.kill()
  await new Promise((resolve) => setTimeout(resolve, 1500))
  rmSync(dataDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 })
}
