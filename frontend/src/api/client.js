const BASE = '/api/v1'

export const apiUrl = (path) => `${BASE}${path}`

export async function request(path, opts = {}) {
  const response = await fetch(`${BASE}${path}`, opts)
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(err.detail || response.statusText)
  }
  return response
}

export const apiGet = (path) => request(path).then((response) => response.json())

export const apiPostJson = (path, body) => request(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}).then((response) => response.json())

export const apiPostForm = (path, body) => request(path, { method: 'POST', body })

export const apiPostBlob = (path, opts = {}) => request(path, { method: 'POST', ...opts })
  .then((response) => response.blob())

export const apiDelete = (path) => request(path, { method: 'DELETE' })
