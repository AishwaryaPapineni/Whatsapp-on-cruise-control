// Session 4.1 + 4.2 -- the WhatsApp socket: stage 1 (message in), 7 (human-like delay), 8 (send).
//
// Keeps the session client's behaviour (QR login, notify-only, kill switch, dry_run from
// config/settings.json, delay, independent allowlist check, LID -> phone for sending) and fixes:
//   * ES module: Baileys 7 is ESM-only; `require()` of it crashes on Node 18/20
//   * makeInMemoryStore no longer exists in Baileys 7 (removed import)
//   * routes by PHONE number when WhatsApp sends a LID JID (otherwise every contact = unknown)
//   * processes EVERY message in an upsert batch (the old code read only messages[0])
//   * skips backlog delivered after a reconnect (never answers yesterday's messages)
//   * forwards YOUR own typed messages to the bridge as from_me -> short-term context and
//     "the real you is here" (the old code dropped them, so the agent could talk over you)
//   * re-checks kill switch + dry_run AFTER the delay, right before sending
//   * cancels a pending reply if you type in that chat during the delay
//   * shows "typing…" during the delay, uses the bridge's length-based delay
//   * acknowledges each send to the bridge (/sent) -> rate limit + console "sent" status
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import axios from 'axios'
import dotenv from 'dotenv'
import pino from 'pino'
import QRCode from 'qrcode-terminal'
import makeWASocket, { DisconnectReason, useMultiFileAuthState } from '@whiskeysockets/baileys'
import { OwnEcho, clampDelayMs, getIsForwarded, getMessageText, getMessageType, isSystemContent, resolveRouteJid, sleep } from './lib.js'

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
dotenv.config({ path: path.join(ROOT, '.env'), quiet: true })

const logger = pino({ level: 'info', timestamp: pino.stdTimeFunctions.isoTime })
const authDir = path.join(ROOT, 'auth_info_baileys') // git-ignored: this folder IS your WhatsApp login
const BRIDGE = process.env.BRIDGE_URL || 'http://127.0.0.1:5001'
const TOKEN = process.env.BRIDGE_TOKEN || ''
const settingsPath = path.join(ROOT, 'config', 'settings.json')
const relationshipMapPath = path.join(ROOT, 'config', 'relationship_map.json')
const killSwitchPath = path.join(ROOT, 'kill_switch.flag')
const defaultSettings = { dry_run: true, min_delay_seconds: 3, max_delay_seconds: 12 }
const startedAt = Math.floor(Date.now() / 1000)

const echo = new OwnEcho()
const pending = new Map() // route jid -> { cancelled }
const seen = new Set()
let reconnectTimer = null
let startupInProgress = false

function readSettings() {
  try { return { ...defaultSettings, ...JSON.parse(fs.readFileSync(settingsPath, 'utf8')) } } catch { return { ...defaultSettings } }
}

function enforceAllowlist(jid) {
  try {
    const map = JSON.parse(fs.readFileSync(relationshipMapPath, 'utf8'))
    const number = String(jid).trim().split('@', 1)[0].split(':', 1)[0]
    return Boolean(number) && Object.prototype.hasOwnProperty.call(map, number) && !['unknown', 'group'].includes(map[number])
  } catch { return false }
}

async function bridge(route, payload) {
  try {
    const res = await axios.post(`${BRIDGE}${route}`, payload, {
      headers: { 'Content-Type': 'application/json', 'X-Bridge-Token': TOKEN }, timeout: 45000,
    })
    return res.data
  } catch (error) {
    logger.error({ err: error.message, route }, '[ROUTE] bridge request failed -- staying silent')
    return null
  }
}

async function handle(sock, m) {
  const key = m.key || {}
  const remoteJid = key.remoteJid
  if (!remoteJid || seen.has(key.id)) return
  seen.add(key.id); if (seen.size > 5000) seen.clear()
  const ts = Number(m.messageTimestamp || 0)
  if (ts && ts < startedAt - 30) return logger.info('[SKIP] backlog from before start')
  const message = m.message
  if (isSystemContent(message)) return
  const isGroup = remoteJid.endsWith('@g.us')
  const routeJid = isGroup ? remoteJid : await resolveRouteJid(key, sock.signalRepository?.lidMapping)
  const text = getMessageText(message)

  if (key.fromMe) {
    if (isGroup || echo.isEcho(routeJid, text, key.id)) return // our own auto-reply echo
    const p = pending.get(routeJid); if (p) p.cancelled = true // the real you took over
    await bridge('/process', { jid: routeJid, text, message_type: getMessageType(message), is_forwarded: false, from_me: true })
    return logger.info({ jid: routeJid }, '[CONTEXT] you typed -- recorded, agent stays quiet here')
  }
  if (fs.existsSync(killSwitchPath)) return logger.warn('[KILL SWITCH] active, skipping all processing')

  const payload = { jid: routeJid, text, message_type: getMessageType(message), is_forwarded: getIsForwarded(message), from_me: false }
  logger.info({ jid: routeJid, lid: routeJid !== remoteJid ? remoteJid : undefined }, '[ROUTE] incoming')
  const r = await bridge('/process', payload)
  if (!r || typeof r !== 'object') return
  logger.info({ shouldReply: r.should_reply, relationship: r.relationship, mode: r.mode, reason: r.reason }, '[DECISION]')
  if (!r.should_reply || !String(r.reply || '').trim()) return

  if (readSettings().dry_run === true) return logger.info({ jid: routeJid, reply: r.reply }, '[DRY_RUN] would reply')

  // ---- stage 7: human-like delay ------------------------------------------------------
  const ticket = { cancelled: false }; pending.set(routeJid, ticket)
  try {
    const delayMs = clampDelayMs(r.delay_seconds, readSettings())
    await sleep(800 + Math.random() * 1200) // notice the message
    await sock.readMessages([key]).catch(() => {})
    await sock.sendPresenceUpdate('composing', remoteJid).catch(() => {})
    logger.info({ jid: routeJid, delayMs }, '[SEND] typing…')
    await sleep(delayMs)
    await sock.sendPresenceUpdate('paused', remoteJid).catch(() => {})
    // re-check everything that could have changed during the wait
    if (ticket.cancelled) return logger.info({ jid: routeJid }, '[SEND] cancelled -- you replied yourself')
    if (fs.existsSync(killSwitchPath)) return logger.warn('[KILL SWITCH] activated during delay -- not sent')
    if (readSettings().dry_run === true) return logger.info('[DRY_RUN] switched on during delay -- not sent')
    if (!enforceAllowlist(routeJid)) return logger.warn({ jid: routeJid }, '[BLOCKED] failed independent allowlist check')

    // ---- stage 8: send ------------------------------------------------------------------
    echo.remember(routeJid, r.reply)
    const sent = await Promise.race([
      sock.sendMessage(remoteJid, { text: r.reply }),
      new Promise((_, rej) => setTimeout(() => rej(new Error('send timeout after 20000ms')), 20000)),
    ])
    echo.remember(routeJid, r.reply, sent?.key?.id)
    await bridge('/sent', { jid: routeJid, reply: r.reply, trace_id: r.trace_id })
    logger.info({ jid: routeJid, reply: r.reply }, '[REPLY] sent')
  } catch (error) {
    logger.error({ jid: routeJid, err: error.message }, '[SEND] failed to deliver reply')
  } finally {
    if (pending.get(routeJid) === ticket) pending.delete(routeJid)
  }
}

async function connectToWhatsApp() {
  if (startupInProgress) return null
  startupInProgress = true
  fs.mkdirSync(authDir, { recursive: true })
  try {
    const { state, saveCreds } = await useMultiFileAuthState(authDir)
    const sock = makeWASocket({
      auth: state, logger: pino({ level: 'silent' }), browser: ['Cruise Control', 'Chrome', '10.0'],
      markOnlineOnConnect: false, // "online" 24/7 is itself a bot tell
      syncFullHistory: false,
    })
    sock.ev.on('creds.update', saveCreds)
    sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
      if (qr) { logger.info('[ROUTE] scan with the DEDICATED number: Linked devices → Link a device'); QRCode.generate(qr, { small: true }) }
      if (connection === 'open') { logger.info('[ROUTE] WhatsApp connection open'); clearTimeout(reconnectTimer); reconnectTimer = null }
      if (connection === 'close') {
        const statusCode = lastDisconnect?.error?.output?.statusCode
        logger.warn({ statusCode }, '[ROUTE] connection closed')
        if (statusCode === DisconnectReason.loggedOut) { logger.error('Logged out -- delete auth_info_baileys/ and scan again'); return }
        if (!reconnectTimer) reconnectTimer = setTimeout(() => { reconnectTimer = null; connectToWhatsApp().catch((e) => logger.error(e)) }, 3000)
      }
    })
    sock.ev.on('messages.upsert', async (event) => {
      if (event?.type !== 'notify') return // history sync, not live
      for (const m of event.messages || []) await handle(sock, m).catch((e) => logger.error({ err: e.message }, '[ROUTE] handler error'))
    })
    return sock
  } finally {
    startupInProgress = false
  }
}

connectToWhatsApp().catch((error) => { logger.error({ err: error }, '[ROUTE] startup failed'); process.exit(1) })
