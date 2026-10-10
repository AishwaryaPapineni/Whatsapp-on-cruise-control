// Pure helpers for baileys_client.js (no network -> unit tested with `node --test`).

/** Text from any message shape: plain, extended, captions (session getMessageText + documents). */
export function getMessageText(message) {
  if (!message || typeof message !== 'object') return ''
  return (
    message.conversation ||
    message.extendedTextMessage?.text ||
    message.imageMessage?.caption ||
    message.videoMessage?.caption ||
    message.documentMessage?.caption ||
    ''
  ).trim()
}

export function getMessageType(message) {
  if (!message || typeof message !== 'object') return 'other'
  if (message.conversation || message.extendedTextMessage) return 'text'
  for (const t of ['image', 'video', 'audio', 'sticker', 'document']) if (message[`${t}Message`]) return t
  return 'other'
}

/** contextInfo lives on the inner message object, never on `conversation` (a plain string). */
export function getIsForwarded(message) {
  if (!message || typeof message !== 'object') return false
  for (const v of Object.values(message)) {
    if (v && typeof v === 'object' && v.contextInfo) return Boolean(v.contextInfo.isForwarded)
  }
  return false
}

/** Protocol edits/deletes, reactions, polls: never fed to the brain. */
export function isSystemContent(message) {
  if (!message) return true
  return Boolean(message.protocolMessage || message.reactionMessage || message.pollUpdateMessage ||
    (message.senderKeyDistributionMessage && Object.keys(message).length === 1))
}

/**
 * Baileys 7 often addresses 1:1 chats by a privacy LID (12345@lid). The relationship map is
 * keyed by PHONE number, so route by the phone JID: key.remoteJidAlt, else the LID mapping.
 * Reply to the original JID (that's the chat the message came from).
 */
export async function resolveRouteJid(key, lidMapping) {
  const jid = key?.remoteJid || ''
  if (!jid.endsWith('@lid')) return jid
  if (key.remoteJidAlt && key.remoteJidAlt.endsWith('@s.whatsapp.net')) return key.remoteJidAlt
  try {
    const pn = lidMapping?.getPNForLID ? await lidMapping.getPNForLID(jid) : null
    return pn || jid
  } catch {
    return jid
  }
}

/** Remembers what the agent itself sent, so its own echo isn't mistaken for "the real you typed". */
export class OwnEcho {
  constructor(ttlMs = 120_000) { this.ttlMs = ttlMs; this.ids = new Map(); this.texts = new Map() }
  remember(chat, text, id) {
    const exp = Date.now() + this.ttlMs
    if (id) this.ids.set(id, exp)
    this.texts.set(`${chat}|${text}`, exp)
  }
  isEcho(chat, text, id) {
    const now = Date.now()
    for (const m of [this.ids, this.texts]) for (const [k, exp] of m) if (exp < now) m.delete(k)
    return Boolean((id && this.ids.has(id)) || this.texts.has(`${chat}|${text}`))
  }
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export function clampDelayMs(seconds, settings) {
  const min = Number(settings.min_delay_seconds ?? 3) * 1000
  const max = Number(settings.max_delay_seconds ?? 12) * 1000
  const want = Number.isFinite(Number(seconds)) && Number(seconds) > 0 ? Number(seconds) * 1000 : min + Math.random() * (max - min)
  return Math.round(Math.min(Math.max(want, min), max))
}
