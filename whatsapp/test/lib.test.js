import { test } from 'node:test'
import assert from 'node:assert/strict'
import { OwnEcho, clampDelayMs, getIsForwarded, getMessageText, getMessageType, isSystemContent, resolveRouteJid } from '../lib.js'

test('text + type extraction', () => {
  assert.equal(getMessageText({ conversation: ' hi ' }), 'hi')
  assert.equal(getMessageText({ extendedTextMessage: { text: 'link' } }), 'link')
  assert.equal(getMessageText({ imageMessage: { caption: 'dekho' } }), 'dekho')
  assert.equal(getMessageType({ imageMessage: {} }), 'image')
  assert.equal(getMessageType({ stickerMessage: {} }), 'sticker')
})
test('forwarded flag read from the inner message', () => {
  assert.equal(getIsForwarded({ extendedTextMessage: { text: 'x', contextInfo: { isForwarded: true } } }), true)
  assert.equal(getIsForwarded({ conversation: 'plain' }), false)
})
test('system content skipped', () => {
  assert.ok(isSystemContent({ reactionMessage: {} }))
  assert.ok(!isSystemContent({ conversation: 'hi' }))
})
test('LID routes to phone via remoteJidAlt or lid mapping', async () => {
  assert.equal(await resolveRouteJid({ remoteJid: '111@lid', remoteJidAlt: '919812345671@s.whatsapp.net' }), '919812345671@s.whatsapp.net')
  const mapping = { getPNForLID: async () => '919812345673@s.whatsapp.net' }
  assert.equal(await resolveRouteJid({ remoteJid: '222@lid' }, mapping), '919812345673@s.whatsapp.net')
  assert.equal(await resolveRouteJid({ remoteJid: '919812345670@s.whatsapp.net' }), '919812345670@s.whatsapp.net')
  assert.equal(await resolveRouteJid({ remoteJid: '333@lid' }, { getPNForLID: async () => { throw new Error('x') } }), '333@lid')
})
test('own echo by id or text', () => {
  const e = new OwnEcho(); e.remember('c', 'Hello pintlu', 'ID1')
  assert.ok(e.isEcho('c', 'other', 'ID1')); assert.ok(e.isEcho('c', 'Hello pintlu')); assert.ok(!e.isEcho('c', 'me typing', 'ID2'))
})
test('delay clamped to settings', () => {
  const s = { min_delay_seconds: 3, max_delay_seconds: 12 }
  assert.equal(clampDelayMs(1, s), 3000); assert.equal(clampDelayMs(60, s), 12000); assert.equal(clampDelayMs(5.5, s), 5500)
  const r = clampDelayMs(undefined, s); assert.ok(r >= 3000 && r <= 12000)
})
