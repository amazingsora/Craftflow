import React, { useState, useEffect } from 'react'
import ProcessTab from './components/ProcessTab.jsx'
import GenerateTab from './components/GenerateTab.jsx'
import ComposeTab from './components/ComposeTab.jsx'
import CharacterTab from './components/CharacterTab.jsx'
import ArtStyleTab from './components/ArtStyleTab.jsx'
import TrainingTab from './components/TrainingTab.jsx'
import SettingsTab from './components/SettingsTab.jsx'

const _HISTORY_KEY = 'craftflow_history_v2'
const _MAX_HISTORY = 100
const _THUMB_PX = 300

async function _makeThumbnail(url) {
  return new Promise(resolve => {
    const img = new Image()
    img.onload = () => {
      try {
        const scale = Math.min(1, _THUMB_PX / Math.max(img.naturalWidth || 1, img.naturalHeight || 1))
        const c = document.createElement('canvas')
        c.width = Math.round((img.naturalWidth || 300) * scale)
        c.height = Math.round((img.naturalHeight || 300) * scale)
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
        resolve(c.toDataURL('image/jpeg', 0.72))
      } catch { resolve(null) }
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
}

function _saveHistory(items) {
  try {
    localStorage.setItem(_HISTORY_KEY, JSON.stringify(
      items.map(h => ({ ...h, url: h.thumbnail ?? h.url }))
    ))
  } catch {
    try {
      localStorage.setItem(_HISTORY_KEY, JSON.stringify(
        items.slice(0, 40).map(h => ({ ...h, url: h.thumbnail ?? h.url }))
      ))
    } catch {}
  }
}

function _badgeStyle(type, S) {
  if (type === 'process') return S.badgeProcess
  if (type === 'generate' || type === 'i2i' || type === 'controlnet') return S.badgeGenerate
  return S.badgeCompose
}

function _badgeLabel(type) {
  if (type === 'process') return '線稿'
  if (type === 'i2i') return 'i2i'
  if (type === 'controlnet') return 'CtrlNet'
  if (type === 'generate') return '生圖'
  return '問答'
}

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
    gap: 14,
    overflowX: 'auto',
    paddingBottom: 6,
  },
  historyEmpty: { color: 'var(--muted)', fontSize: 13 },
  historyItemWrap: {
    flex: '0 0 auto',
    width: 150,
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    position: 'relative',
  },
  historyThumb: {
    width: 150,
    height: 150,
    objectFit: 'cover',
    borderRadius: 10,
    border: '1px solid var(--border)',
    cursor: 'zoom-in',
    transition: 'border-color .15s',
    display: 'block',
  },
  historyDeleteBtn: {
    position: 'absolute',
    top: 5,
    left: 5,
    width: 20,
    height: 20,
    borderRadius: '50%',
    background: 'rgba(0,0,0,.75)',
    border: 'none',
    color: '#fff',
    fontSize: 13,
    lineHeight: '20px',
    textAlign: 'center',
    cursor: 'pointer',
    padding: 0,
    zIndex: 1,
  },
  historyToggleBtn: {
    fontSize: 12,
    color: 'var(--muted)',
    background: 'none',
    border: '1px solid var(--border)',
    borderRadius: 6,
    cursor: 'pointer',
    padding: '2px 8px',
  },
  lightboxOverlay: {
    position: 'fixed', inset: 0,
    background: 'rgba(0,0,0,.82)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 2000,
  },
  lightboxBox: {
    position: 'relative',
    display: 'flex', flexDirection: 'column',
    maxWidth: '80vw',
  },
  lightboxImg: {
    maxWidth: '80vw',
    maxHeight: '78vh',
    borderRadius: 10,
    display: 'block',
    objectFit: 'contain',
  },
  lightboxClose: {
    position: 'absolute',
    top: -14,
    right: -14,
    width: 28,
    height: 28,
    borderRadius: '50%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    color: 'var(--text)',
    fontSize: 16,
    cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1,
  },
  lightboxFooter: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '8px 4px 0',
  },
  badge: {
    fontSize: 11,
    borderRadius: 4,
    padding: '2px 7px',
    fontWeight: 700,
    position: 'absolute',
    top: 6,
    right: 6,
    zIndex: 1,
  },
  badgeProcess: { background: '#2d3a5c', color: '#7eb8f7' },
  badgeGenerate: { background: '#3a2d5c', color: '#c07ef7' },
  badgeCompose: { background: '#1e3a2d', color: '#7ef7b0' },
  historyMeta: { fontSize: 12, color: 'var(--text)', lineHeight: 1.5 },
  historyMetaSub: { fontSize: 11, color: 'var(--muted)', lineHeight: 1.4, marginTop: 1 },
  gearBtn: {
    background: 'none',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--muted)',
    fontSize: 18,
    cursor: 'pointer',
    padding: '5px 9px',
    lineHeight: 1,
    transition: 'color .15s, border-color .15s',
  },
  modalOverlay: {
    position: 'fixed', inset: 0,
    background: 'rgba(0,0,0,.55)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000,
  },
  modalBox: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 14,
    width: '100%',
    maxWidth: 520,
    maxHeight: '85vh',
    display: 'flex', flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: '0 24px 60px rgba(0,0,0,.5)',
  },
  modalHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '16px 20px',
    borderBottom: '1px solid var(--border)',
  },
  modalTitle: { fontSize: 15, fontWeight: 600, color: 'var(--text)' },
  modalClose: {
    background: 'none', border: 'none',
    color: 'var(--muted)', fontSize: 20, cursor: 'pointer',
    lineHeight: 1, padding: '2px 6px',
  },
  modalBody: { padding: '20px', overflowY: 'auto', flex: 1 },
}

function formatTime(ts) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}

function _shortModel(model) {
  if (!model) return ''
  const base = model.replace(/\.[^.]+$/, '')
  return base.length > 14 ? base.slice(0, 13) + '…' : base
}

export default function App() {
  const [tab, setTab] = useState(() => localStorage.getItem('craftflow_tab') ?? 'process')
  const [history, setHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem(_HISTORY_KEY) || '[]') }
    catch { return [] }
  })
  const [historyVisible, setHistoryVisible] = useState(
    () => localStorage.getItem('craftflow_history_visible') !== 'false'
  )
  const [lightboxItem, setLightboxItem] = useState(null)
  const [checkpoints, setCheckpoints] = useState([])
  const [activeCheckpoint, setActiveCheckpoint] = useState('')
  const [workflows, setWorkflows] = useState([])
  const [activeWorkflow, setActiveWorkflow] = useState('text_to_image.json')
  const [workflowIpaSupported, setWorkflowIpaSupported] = useState(false)
  const [generationMode, setGenerationMode] = useState(
    () => localStorage.getItem('craftflow_gen_mode') ?? 'checkpoint'
  )
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [pendingGenPrompt, setPendingGenPrompt] = useState('')
  const [historyFilter, setHistoryFilter] = useState('all')
  const [visionModels, setVisionModels] = useState([])
  const [activeVisionModel, setActiveVisionModel] = useState(
    () => localStorage.getItem('craftflow_vision_model') ?? ''
  )
  const [activeTextModel, setActiveTextModel] = useState(
    () => localStorage.getItem('craftflow_text_model') ?? ''
  )

  useEffect(() => {
    const savedCheckpoint   = localStorage.getItem('craftflow_checkpoint')
    const savedWorkflow     = localStorage.getItem('craftflow_workflow')
    const savedVisionModel  = localStorage.getItem('craftflow_vision_model')
    const savedTextModel    = localStorage.getItem('craftflow_text_model')

    fetch('/api/v1/settings/checkpoints')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) {
          // ComfyUI 離線：仍套用 localStorage 記憶值
          if (savedCheckpoint) setActiveCheckpoint(savedCheckpoint)
          return
        }
        const list = data.checkpoints ?? []
        setCheckpoints(list)
        const target = savedCheckpoint && list.includes(savedCheckpoint)
          ? savedCheckpoint
          : (data.active ?? list[0] ?? '')
        setActiveCheckpoint(target)
        if (target && target !== data.active) {
          fetch('/api/v1/settings/checkpoint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ checkpoint: target }),
          }).catch(() => {})
        }
      })
      .catch(() => {
        if (savedCheckpoint) setActiveCheckpoint(savedCheckpoint)
      })

    fetch('/api/v1/settings/workflows')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return
        const list = data.workflows ?? []
        setWorkflows(list)
        const target = (savedWorkflow && list.includes(savedWorkflow))
          ? savedWorkflow
          : (list.includes(data.active) ? data.active : (list[0] ?? 'text_to_image.json'))
        setActiveWorkflow(target)
        setWorkflowIpaSupported(!!(data.ipa_support?.[target]))
        // checkpoint 模式永遠讓後端用 text_to_image.json；workflow 模式才套用自訂 workflow
        const backendWorkflow = (localStorage.getItem('craftflow_gen_mode') ?? 'checkpoint') === 'workflow'
          ? target
          : 'text_to_image.json'
        if (backendWorkflow !== data.active) {
          fetch('/api/v1/settings/workflow', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workflow: backendWorkflow }),
          }).catch(() => {})
        }
      })
      .catch(() => {})

    fetch('/api/v1/settings/vision-models')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return
        const models = data.models ?? []
        setVisionModels(models)
        const target = (savedVisionModel && models.includes(savedVisionModel))
          ? savedVisionModel
          : (data.default ?? models[0] ?? '')
        setActiveVisionModel(target)
        if (target) {
          fetch('/api/v1/settings/vision-model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: target }),
          }).catch(() => {})
        }
      })
      .catch(() => {})

    Promise.all([
      fetch('/api/v1/settings/vision-models').then(r => r.ok ? r.json() : {}),
      fetch('/api/v1/settings/text-model').then(r => r.ok ? r.json() : {}),
    ])
      .then(([vData, tData]) => {
        const models = vData.models ?? []
        const textDefault = tData.default ?? tData.model ?? models[0] ?? ''
        const target = (savedTextModel && models.includes(savedTextModel))
          ? savedTextModel
          : textDefault
        setActiveTextModel(target)
        if (target) {
          fetch('/api/v1/settings/text-model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: target }),
          }).catch(() => {})
        }
      })
      .catch(() => {})
  }, [])

  const onVisionModelChange = async (model) => {
    setActiveVisionModel(model)
    localStorage.setItem('craftflow_vision_model', model)
    await fetch('/api/v1/settings/vision-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    }).catch(() => {})
  }

  const onTextModelChange = async (model) => {
    setActiveTextModel(model)
    localStorage.setItem('craftflow_text_model', model)
    await fetch('/api/v1/settings/text-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    }).catch(() => {})
  }

  const onCheckpointChange = async (name) => {
    setActiveCheckpoint(name)
    localStorage.setItem('craftflow_checkpoint', name)
    await fetch('/api/v1/settings/checkpoint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checkpoint: name }),
    }).catch(() => {})
  }

  const onWorkflowChange = async (name) => {
    setActiveWorkflow(name)
    localStorage.setItem('craftflow_workflow', name)
    const res = await fetch('/api/v1/settings/workflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow: name }),
    }).catch(() => null)
    if (res?.ok) {
      const data = await res.json().catch(() => null)
      if (data) setWorkflowIpaSupported(!!data.ipa_supported)
    }
  }

  const onGenerationModeChange = async (mode) => {
    setGenerationMode(mode)
    localStorage.setItem('craftflow_gen_mode', mode)
    // sync workflow to backend: checkpoint mode resets to default system workflow
    const workflowToSync = mode === 'checkpoint' ? 'text_to_image.json' : activeWorkflow
    await fetch('/api/v1/settings/workflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow: workflowToSync }),
    }).catch(() => {})
  }

  const switchTab = (id) => {
    localStorage.setItem('craftflow_tab', id)
    setTab(id)
  }

  const onSendToGenerate = (promptZh) => {
    setPendingGenPrompt(promptZh)
    switchTab('generate')
  }

  const addHistory = async (item) => {
    const thumbnail = await _makeThumbnail(item.url)
    setHistory(prev => {
      const model = generationMode === 'workflow'
        ? activeWorkflow.replace('.json', '')
        : activeCheckpoint
      const newItem = { ...item, id: Date.now(), ts: Date.now(), thumbnail, model: model || undefined }
      const updated = [newItem, ...prev].slice(0, _MAX_HISTORY)
      _saveHistory(updated)
      return updated
    })
  }

  const deleteHistory = (id) => {
    setHistory(prev => {
      const updated = prev.filter(h => h.id !== id)
      _saveHistory(updated)
      return updated
    })
  }

  const clearHistory = () => {
    setHistory([])
    localStorage.removeItem(_HISTORY_KEY)
  }

  const toggleHistoryVisible = () => {
    setHistoryVisible(v => {
      localStorage.setItem('craftflow_history_visible', String(!v))
      return !v
    })
  }

  return (
    <div style={S.page}>
      <div style={S.header}>
        <div style={S.headerLeft}>
          <div style={S.title}>Craftflow</div>
          <div style={S.subtitle}>
            ComfyUI · {generationMode === 'workflow'
              ? (activeWorkflow.replace('.json', '') || 'workflow 模式')
              : (activeCheckpoint || '未設定 checkpoint')
            } · localhost:8188
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={S.modelLabel}>
              {generationMode === 'workflow' ? 'Workflow 模式' : 'Checkpoint 模式'}
            </div>
            <div style={{ fontSize: 13, color: 'var(--muted)' }}>
              {generationMode === 'workflow'
                ? (activeWorkflow.replace('.json', '') || '—')
                : (activeCheckpoint || '未設定')}
            </div>
          </div>
          <button
            style={S.gearBtn}
            onClick={() => setSettingsOpen(true)}
            title="設定"
          >⚙</button>
        </div>
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
          <GenerateTab
            onAddHistory={addHistory}
            pendingPrompt={pendingGenPrompt}
            onPromptConsumed={() => setPendingGenPrompt('')}
          />
        </div>
        <div style={{ display: tab === 'compose' ? 'block' : 'none' }}>
          <ComposeTab
            onAddHistory={addHistory}
            activeVisionModel={activeVisionModel}
            ipaSupported={generationMode === 'checkpoint' || workflowIpaSupported}
            onSendToGenerate={onSendToGenerate}
          />
        </div>
        <div style={{ display: tab === 'character' ? 'block' : 'none' }}>
          <CharacterTab onAddHistory={addHistory} onSendToGenerate={onSendToGenerate} />
        </div>
        <div style={{ display: tab === 'artstyle' ? 'block' : 'none' }}>
          <ArtStyleTab />
        </div>
      </div>

      {/* Settings modal */}
      {settingsOpen && (
        <div style={S.modalOverlay} onClick={e => e.target === e.currentTarget && setSettingsOpen(false)}>
          <div style={{ ...S.modalBox, maxWidth: 560 }}>
            <div style={S.modalHeader}>
              <span style={S.modalTitle}>⚙ 設定</span>
              <button style={S.modalClose} onClick={() => setSettingsOpen(false)}>×</button>
            </div>
            <div style={S.modalBody}>
              <SettingsTab
                generationMode={generationMode}
                setGenerationMode={onGenerationModeChange}
                checkpoints={checkpoints}
                activeCheckpoint={activeCheckpoint}
                onCheckpointChange={onCheckpointChange}
                workflows={workflows}
                activeWorkflow={activeWorkflow}
                onWorkflowChange={onWorkflowChange}
                visionModels={visionModels}
                activeVisionModel={activeVisionModel}
                onVisionModelChange={onVisionModelChange}
                activeTextModel={activeTextModel}
                onTextModelChange={onTextModelChange}
              />
              <div style={{ borderTop: '1px solid var(--border)', marginTop: 20, paddingTop: 20 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--muted)', marginBottom: 12 }}>LoRA 訓練</div>
                <TrainingTab />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* History panel */}
      <div style={S.historyPanel}>
        <div style={S.historyHeader}>
          <span style={S.historyTitle}>
            歷史記錄 ({history.length}/{_MAX_HISTORY})
          </span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {historyVisible && history.length > 0 && (
              <button style={S.clearBtn} onClick={clearHistory}>清除全部</button>
            )}
            <button style={S.historyToggleBtn} onClick={toggleHistoryVisible}>
              {historyVisible ? '隱藏 ▲' : '顯示 ▼'}
            </button>
          </div>
        </div>

        {historyVisible && history.length > 0 && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
            {[
              { key: 'all', label: '全部' },
              { key: 'process', label: '線稿' },
              { key: 'generate', label: '生圖' },
              { key: 'compose', label: '問答' },
              { key: 'character', label: '角色' },
            ].map(f => (
              <button
                key={f.key}
                onClick={() => setHistoryFilter(f.key)}
                style={{
                  fontSize: 11, padding: '2px 10px', borderRadius: 20, cursor: 'pointer',
                  border: historyFilter === f.key ? 'none' : '1px solid var(--border)',
                  background: historyFilter === f.key ? 'var(--accent)' : 'transparent',
                  color: historyFilter === f.key ? '#fff' : 'var(--muted)',
                  fontWeight: historyFilter === f.key ? 600 : 400,
                }}
              >{f.label}</button>
            ))}
          </div>
        )}

        {historyVisible && (
          (() => {
            const filtered = historyFilter === 'all' ? history
              : historyFilter === 'generate' ? history.filter(h => ['generate', 'i2i', 'controlnet', 'ipadapter'].includes(h.type))
              : history.filter(h => h.type === historyFilter)
            return filtered.length === 0
              ? <span style={S.historyEmpty}>{history.length === 0 ? '尚無記錄，生成後圖片會保留在此' : '此類型無記錄'}</span>
              : (
              <div style={S.historyScroll}>
                {filtered.map((item) => (
                  <div key={item.id} style={S.historyItemWrap}>
                    <button
                      style={S.historyDeleteBtn}
                      onClick={() => deleteHistory(item.id)}
                      title="刪除"
                    >×</button>
                    <span style={{ ...S.badge, ..._badgeStyle(item.type, S) }}>
                      {_badgeLabel(item.type)}
                    </span>
                    <img
                      src={item.thumbnail ?? item.url}
                      style={S.historyThumb}
                      alt=""
                      onClick={() => setLightboxItem(item)}
                    />
                    <div>
                      <div style={S.historyMeta}>{formatTime(item.ts)}</div>
                      {item.label && (
                        <div style={S.historyMeta} title={item.label}>
                          {item.label.length > 22 ? item.label.slice(0, 21) + '…' : item.label}
                        </div>
                      )}
                      {item.model && (
                        <div style={S.historyMetaSub} title={item.model}>
                          {_shortModel(item.model)}
                        </div>
                      )}
                      {item.params && (item.params.ipa != null || item.params.cn != null || item.params.cnMode) && (
                        <div style={S.historyMetaSub}>
                          {item.params.ipa != null ? `IPA ${Number(item.params.ipa).toFixed(2)}` : 'IPA off'}
                          {' · '}
                          {item.params.cn != null ? `CN ${Number(item.params.cn).toFixed(2)}` : 'CN off'}
                          {item.params.cnMode ? ` (${item.params.cnMode})` : ''}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )
          })()
        )}
      </div>

      {/* Lightbox */}
      {lightboxItem && (
        <div style={S.lightboxOverlay} onClick={() => setLightboxItem(null)}>
          <div style={S.lightboxBox} onClick={e => e.stopPropagation()}>
            <button style={S.lightboxClose} onClick={() => setLightboxItem(null)}>×</button>
            <img
              src={lightboxItem.thumbnail ?? lightboxItem.url}
              style={S.lightboxImg}
              alt=""
            />
            <div style={S.lightboxFooter}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ ...S.badge, position: 'static', ..._badgeStyle(lightboxItem.type, S) }}>
                    {_badgeLabel(lightboxItem.type)}
                  </span>
                  <span style={{ fontSize: 13, color: 'var(--text)' }}>{formatTime(lightboxItem.ts)}</span>
                  {lightboxItem.model && (
                    <span style={{ fontSize: 12, color: 'var(--muted)' }} title={lightboxItem.model}>
                      {_shortModel(lightboxItem.model)}
                    </span>
                  )}
                </div>
                {lightboxItem.label && (
                  <div style={{ fontSize: 13, color: 'var(--muted)', maxWidth: '60vw' }}>
                    {lightboxItem.label}
                  </div>
                )}
                {lightboxItem.params && (lightboxItem.params.ipa != null || lightboxItem.params.cn != null || lightboxItem.params.cnMode) && (
                  <div style={{ fontSize: 12, color: 'var(--muted)' }}>
                    {lightboxItem.params.ipa != null ? `IPA ${Number(lightboxItem.params.ipa).toFixed(2)}` : 'IPA off'}
                    {' · '}
                    {lightboxItem.params.cn != null ? `CN ${Number(lightboxItem.params.cn).toFixed(2)}` : 'CN off'}
                    {lightboxItem.params.cnMode ? ` (${lightboxItem.params.cnMode})` : ''}
                  </div>
                )}
              </div>
              <a
                href={lightboxItem.url}
                download={lightboxItem.filename}
                style={{ fontSize: 13, color: 'var(--accent)', textDecoration: 'none', fontWeight: 600, flexShrink: 0 }}
              >
                下載
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
