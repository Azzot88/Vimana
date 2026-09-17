import { describe, expect, it } from 'vitest'
import { relativeParts } from '../lib/format'

/**
 * T_UX.28 — «сколько назад», пока это полезный ответ.
 *
 * Owner, 2026-09-16: до пяти минут — «только что», дальше точные минуты до
 * часа, до двух часов — получасами, дальше целыми часами. Past a day the
 * relative form stops helping, so the helper returns nothing and the caller
 * prints the date it already knows how to print.
 */
const NOW = Date.parse('2026-09-16T12:00:00Z')
const ago = (minutes: number) => new Date(NOW - minutes * 60_000).toISOString()

describe('relativeParts', () => {
  it('calls the first five minutes «just now», without a number', () => {
    expect(relativeParts(ago(0), NOW)).toEqual({ key: 'time.justNow' })
    expect(relativeParts(ago(4), NOW)).toEqual({ key: 'time.justNow' })
  })

  it('counts exact minutes for the rest of the hour', () => {
    expect(relativeParts(ago(5), NOW)).toEqual({ key: 'time.minutes', count: 5 })
    expect(relativeParts(ago(47), NOW)).toEqual({ key: 'time.minutes', count: 47 })
  })

  it('rounds the second hour to halves, because nobody needs «73 минуты»', () => {
    expect(relativeParts(ago(60), NOW)).toEqual({ key: 'time.hour' })
    expect(relativeParts(ago(89), NOW)).toEqual({ key: 'time.hour' })
    expect(relativeParts(ago(90), NOW)).toEqual({ key: 'time.hourHalf' })
    expect(relativeParts(ago(119), NOW)).toEqual({ key: 'time.hourHalf' })
  })

  it('counts whole hours after that', () => {
    expect(relativeParts(ago(120), NOW)).toEqual({ key: 'time.hours', count: 2 })
    expect(relativeParts(ago(23 * 60), NOW)).toEqual({ key: 'time.hours', count: 23 })
  })

  it('gives up after a day, so the caller prints the date', () => {
    expect(relativeParts(ago(24 * 60), NOW)).toBeNull()
    expect(relativeParts(ago(400 * 60), NOW)).toBeNull()
  })

  it('says nothing about a stamp from the future or a broken one', () => {
    // Somebody's clock, not a moment to describe.
    expect(relativeParts(new Date(NOW + 60_000).toISOString(), NOW)).toBeNull()
    expect(relativeParts('not a date', NOW)).toBeNull()
    expect(relativeParts(null, NOW)).toBeNull()
  })
})
