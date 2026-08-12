import React, { useState, useEffect } from 'react'
import { apiGet } from '../api/client'

// ── 生成資訊面板（2026-07-26）──────────────────────────────────────────────────
// 資料源是後端 generation_history（已存齊 prompt/seed/參數/耗時），不在 localStorage
// 另存一份，避免兩份真相。historyId 來自生圖回應的 X-History-Id header。
export function GenerationInfo({ historyId, fetchPath }) {
  const [info, setInfo] = useState(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open || info || err) return
    const path = fetchPath ?? (historyId ? `/generation-history/${historyId}` : null)
    if (!path) { setErr('這張圖沒有留下生成資訊'); return }
    let cancelled = false
    apiGet(path)
      .then(d => { if (!cancelled) setInfo(d) })
      .catch(e => { if (!cancelled) setErr(e.message) })
    return () => { cancelled = true }
  }, [open, info, err, historyId, fetchPath])

  if (!historyId && !fetchPath) return null

  const box = { fontSize: 12, color: 'var(--muted)', lineHeight: 1.55 }
  const label = { color: 'var(--text)', fontWeight: 600 }
  const pre = {
    ...box, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
    background: 'var(--panel-2, rgba(127,127,127,0.08))',
    borderRadius: 6, padding: '6px 8px', marginTop: 3, maxHeight: 140, overflowY: 'auto',
    userSelect: 'text',
  }
  const p = info?.params || {}
  const t = p.timings || {}

  return (
    <div style={{ marginTop: 4 }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none',
          padding: 0, cursor: 'pointer', fontWeight: 600,
        }}
      >
        {open ? '收合生成資訊 ▲' : '生成資訊 ▼'}
      </button>
      {open && (
        <div style={{ ...box, marginTop: 5, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {err && <div style={{ color: 'var(--danger, #c04)' }}>{err}</div>}
          {!info && !err && <div>載入中…</div>}
          {info && (
            <>
              <div>
                <span style={label}>seed</span> {info.seed}
                {' · '}<span style={label}>workflow</span> {info.workflow}
                {info.style ? <>{' · '}<span style={label}>style</span> {info.style}</> : null}
              </div>
              <div>
                {p.width}×{p.height}
                {p.steps != null ? ` · steps ${p.steps}` : ''}
                {p.cn_used ? ` · CN ${p.cn_weight}${p.cn_mode ? `(${p.cn_mode})` : ''}` : ' · CN off'}
                {p.ipa_used ? ` · IPA ${p.ipa_weight}` : ' · IPA off'}
                {p.coverage ? ` · coverage ${p.coverage}` : ''}
              </div>
              {Object.keys(t).length > 0 && (
                <div>
                  <span style={label}>耗時</span>{' '}
                  {['vision', 'compile_prompt', 'compile_ai_prompt', 'upload', 'comfyui', 'canvas_expand']
                    .filter(k => t[k] != null).map(k => `${k} ${t[k]}s`).join(' · ')}
                  {t.total != null ? ` · 總計 ${t.total}s` : ''}
                </div>
              )}
              <div><span style={label}>positive</span><div style={pre}>{info.positive || '—'}</div></div>
              <div><span style={label}>negative</span><div style={pre}>{info.negative || '—'}</div></div>
              <button
                onClick={() => navigator.clipboard?.writeText(
                  `seed: ${info.seed}\nworkflow: ${info.workflow}\nstyle: ${info.style || ''}\n`
                  + `params: ${JSON.stringify(p)}\n\npositive:\n${info.positive || ''}\n\nnegative:\n${info.negative || ''}`
                )}
                style={{
                  alignSelf: 'flex-start', fontSize: 12, color: 'var(--accent)',
                  background: 'none', border: '1px solid var(--border)', borderRadius: 5,
                  padding: '3px 9px', cursor: 'pointer',
                }}
              >
                複製全部
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
