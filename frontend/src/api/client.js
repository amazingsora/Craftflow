const BASE = '/api/v1'

export const apiUrl = (path) => `${BASE}${path}`

// 把後端技術性錯誤字串映射成使用者可行動的中文訊息。
// 僅針對明確的「服務未啟動 / 連線 / 逾時」情境改寫，其餘原樣保留
// （後端多數 detail 已是中文，且保留原文有助排查）。
export function friendlyError(detail) {
  const raw = (detail == null ? '' : String(detail)).trim()
  if (!raw) return '發生未知錯誤，請稍後再試。'
  const low = raw.toLowerCase()
  const mentionsOllama = low.includes('ollama')
  const mentionsComfy = low.includes('comfyui')
  const offline = low.includes('unavailable') || low.includes('not running')
    || low.includes('connection') || low.includes('connect') || raw.includes('連接') || raw.includes('連線')

  if (mentionsOllama && offline)
    return 'AI 文字／視覺服務（Ollama）尚未啟動或無法連線。請先啟動 Ollama 後再試一次。'
  if (mentionsComfy && offline)
    return '繪圖服務（ComfyUI）尚未啟動或無法連線。請先啟動 ComfyUI 後再試一次。'
  if (low.includes('timed out') || low.includes('timeout') || raw.includes('逾時'))
    return '處理逾時（可能是圖片較大或模型正在載入）。請稍候再試一次。'
  // workflow UI 格式等後端已給的中文指引，原樣保留
  return raw
}

export async function request(path, opts = {}) {
  let response
  try {
    response = await fetch(`${BASE}${path}`, opts)
  } catch (e) {
    // 網路層失敗（後端未啟動等）
    throw new Error('無法連線到後端服務，請確認後端是否已啟動。')
  }
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(friendlyError(err.detail || response.statusText))
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
