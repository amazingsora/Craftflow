import React, { useState, useEffect } from 'react'
import ProcessTab from './components/ProcessTab.jsx'
import GenerateTab from './components/GenerateTab.jsx'
import ComposeTab from './components/ComposeTab.jsx'
import CharacterTab from './components/CharacterTab.jsx'
import ArtStyleTab from './components/ArtStyleTab.jsx'

const TABS = [
  { id: 'process', label: '草稿 → 線稿' },
  { id: 'generate', label: '文字 → 生圖' },
  { id: 'compose', label: '草圖問答' },
  { id: 'character', label: '角色管理' },
  { id: 'artstyle', label: '畫風' },
]

const S = {
  page: { minHeight: '100vh', display: 'flex', flexDirection: 'column', padding: '24px 32px', gap: 20 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  headerLeft: {},
  title: { fontSize: 22, fontWeight: 700, letterSpacing: 1, color: 'var(--accent)' },
  subtitle: { fontSize: 13, color: 'var(--muted)', marginTop: 4 },
  modelSelect: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text)',
    padding: '6px 10px',
    fontSize: 13,
    outline: 'none',
    maxWidth: 260,
  },
  modelLabel: { fontSize: 11, color: 'var(--muted)', marginBottom: 4 },
  tabBar: { display: 'flex', gap: 8, borderBottom: '1px solid var(--border)', paddingBottom: 0 },
  tab: {
    padding: '9px 22px',
    border: 'none',
    background: 'transparent',
    color: 'var(--muted)',
    fontSize: 14,
    cursor: 'pointer',
    borderBottom: '2px solid transparent',
    marginBottom: -1,
    transition: 'color .15s',
  },
  tabActive: { color: 'var(--text)', borderBottom: '2px solid var(--accent)', fontWeight: 600 },
  content: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: 24,
  },
  // History panel
  historyPanel: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: '14px 20px',
  },
  historyHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  historyTitle: { fontSize: 13, fontWeight: 600, color: 'var(--muted)' },
  clearBtn: {
    fontSize: 12,
    color: 'var(--muted)',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    padding: '2px 6px',
  },
  historyScroll: {
    display: 'flex',
    gap: 10,
    overflowX: 'auto',
    paddingBottom: 4,
  },
  historyEmpty: { color: 'var(--muted)', fontSize: 13 },
  historyItem: {
    flex: '0 0 auto',
    width: 100,
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    cursor: 'pointer',
  },
  historyThumb: {
    width: 100,
    height: 100,
    objectFit: 'cover',
    borderRadius: 8,
    border: '1px solid var(--border)',
    transition: 'border-color .15s',
  },
  badge: {
    fontSize: 11,
    borderRadius: 4,
    padding: '1px 6px',
    fontWeight: 600,
    alignSelf: 'flex-start',
  },
  badgeProcess: { background: '#2d3a5c', color: '#7eb8f7' },
  badgeGenerate: { background: '#3a2d5c', color: '#c07ef7' },
  badgeCompose: { background: '#1e3a2d', color: '#7ef7b0' },
  historyMeta: { fontSize: 11, color: 'var(--muted)', lineHeight: 1.3 },
}

function formatTime(ts) {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}

export default function App() {
  const [tab, setTab] = useState(() => localStorage.getItem('craftflow_tab') ?? 'process')
  const [history, setHistory] = useState([])
  const [checkpoints, setCheckpoints] = useState([])
  const [activeCheckpoint, setActiveCheckpoint] = useState('')

  useEffect(() => {
    fetch('/api/v1/settings/checkpoints')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return
        setCheckpoints(data.checkpoints ?? [])
        setActiveCheckpoint(data.active ?? '')
      })
      .catch(() => {})
  }, [])

  const onCheckpointChange = async (name) => {
    setActiveCheckpoint(name)
    await fetch('/api/v1/settings/checkpoint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checkpoint: name }),
    }).catch(() => {})
  }

  const switchTab = (id) => {
    localStorage.setItem('craftflow_tab', id)
    setTab(id)
  }

  const addHistory = (item) => {
    setHistory(prev => [{ ...item, id: Date.now(), ts: Date.now() }, ...prev])
  }

  return (
    <div style={S.page}>
      <div style={S.header}>
        <div style={S.headerLeft}>
          <div style={S.title}>Craftflow 生圖測試台</div>
          <div style={S.subtitle}>ComfyUI · {activeCheckpoint || '未連線'} · localhost:8188</div>
        </div>
        {checkpoints.length > 0 && (
          <div style={{ textAlign: 'right' }}>
            <div style={S.modelLabel}>Checkpoint</div>
            <select
              style={S.modelSelect}
              value={activeCheckpoint}
              onChange={e => onCheckpointChange(e.target.value)}
            >
              {checkpoints.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div style={S.tabBar}>
        {TABS.map((t) => (
          <button
            key={t.id}
            style={{ ...S.tab, ...(tab === t.id ? S.tabActive : {}) }}
            onClick={() => switchTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 用 display:none 切換，保留各 Tab 的 React state */}
      <div style={S.content}>
        <div style={{ display: tab === 'process' ? 'block' : 'none' }}>
          <ProcessTab onAddHistory={addHistory} />
        </div>
        <div style={{ display: tab === 'generate' ? 'block' : 'none' }}>
          <GenerateTab onAddHistory={addHistory} />
        </div>
        <div style={{ display: tab === 'compose' ? 'block' : 'none' }}>
          <ComposeTab onAddHistory={addHistory} />
        </div>
        <div style={{ display: tab === 'character' ? 'block' : 'none' }}>
          <CharacterTab />
        </div>
        <div style={{ display: tab === 'artstyle' ? 'block' : 'none' }}>
          <ArtStyleTab />
        </div>
      </div>

      {/* History panel — 一直顯示在底部 */}
      <div style={S.historyPanel}>
        <div style={S.historyHeader}>
          <span style={S.historyTitle}>歷史記錄 ({history.length})</span>
          {history.length > 0 && (
            <button style={S.clearBtn} onClick={() => setHistory([])}>清除</button>
          )}
        </div>
        {history.length === 0
          ? <span style={S.historyEmpty}>尚無記錄，生成後圖片會保留在此</span>
          : (
            <div style={S.historyScroll}>
              {history.map((item) => (
                <a
                  key={item.id}
                  href={item.url}
                  download={item.filename}
                  style={S.historyItem}
                  title="點擊下載"
                >
                  <img src={item.url} style={S.historyThumb} alt="" />
                  <span style={{
                    ...S.badge,
                    ...(item.type === 'process' ? S.badgeProcess
                      : item.type === 'generate' ? S.badgeGenerate
                      : S.badgeCompose),
                  }}>
                    {item.type === 'process' ? '線稿' : item.type === 'generate' ? '生圖' : '問答'}
                  </span>
                  <span style={S.historyMeta}>
                    {formatTime(item.ts)}<br />
                    {item.label}
                  </span>
                </a>
              ))}
            </div>
          )
        }
      </div>
    </div>
  )
}
