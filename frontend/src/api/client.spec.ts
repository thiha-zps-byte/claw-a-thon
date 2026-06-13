import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { api, ApiException, getUid, setUid } from './client'

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  } as Response)
}

describe('api client', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('generates and persists a UID', () => {
    const uid = getUid()
    expect(uid).toMatch(/^u-/)
    expect(getUid()).toBe(uid)
  })

  it('lets the user set a UID', () => {
    setUid('player-42')
    expect(getUid()).toBe('player-42')
  })

  it('sends X-UID header on requests', async () => {
    const f = mockFetch(200, { bots: [] })
    vi.stubGlobal('fetch', f)
    await api.listBots()
    const headers = (f.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers['X-UID']).toBeTruthy()
  })

  it('unwraps the list payload', async () => {
    vi.stubGlobal('fetch', mockFetch(200, { bots: [{ id: 'a', name: 'X' }] }))
    const bots = await api.listBots()
    expect(bots).toHaveLength(1)
    expect(bots[0].id).toBe('a')
  })

  it('throws ApiException with the envelope message on error', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(400, { error: 'validation_error', message: 'Tên bot không được để trống.' }),
    )
    await expect(api.createBot({})).rejects.toBeInstanceOf(ApiException)
    await expect(api.createBot({})).rejects.toThrow('Tên bot không được để trống.')
  })

  it('marks 5xx as retryable', async () => {
    vi.stubGlobal('fetch', mockFetch(503, { error: 'llm_unavailable', message: 'Bận', retryable: true }))
    try {
      await api.chat('b1', 'hi')
      expect.unreachable()
    } catch (e) {
      expect(e).toBeInstanceOf(ApiException)
      expect((e as ApiException).retryable).toBe(true)
    }
  })

  it('treats fetch rejection as a retryable network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')))
    try {
      await api.listBots()
      expect.unreachable()
    } catch (e) {
      expect((e as ApiException).code).toBe('network')
      expect((e as ApiException).retryable).toBe(true)
    }
  })
})
