// CharacterTab 葉子元件（STATUS_COLOR / GENDER_OPTIONS 僅內部使用）

import { useState, useEffect } from 'react'
import { S } from './characterTabStyles.js'
import { UI } from './sharedStyles.js'
import { Icon } from './Icon.jsx'

const chipStyle = on => ({ ...UI.chip, ...(on ? UI.chipActive : {}) })
const tagPreview = { fontSize: 11.5, color: 'var(--muted)', fontFamily: 'var(--font-mono)', lineHeight: 1.6 }

const STATUS_COLOR = {
  '構思中': { bg: 'var(--tint-blue-bg)', text: 'var(--tint-blue-fg)' },
  '撰寫中': { bg: 'var(--tint-green-bg)', text: 'var(--tint-green-fg)' },
  '修稿中': { bg: 'var(--tint-amber-bg)', text: 'var(--tint-amber-fg)' },
  '完稿':   { bg: 'var(--tint-purple-bg)', text: 'var(--tint-purple-fg)' },
}


export function Spinner() { return <span style={S.spinner} /> }

// ── ImageLightbox ─────────────────────────────────────────────────────────────

export function ImageLightbox({ src, onClose }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999, padding: 32,
        background: 'rgba(8,9,11,.88)', backdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'zoom-out', animation: 'cf-fade .18s var(--ease) both',
      }}
    >
      <img
        src={src}
        onClick={e => e.stopPropagation()}
        style={{
          maxWidth: '92vw', maxHeight: '90vh',
          borderRadius: 'var(--r)', objectFit: 'contain',
          boxShadow: '0 24px 80px rgba(0,0,0,.6)',
          cursor: 'default', animation: 'cf-pop .24s var(--ease) both',
        }}
        alt="放大預覽"
      />
      <button
        onClick={onClose}
        aria-label="關閉（Esc）"
        style={{
          position: 'absolute', top: 18, right: 18,
          width: 36, height: 36, borderRadius: 'var(--r)',
          border: '1px solid rgba(255,255,255,.16)', background: 'rgba(255,255,255,.1)',
          color: '#fff', cursor: 'pointer', display: 'grid', placeItems: 'center',
        }}
      ><Icon name="x" size={18} /></button>
    </div>
  )
}

export function StatusBadge({ status }) {
  const c = STATUS_COLOR[status] ?? { bg: 'var(--surface)', text: 'var(--muted)' }
  return <span style={{ ...S.badge, background: c.bg, color: c.text }}>{status ?? '—'}</span>
}

// ── GenderPicker ──────────────────────────────────────────────────────────────

const GENDER_OPTIONS = [
  { value: 'male',    label: '男' },
  { value: 'female',  label: '女' },
  { value: 'neutral', label: '中性' },
]

export function GenderPicker({ value, onChange }) {
  return (
    <div role="radiogroup" style={{ display: 'inline-flex', border: '1px solid var(--border-strong)', borderRadius: 'var(--r)', overflow: 'hidden', background: 'var(--surface)' }}>
      {GENDER_OPTIONS.map((opt, i) => {
        const selected = value === opt.value
        return (
          <button
            key={opt.value}
            role="radio" aria-checked={selected}
            onClick={() => onChange(selected ? null : opt.value)}
            title={selected ? '再點一次取消' : undefined}
            style={{
              padding: '6px 18px', cursor: 'pointer', border: 'none',
              borderLeft: i === 0 ? 'none' : '1px solid var(--border-strong)',
              background: selected ? 'var(--accent-soft)' : 'transparent',
              color: selected ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 13, fontWeight: selected ? 600 : 500,
            }}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}

// ── DeleteConfirm ─────────────────────────────────────────────────────────────

export function DeleteConfirm({ label, name, onConfirm, onCancel, loading = false }) {
  const [input, setInput] = useState('')
  const match = input === name
  return (
    <div style={S.deleteBox}>
      <p style={S.deletePrompt}>{label}，輸入「{name}」確認</p>
      <input
        style={S.input} value={input} autoFocus
        onChange={e => setInput(e.target.value)}
        placeholder={name}
      />
      <div style={S.btnRow}>
        <button style={S.btnSm} onClick={onCancel}>取消</button>
        <button
          style={{ ...S.btnDanger, opacity: match ? 1 : 0.35, cursor: match ? 'pointer' : 'default' }}
          disabled={!match || loading}
          onClick={onConfirm}
        >
          {loading ? <><Spinner />刪除中...</> : '確認刪除'}
        </button>
      </div>
    </div>
  )
}

// ── AppearanceCardPicker ─────────────────────────────────────────────────────
// [CN-129] 外觀年齡卡片：清單來自 GET /art/appearance-cards（backend/appearance_cards.yml）

const _GENDER_TAG = { female: '1girl', male: '1boy', neutral: 'androgynous' }

// 性別＋卡片 → 送進 prompt 的主體段預覽（與後端 _appearance_parts 同規則）
export function appearanceTagPreview(gender, cardKey, cards) {
  const card = (cards || []).find(c => c.key === cardKey)
  const side = card?.tags?.[gender === 'female' || gender === 'male' ? gender : 'neutral']
  return [_GENDER_TAG[gender], side?.positive].filter(Boolean).join(', ')
}

// [CN-130] 身材卡片：每組單選；卡片不適用目前性別／外觀年齡時隱藏（已存的選擇保留，後端會略過）
const _genderKey = g => (g === 'female' || g === 'male' ? g : 'neutral')

export function BodyCardPicker({ value, onChange, groups, gender, appearanceAge }) {
  const selected = (value || '').split(',').map(s => s.trim()).filter(Boolean)
  const g = _genderKey(gender)
  const usable = c => c.tags?.[g] 
  const pick = (group, key) => {
    const others = selected.filter(k => !group.cards.some(c => c.key === k))
    onChange([...others, ...(key ? [key] : [])].join(','))
  }
  const chip = chipStyle
  const active = (groups || []).map(gr => ({ ...gr, cards: gr.cards.filter(usable) })).filter(gr => gr.cards.length)
  const preview = active.flatMap(gr => gr.cards.filter(c => selected.includes(c.key)).map(c => c.tags[g]))
  const pos = preview.map(s => s.positive).filter(Boolean).join(', ')
  const neg = preview.map(s => s.negative).filter(Boolean).join(', ')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {active.map(gr => {
        const cur = gr.cards.find(c => selected.includes(c.key))?.key || ''
        return (
          <div key={gr.key} style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--muted)', minWidth: 40 }}>{gr.label}</span>
            {[{ key: '', label: '不指定' }, ...gr.cards].map(c => (
              <button key={c.key || 'none'} title={c.hint} onClick={() => pick(gr, c.key)} style={chip(cur === c.key)}>
                {c.label}
              </button>
            ))}
          </div>
        )
      })}
      {(pos || neg) && (
        <div style={tagPreview}>
          {pos && <>正向 + {pos}</>}{pos && neg && '　'}{neg && <>負向 + {neg}</>}
        </div>
      )}
    </div>
  )
}

export function AppearanceCardPicker({ value, onChange, cards, gender }) {
  const options = [{ key: '', label: '不指定', hint: '不加外觀 tag' }, ...(cards || [])]
  const selected = options.find(o => o.key === (value || '')) || options[0]
  const side = selected.tags?.[gender === 'female' || gender === 'male' ? gender : 'neutral']
  return (
    <div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {options.map(opt => {
          const on = (value || '') === opt.key
          return (
            <button
              key={opt.key || 'none'}
              onClick={() => onChange(opt.key)}
              title={opt.hint}
              style={{ ...chipStyle(on), flexDirection: 'column', alignItems: 'flex-start', gap: 1, padding: '5px 12px', fontSize: 13, textAlign: 'left' }}
            >
              {opt.label}
              {opt.hint && <span style={{ fontSize: 10.5, opacity: 0.75, fontWeight: 400 }}>{opt.hint}</span>}
            </button>
          )
        })}
      </div>
      {side && (side.positive || side.negative) && (
        <div style={{ ...tagPreview, marginTop: 6 }}>
          {side.positive && <>正向 + {side.positive}</>}
          {side.positive && side.negative && '　'}
          {side.negative && <>負向 + {side.negative}</>}
        </div>
      )}
    </div>
  )
}
