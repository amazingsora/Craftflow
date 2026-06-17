// Craftflow CharacterTab 葉子元件（2026-06-13 A2 增量2：自 CharacterTab.jsx 抽出）
// 相依：S（樣式）、React hooks；STATUS_COLOR / GENDER_OPTIONS 為內部用，不外曝。

import { useState, useEffect } from 'react'
import { S } from './characterTabStyles.js'

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
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.88)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'zoom-out',
      }}
    >
      <img
        src={src}
        onClick={e => e.stopPropagation()}
        style={{
          maxWidth: '90vw', maxHeight: '90vh',
          borderRadius: 12, objectFit: 'contain',
          boxShadow: '0 12px 64px rgba(0,0,0,0.7)',
          cursor: 'default',
        }}
        alt="放大預覽"
      />
      <button
        onClick={onClose}
        style={{
          position: 'absolute', top: 16, right: 20,
          width: 34, height: 34, borderRadius: '50%',
          border: 'none', background: 'rgba(255,255,255,0.15)',
          color: 'var(--accent-contrast)', fontSize: 20, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          lineHeight: 1,
        }}
      >×</button>
    </div>
  )
}

export function StatusBadge({ status }) {
  const c = STATUS_COLOR[status] ?? { bg: 'var(--surface)', text: 'var(--muted)' }
  return <span style={{ ...S.badge, background: c.bg, color: c.text }}>{status ?? '—'}</span>
}

// ── GenderPicker ──────────────────────────────────────────────────────────────

const GENDER_OPTIONS = [
  { value: 'male',    icon: '♂', label: '男',   active: 'var(--tint-blue-fg)', bg: 'var(--tint-blue-bg)' },
  { value: 'female',  icon: '♀', label: '女',   active: 'var(--tint-pink-fg)', bg: 'var(--tint-pink-bg)' },
  { value: 'neutral', icon: '⚧', label: '中性', active: 'var(--tint-purple-fg)', bg: 'var(--tint-purple-bg)' },
]

export function GenderPicker({ value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap' }}>
      {GENDER_OPTIONS.map(opt => {
        const selected = value === opt.value
        return (
          <button
            key={opt.value}
            onClick={() => onChange(selected ? null : opt.value)}
            style={{
              padding: '6px 14px', borderRadius: 20, cursor: 'pointer',
              border: `1px solid ${selected ? opt.active : 'var(--border)'}`,
              background: selected ? opt.bg : 'transparent',
              color: selected ? opt.active : 'var(--muted)',
              fontSize: 13, fontWeight: selected ? 700 : 400,
              transition: 'all .15s',
            }}
          >
            {opt.icon} {opt.label}
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
