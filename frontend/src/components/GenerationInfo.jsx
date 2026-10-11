import React, { useState, useEffect } from 'react'
import { apiGet } from '../api/client'
import { Icon } from './Icon.jsx'

const TIMING_KEYS = ['vision', 'compile_prompt', 'compile_ai_prompt', 'upload', 'comfyui', 'canvas_expand']

// ── 生成資訊面板：資料只來自後端 generation_history（historyId＝X-History-Id）──
// R-03：卡片欄寬很窄，改成點擊後開寬版對話框，欄位逐列排、prompt 不斷字
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

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!historyId && !fetchPath) return null

  return (
    <div style={{ marginTop: 6 }}>
      <button
        onClick={() => setOpen(true)}
        className="cf-link"
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          fontSize: 11.5, color: 'var(--muted)', background: 'none', border: 'none',
          padding: '2px 4px', margin: '0 -4px', borderRadius: 'var(--r-sm)', cursor: 'pointer', fontWeight: 500,
        }}
      >
        <Icon name="info" size={12} />生成資訊
      </button>
      {open && (
        <div
          onClick={e => e.target === e.currentTarget && setOpen(false)}
          style={{
            position: 'fixed', inset: 0, zIndex: 900, background: 'var(--scrim)', backdropFilter: 'blur(3px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
            animation: 'cf-fade .16s var(--ease) both',
          }}
        >
          <div style={{
            width: 'min(760px, 100%)', maxHeight: '88vh', overflowY: 'auto',
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '14px 20px 20px', color: 'var(--text)',
            boxShadow: 'var(--shadow-modal)', animation: 'cf-pop .22s var(--ease) both',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <strong style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}><Icon name="info" size={16} style={{ color: 'var(--muted)' }} />生成資訊</strong>
              <button
                onClick={() => setOpen(false)}
                className="cf-link"
                style={{ width: 30, height: 30, display: 'grid', placeItems: 'center', background: 'none', border: 'none', borderRadius: 'var(--r)', color: 'var(--muted)', cursor: 'pointer' }}
                aria-label="關閉"
              ><Icon name="x" size={16} /></button>
            </div>
            {err && <div style={{ color: 'var(--danger, #c04)', fontSize: 13 }}>{err}</div>}
            {!info && !err && <div style={{ fontSize: 13, color: 'var(--muted)' }}>載入中…</div>}
            {info && <InfoBody info={info} />}
          </div>
        </div>
      )}
    </div>
  )
}

function InfoBody({ info }) {
  const p = info.params || {}
  const t = p.timings || {}
  const rows = [
    ['Seed', info.seed],
    ['Workflow', info.workflow],
    ['Style', info.style],
    ['尺寸', p.width && p.height ? `${p.width} × ${p.height}` : null],
    ['Steps / CFG', [p.steps != null ? `steps ${p.steps}` : null, p.cfg != null ? `cfg ${p.cfg}` : null].filter(Boolean).join(' · ') || null],
    ['ControlNet', p.cn_used ? `${p.cn_weight}${p.cn_mode ? `（${p.cn_mode}）` : ''}` : '關'],
    ['IP-Adapter', p.ipa_used ? String(p.ipa_weight) : '關'],
    ['Coverage', p.coverage],
    ['結構控制機制', p.mechanism && p.mechanism !== 'none'
      ? [p.mechanism,
         p.mechanism === 'lllite' && p.lllite_name ? `${p.lllite_name} · strength ${p.lllite_strength}` : null,
         p.mechanism === 'img2img' && p.img2img_denoise != null ? `denoise ${p.img2img_denoise}` : null,
        ].filter(Boolean).join(' · ')
      : null],
    ['耗時', Object.keys(t).length
      ? [...TIMING_KEYS.filter(k => t[k] != null).map(k => `${k} ${t[k]}s`), t.total != null ? `總計 ${t.total}s` : null]
          .filter(Boolean).join(' · ')
      : null],
  ].filter(([, v]) => v != null && v !== '')

  const pre = {
    fontSize: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'normal', overflowWrap: 'break-word',
    background: 'var(--surface-2, rgba(127,127,127,0.08))', border: '1px solid var(--border)',
    borderRadius: 'var(--r)', padding: '8px 10px', marginTop: 6, maxHeight: '30vh', overflowY: 'auto',
    userSelect: 'text', fontFamily: 'var(--font-mono)',
  }
  const copyAll = () => navigator.clipboard?.writeText(
    `seed: ${info.seed}\nworkflow: ${info.workflow}\nstyle: ${info.style || ''}\n`
    + `params: ${JSON.stringify(p)}\n\npositive:\n${info.positive || ''}\n\nnegative:\n${info.negative || ''}`
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', columnGap: 16, rowGap: 6, fontSize: 13 }}>
        {rows.map(([k, v]) => (
          <React.Fragment key={k}>
            <div style={{ color: 'var(--muted)', whiteSpace: 'nowrap' }}>{k}</div>
            <div style={{ overflowWrap: 'anywhere', fontFamily: 'var(--font-mono)', fontSize: 12.5 }}>{String(v)}</div>
          </React.Fragment>
        ))}
      </div>
      <div>
        <div style={{ fontSize: 12, fontWeight: 600 }}>Positive</div>
        <div style={pre}>{info.positive || '—'}</div>
      </div>
      <div>
        <div style={{ fontSize: 12, fontWeight: 600 }}>Negative</div>
        <div style={pre}>{info.negative || '—'}</div>
      </div>
      <button
        onClick={copyAll}
        style={{
          alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--text)',
          background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 'var(--r)',
          padding: '5px 10px', cursor: 'pointer',
        }}
      >
        <Icon name="copy" size={13} />複製全部
      </button>
    </div>
  )
}
