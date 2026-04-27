// Wrapper around the FastAPI backend. Attaches the Supabase JWT for auth endpoints.
import { supabase } from './supabase'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function authHeaders() {
  const { data: { session } } = await supabase.auth.getSession()
  return session ? { Authorization: `Bearer ${session.access_token}` } : {}
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
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
  return request(`/api/listings/${id}`, {
    method: 'PUT',
    headers: await authHeaders(),
    body: JSON.stringify(data),
  })
}

export async function deleteListing(id) {
  return request(`/api/listings/${id}`, {
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
  return request(`/api/wishlist/${cardId}`, {
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
