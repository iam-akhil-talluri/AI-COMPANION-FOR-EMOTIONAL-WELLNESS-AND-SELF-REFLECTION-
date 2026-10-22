/*
  API CLIENT

  One place for every request to the FastAPI backend:
  - base URL (VITE_API_URL in production; the Vite dev server proxies /api locally)
  - the signed-in user's access token
  - a request timeout
  - one error shape: ApiError { status, code, message }

  The backend always answers errors as { code, detail }. `detail` is written
  to be shown to the user as-is.
*/

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '')
const TOKEN_STORAGE_KEY = 'wellnessCompanionToken'
const REQUEST_TIMEOUT_MS = 30000
const GATEWAY_STATUSES = [502, 503, 504]

export const NETWORK_ERROR_MESSAGE =
  'We could not reach the server. Check your connection and try again.'
const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.'

export class ApiError extends Error {
  constructor(status, code, message, data = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    // The response body, for endpoints whose error body is still useful (e.g. /api/health).
    this.data = data
  }
}

// TOKEN STORAGE
// sessionStorage: the sign-in lasts for this browser tab and is cleared when it closes.
// memoryToken is the fallback when the browser blocks storage (some private modes).
let memoryToken = null

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_STORAGE_KEY) || memoryToken
  } catch {
    return memoryToken
  }
}

export function setToken(token) {
  try {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
  } catch {
    // Storage can be blocked (private mode); the token then lasts until reload.
  }
  memoryToken = token
}

export function clearToken() {
  try {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    // Nothing stored.
  }
  memoryToken = null
}

// SIGN-IN EXPIRY
// App.jsx registers a handler that returns the user to the login screen.
let unauthorizedHandler = null

export function onUnauthorized(handler) {
  unauthorizedHandler = handler
}

async function readJson(response) {
  try {
    return await response.json()
  } catch {
    return null
  }
}

export async function apiRequest(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  const token = auth ? getToken() : null
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal
    })
  } catch {
    throw new ApiError(0, 'network_error', NETWORK_ERROR_MESSAGE)
  } finally {
    clearTimeout(timer)
  }

  if (response.status === 204) {
    return null
  }

  const data = await readJson(response)

  // 502/503/504 without a JSON body come from a proxy or gateway (the Vite dev
  // proxy, a load balancer) when the backend can't be reached. The backend itself
  // always answers with JSON, including its own 503s.
  if (GATEWAY_STATUSES.includes(response.status) && data === null) {
    throw new ApiError(0, 'network_error', NETWORK_ERROR_MESSAGE)
  }

  if (!response.ok) {
    const code = data?.code || 'http_error'
    const message = typeof data?.detail === 'string' ? data.detail : GENERIC_ERROR_MESSAGE

    if (response.status === 401 && auth) {
      clearToken()
      if (unauthorizedHandler) {
        unauthorizedHandler(message)
      }
    }

    throw new ApiError(response.status, code, message, data)
  }

  return data
}
