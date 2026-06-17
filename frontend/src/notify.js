// 生成 / 訓練完成的通知（2026-06-13）
// 三層：app 內右下角 toast（一定看得到，免權限）＋ OS 桌面通知（切到背景也看得到，需授權）＋ 通知音。
// 設定存 localStorage：
//   craftflow_notify       'on'|'off'（預設 on）— 通知總開關
//   craftflow_notify_sound 'on'|'off'（預設 on）— 通知音
// 所有呼叫皆容錯，不可讓主流程 crash。

const K_NOTIFY = 'craftflow_notify'
const K_SOUND = 'craftflow_notify_sound'

export function notifyEnabled() {
  return localStorage.getItem(K_NOTIFY) !== 'off'
}
export function soundEnabled() {
  return localStorage.getItem(K_SOUND) !== 'off'
}
export function setNotifyEnabled(on) {
  localStorage.setItem(K_NOTIFY, on ? 'on' : 'off')
}
export function setSoundEnabled(on) {
  localStorage.setItem(K_SOUND, on ? 'on' : 'off')
}

// 目前桌面通知權限：'granted' | 'denied' | 'default' | 'unsupported'
export function notifyPermission() {
  try {
    return (typeof Notification === 'undefined') ? 'unsupported' : Notification.permission
  } catch (_) {
    return 'unsupported'
  }
}

// 主動要求權限（建議由按鈕點擊觸發 → user gesture，瀏覽器才會穩定彈窗）
export function requestNotifyPermission() {
  try {
    if (typeof Notification === 'undefined') return Promise.resolve('unsupported')
    return Notification.requestPermission()
  } catch (_) {
    return Promise.resolve('denied')
  }
}

// App 載入時嘗試要一次（default 才要；部分瀏覽器無 user gesture 會忽略，故 Settings 另備按鈕）
export function ensureNotifyPermission() {
  try {
    if (typeof Notification === 'undefined') return
    if (Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {})
    }
  } catch (_) { /* ignore */ }
}

// 短促通知音（C6→E6 兩聲上行小鈴）
function playChime() {
  if (!soundEnabled()) return
  try {
    const AC = window.AudioContext || window.webkitAudioContext
    if (!AC) return
    const ctx = new AC()
    const now = ctx.currentTime
    const freqs = [1046.5, 1318.5]
    freqs.forEach((f, i) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = f
      const t0 = now + i * 0.12
      gain.gain.setValueAtTime(0.0001, t0)
      gain.gain.exponentialRampToValueAtTime(0.25, t0 + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.18)
      osc.connect(gain).connect(ctx.destination)
      osc.start(t0)
      osc.stop(t0 + 0.2)
    })
    setTimeout(() => { try { ctx.close() } catch (_) {} }, 700)
  } catch (_) { /* ignore */ }
}

// app 內右下角 toast（直接注入 DOM，免 React 連動；用主題 token 配色）
function showToast(title, body) {
  try {
    const doc = document
    let host = doc.getElementById('craftflow-toast-host')
    if (!host) {
      host = doc.createElement('div')
      host.id = 'craftflow-toast-host'
      host.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:99999;display:flex;flex-direction:column;gap:10px;pointer-events:none'
      doc.body.appendChild(host)
    }
    const el = doc.createElement('div')
    el.style.cssText = [
      'pointer-events:auto', 'cursor:pointer',
      'min-width:220px', 'max-width:320px',
      'background:var(--surface,#ffffff)', 'color:var(--text,#111111)',
      'border:1px solid var(--border,#dddddd)', 'border-left:4px solid var(--accent,#4f8cff)',
      'border-radius:10px', 'box-shadow:0 6px 24px rgba(0,0,0,.18)',
      'padding:12px 14px', 'font-size:13px', 'line-height:1.5',
      'opacity:0', 'transform:translateY(8px)', 'transition:opacity .2s,transform .2s',
    ].join(';')
    const t = doc.createElement('div')
    t.style.cssText = 'font-weight:600;margin-bottom:2px'
    t.textContent = title || '完成'
    el.appendChild(t)
    if (body) {
      const b = doc.createElement('div')
      b.style.cssText = 'color:var(--muted,#666666)'
      b.textContent = body
      el.appendChild(b)
    }
    host.appendChild(el)
    requestAnimationFrame(() => { el.style.opacity = '1'; el.style.transform = 'translateY(0)' })
    const remove = () => {
      el.style.opacity = '0'; el.style.transform = 'translateY(8px)'
      setTimeout(() => { try { el.remove() } catch (_) {} }, 250)
    }
    el.addEventListener('click', remove)
    setTimeout(remove, 4200)
  } catch (_) { /* ignore */ }
}

// 生成 / 訓練完成時呼叫
export function notifyDone(title, body) {
  if (!notifyEnabled()) return
  playChime()
  showToast(title, body)  // 一定看得到（app 內右下角）
  try {
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      // silent:true → 不讓 OS 另外播音，避免與 playChime 重複
      const n = new Notification(title, { body: body || '', tag: 'craftflow-gen', silent: true })
      n.onclick = () => { try { window.focus() } catch (_) {} ; n.close() }
      setTimeout(() => { try { n.close() } catch (_) {} }, 6000)
    }
  } catch (_) { /* ignore */ }
}
