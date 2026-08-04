// Wrapper around the FastAPI backend. Attaches the Supabase JWT for auth endpoints.
import { supabase } from './supabase'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function authHeaders() {
  const { data: { session } } = await supabase.auth.getSession()
  return session ? { Authorization: `Bearer ${session.access_token}` } : {}
}

/**
 * An HTTP failure that kept its status code.
 *
 * The backend now distinguishes cases the UI has to treat differently — 409 for
 * insufficient stock, 400 for a stale cart total, 429 for rate limiting — and a
 * bare Error() collapsed all of them into one string. Callers branch on `.status`.
 */
export class ApiError extends Error {
  constructor(message, { status, retryAfter = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

async function request(path, { headers: extraHeaders = {}, ...rest } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...extraHeaders },
    ...rest,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    // FastAPI validation errors return detail as an array of {loc, msg, type} objects
    const detail = Array.isArray(err.detail)
      ? err.detail.map(d => d.msg).join('; ')
      : err.detail

    // Readable only because the backend lists it in Access-Control-Expose-Headers;
    // Retry-After is not a CORS-safelisted response header.
    const retryAfterRaw = res.headers.get('Retry-After')
    const retryAfter = retryAfterRaw ? Number(retryAfterRaw) : null

    throw new ApiError(detail || `Request failed (${res.status})`, {
      status: res.status,
      retryAfter: Number.isFinite(retryAfter) ? retryAfter : null,
    })
  }
  if (res.status === 204) return null
  return res.json()
}

// ── Listings ──────────────────────────────────────────────────

export const getListings = () => request('/api/listings/')

export async function createListing(data) {
  return request('/api/listings/', {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify(data),
  })
}

export async function updateListing(id, data) {
  return request(`/api/listings/${id}/`, {
    method: 'PUT',
    headers: await authHeaders(),
    body: JSON.stringify(data),
  })
}

export async function deleteListing(id) {
  return request(`/api/listings/${id}/`, {
    method: 'DELETE',
    headers: await authHeaders(),
  })
}

// ── Wishlist ──────────────────────────────────────────────────

export async function getWishlist() {
  return request('/api/wishlist/', { headers: await authHeaders() })
}

export async function addToWishlist(item) {
  return request('/api/wishlist/', {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify(item),
  })
}

export async function removeFromWishlist(cardId) {
  return request(`/api/wishlist/${cardId}/`, {
    method: 'DELETE',
    headers: await authHeaders(),
  })
}

// ── Orders ────────────────────────────────────────────────────

export async function getOrders() {
  return request('/api/orders/', { headers: await authHeaders() })
}

export async function createOrder(data) {
  return request('/api/orders/', {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify(data),
  })
}
