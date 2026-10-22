/*
  AUTHENTICATION SERVICE

  Accounts are pseudonymous: a username and a password, no email or real name.
  The server decides the role. Signing in with the Administrator checkbox
  sends admin: true, and the server refuses (403) if the account is not an admin.
*/

import { apiRequest, clearToken, getToken, setToken } from './apiClient'

export async function signIn(username, password, asAdmin) {
  const data = await apiRequest('/api/auth/login', {
    method: 'POST',
    auth: false,
    body: { username: username.trim(), password, admin: asAdmin }
  })

  setToken(data.token)
  return data.user
}

export async function register(username, password) {
  const data = await apiRequest('/api/auth/register', {
    method: 'POST',
    auth: false,
    body: { username: username.trim(), password }
  })

  setToken(data.token)
  return data.user
}

// Returns the signed-in user, or null when there is no valid sign-in.
// An expired token is discarded by apiRequest (401).
export async function restoreSession() {
  if (!getToken()) {
    return null
  }

  try {
    return await apiRequest('/api/auth/me')
  } catch {
    return null
  }
}

export async function signOut() {
  try {
    // Invalidates the token on the server too (signs out everywhere).
    await apiRequest('/api/auth/logout', { method: 'POST' })
  } catch {
    // Signing out locally still works if the server can't be reached.
  } finally {
    clearToken()
  }
}
