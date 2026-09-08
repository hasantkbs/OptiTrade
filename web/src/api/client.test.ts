import axios, { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient, apiErrorMessage, setSessionExpiredHandler, tokenStorage } from './client'

describe('tokenStorage', () => {
  it('stores and retrieves an access/refresh token pair', () => {
    tokenStorage.setTokens({ access_token: 'access-123', refresh_token: 'refresh-456' })
    expect(tokenStorage.getAccessToken()).toBe('access-123')
    expect(tokenStorage.getRefreshToken()).toBe('refresh-456')
  })

  it('returns null when nothing is stored', () => {
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })

  it('clears both tokens', () => {
    tokenStorage.setTokens({ access_token: 'a', refresh_token: 'b' })
    tokenStorage.clear()
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })
})

describe('apiErrorMessage', () => {
  it('falls back to a generic message for a non-axios error', () => {
    expect(apiErrorMessage(new Error('boom'))).toBe('Something went wrong. Please try again.')
  })

  it('accepts a custom fallback', () => {
    expect(apiErrorMessage(new Error('boom'), 'Custom fallback')).toBe('Custom fallback')
  })
})

/**
 * Exercises the real 401 -> refresh -> retry interceptor in client.ts
 * (WEB STEP 8 Phase 2/13 - previously untested at this level) by
 * swapping the shared `apiClient` instance's transport for a mock
 * adapter, rather than mocking `axios` wholesale - the interceptor,
 * single-flight `refreshPromise` guard, and header-attachment logic
 * under test are the exact real production code, only the network
 * transport is fake. A real adapter (xhr.js/http.js) calls `settle()`
 * itself to turn a non-2xx status into a rejected AxiosError carrying
 * `.config`/`.response` - a bare custom adapter does not get that for
 * free, so this helper reproduces exactly that behavior with the real
 * `AxiosError` class.
 */
function respond(status: number, data: unknown, config: InternalAxiosRequestConfig) {
  const response = { data, status, statusText: '', headers: {}, config }
  if (status >= 200 && status < 300) return Promise.resolve(response)
  return Promise.reject(new AxiosError('Request failed', String(status), config, null, response))
}

describe('apiClient 401/refresh interceptor', () => {
  let adapter: ReturnType<typeof vi.fn>

  beforeEach(() => {
    tokenStorage.clear()
    setSessionExpiredHandler(null)
    adapter = vi.fn()
    apiClient.defaults.adapter = adapter as unknown as AxiosAdapter
  })

  afterEach(() => {
    vi.restoreAllMocks()
    setSessionExpiredHandler(null)
  })

  it('attaches the stored access token as a Bearer header', async () => {
    tokenStorage.setTokens({ access_token: 'tok-1', refresh_token: 'r' })
    adapter.mockImplementationOnce((config: InternalAxiosRequestConfig) => respond(200, { ok: true }, config))

    await apiClient.get('/whatever')

    expect(adapter.mock.calls[0][0].headers.Authorization).toBe('Bearer tok-1')
  })

  it('on a single 401, refreshes exactly once and retries the original request with the new token', async () => {
    tokenStorage.setTokens({ access_token: 'old', refresh_token: 'refresh-1' })
    const postSpy = vi.spyOn(axios, 'post').mockResolvedValueOnce({
      data: { access_token: 'new', refresh_token: 'refresh-2', token_type: 'bearer', expires_in: 900 },
      status: 200,
      statusText: '',
      headers: {},
      config: {} as InternalAxiosRequestConfig,
    })
    adapter
      .mockImplementationOnce((config: InternalAxiosRequestConfig) => respond(401, { detail: 'expired' }, config))
      .mockImplementationOnce((config: InternalAxiosRequestConfig) => respond(200, { ok: true }, config))

    const response = await apiClient.get('/protected')

    expect(response.data).toEqual({ ok: true })
    expect(postSpy).toHaveBeenCalledTimes(1)
    expect(adapter).toHaveBeenCalledTimes(2)
    expect(adapter.mock.calls[1][0].headers.Authorization).toBe('Bearer new')
    expect(tokenStorage.getAccessToken()).toBe('new')
  })

  it('two concurrent 401s share a single refresh call, never two (single-flight)', async () => {
    tokenStorage.setTokens({ access_token: 'old', refresh_token: 'refresh-1' })
    const postSpy = vi.spyOn(axios, 'post').mockResolvedValueOnce({
      data: { access_token: 'new', refresh_token: 'refresh-2', token_type: 'bearer', expires_in: 900 },
      status: 200,
      statusText: '',
      headers: {},
      config: {} as InternalAxiosRequestConfig,
    })
    adapter
      .mockImplementationOnce((config: InternalAxiosRequestConfig) => respond(401, { detail: 'expired' }, config))
      .mockImplementationOnce((config: InternalAxiosRequestConfig) => respond(401, { detail: 'expired' }, config))
      .mockImplementationOnce((config: InternalAxiosRequestConfig) => respond(200, { first: true }, config))
      .mockImplementationOnce((config: InternalAxiosRequestConfig) => respond(200, { second: true }, config))

    const [first, second] = await Promise.all([apiClient.get('/a'), apiClient.get('/b')])

    expect(first.data).toEqual({ first: true })
    expect(second.data).toEqual({ second: true })
    expect(postSpy).toHaveBeenCalledTimes(1)
  })

  it('clears the session and notifies the session-expired handler when the refresh call itself fails, without retrying forever', async () => {
    tokenStorage.setTokens({ access_token: 'old', refresh_token: 'dead-refresh' })
    vi.spyOn(axios, 'post').mockRejectedValueOnce(new Error('refresh token revoked'))
    adapter.mockImplementationOnce((config: InternalAxiosRequestConfig) => respond(401, { detail: 'expired' }, config))
    const onExpired = vi.fn()
    setSessionExpiredHandler(onExpired)

    await expect(apiClient.get('/protected')).rejects.toBeTruthy()

    expect(adapter).toHaveBeenCalledTimes(1)
    expect(onExpired).toHaveBeenCalledTimes(1)
    expect(tokenStorage.getAccessToken()).toBeNull()
  })

  it('never retries a 401 from /auth/refresh itself (would otherwise loop)', async () => {
    tokenStorage.setTokens({ access_token: 'old', refresh_token: 'r' })
    const onExpired = vi.fn()
    setSessionExpiredHandler(onExpired)
    adapter.mockImplementationOnce((config: InternalAxiosRequestConfig) => respond(401, { detail: 'invalid refresh token' }, config))

    await expect(apiClient.get('/auth/refresh')).rejects.toBeTruthy()

    expect(adapter).toHaveBeenCalledTimes(1)
    expect(onExpired).toHaveBeenCalledTimes(1)
  })
})
