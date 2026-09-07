import { describe, expect, it } from 'vitest'
import { apiErrorMessage, tokenStorage } from './client'

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
