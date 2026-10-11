import React, { useState, useEffect } from 'react'
import ProcessTab from './components/ProcessTab.jsx'
import GenerateTab from './components/GenerateTab.jsx'
import ComposeTab from './components/ComposeTab.jsx'
import CharacterTab from './components/CharacterTab.jsx'
import ArtStyleTab from './components/ArtStyleTab.jsx'
import TrainingTab from './components/TrainingTab.jsx'
import SettingsTab from './components/SettingsTab.jsx'
import NovelTab from './components/NovelTab.jsx'
import { ensureNotifyPermission, notifyDone } from './notify.js'
import { GenerationInfo } from './components/GenerationInfo.jsx'
import { Icon } from './components/Icon.jsx'

const _HISTORY_KEY = 'craftflow_history_v2'
const _MAX_HISTORY = 100
// 縮圖邊長：過小在「檢視」放大時會糊；過大會撐爆 localStorage（見 _saveHistory 降階）
const _THUMB_PX = 768
const _THUMB_QUALITY = 0.85
// localStorage 配額超出時，依序砍到剩幾筆再試（最後一階只留最新 5 筆）。
const _HISTORY_QUOTA_STEPS = [100, 40, 15, 5]
const _STATUS_POLL_MS = 20000  // 系統狀態輪詢間隔

// header 服務狀態燈：顯示 Ollama / ComfyUI 是否在線，離線時 hover 顯示提示
function ServiceStatus({ status }) {
  // status 為 null（尚未取得 / 後端離線）時，兩者皆視為未知（灰）
  const known = !!status
  const ollamaOk = known && status.services?.ollama?.available
  const comfyOk = known && status.services?.comfyui?.available
  const dots = [
    { label: 'Ollama', ok: ollamaOk, color: !known ? 'var(--faint)' : (ollamaOk ? 'var(--success)' : 'var(--danger)') },
    { label: 'ComfyUI', ok: comfyOk, color: !known ? 'var(--faint)' : (comfyOk ? 'var(--success)' : 'var(--danger)') },
  ]
  const hints = (status?.hints ?? [])
  const tip = !known
    ? '無法取得系統狀態（後端可能未啟動）'
    : (hints.length ? hints.join('\n') : 'Ollama 與 ComfyUI 皆正常運作')
  return (
    <div title={tip} style={{ display: 'flex', gap: 14, alignItems: 'center', cursor: 'default' }}>
      {dots.map(d => (
        <span key={d.label} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{
            width: 7, height: 7, borderRadius: '50%', background: d.color, display: 'inline-block',
            boxShadow: `0 0 0 3px color-mix(in srgb, ${d.color} 18%, transparent)`,
            animation: known && !d.ok ? 'cf-pulse 1.6s ease-in-out infinite' : 'none',
          }} />
          {d.label}
        </span>
      ))}
    </div>
  )
}

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
        resolve(c.toDataURL('image/jpeg', _THUMB_QUALITY))
      } catch { resolve(null) }
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
}

// 持久化時 url 換成縮圖（blob URL 重整即失效）；超出 localStorage 配額時逐階減量重試
function _saveHistory(items) {
  for (const n of _HISTORY_QUOTA_STEPS) {
    try {
      localStorage.setItem(_HISTORY_KEY, JSON.stringify(
        items.slice(0, n).map(h => ({ ...h, url: h.thumbnail ?? h.url }))
      ))
      return n
    } catch { /* 配額不足 → 再砍一階 */ }
  }
  return 0
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
  { id: 'process', label: '草稿 → 線稿', icon: 'brush', hidden: true },
  { id: 'novel', label: '小說', icon: 'book-open-text', desc: '章節寫作與 AI 分析' },
  { id: 'generate', label: '文字生圖', icon: 'wand-sparkles', desc: '中文描述 → 提示詞 → ComfyUI' },
  { id: 'compose', label: '草圖問答', icon: 'messages-square', desc: '以草圖向視覺模型提問' },
  { id: 'character', label: '角色管理', icon: 'users', desc: '作品、勢力與角色人設' },
  { id: 'artstyle', label: '畫風', icon: 'palette', desc: '可重用的畫風配方' },
]

const HISTORY_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'process', label: '線稿' },
  { key: 'generate', label: '生圖' },
  { key: 'compose', label: '問答' },
  { key: 'character', label: '角色' },
]

const S = {
  app: {
    height: '100vh', display: 'grid', overflow: 'hidden',
    gridTemplateColumns: 'var(--rail) minmax(0, 1fr)',
    gridTemplateRows: 'minmax(0, 1fr) 28px',
    transition: 'grid-template-columns .22s var(--ease)',
  },
  // ── Rail ──
  sidebar: {
    gridRow: '1 / 3', minWidth: 0, overflow: 'hidden',
    display: 'flex', flexDirection: 'column', gap: 2,
    padding: '14px 10px 10px',
    borderRight: '1px solid var(--border)',
    background: 'var(--surface)',
  },
  brandRow: { display: 'flex', alignItems: 'center', gap: 10, padding: '2px 6px 18px', minHeight: 44 },
  brandMark: {
    width: 22, height: 22, borderRadius: 6, flexShrink: 0, position: 'relative',
    background: 'var(--text)', display: 'grid', placeItems: 'center',
  },
  brandMarkInner: {
    width: 10, height: 10, background: 'var(--accent)',
    clipPath: 'polygon(0 0, 100% 0, 0 100%)', transform: 'translate(-1px,-1px)',
  },
  brand: { fontSize: 15, fontWeight: 700, letterSpacing: '-.02em', color: 'var(--text)', lineHeight: 1.1 },
  brandSub: { fontSize: 11, color: 'var(--muted)', lineHeight: 1.2, marginTop: 2 },
  navLabel: { fontSize: 11, fontWeight: 600, color: 'var(--faint)', padding: '0 10px 6px', letterSpacing: '.04em', whiteSpace: 'nowrap' },
  navItem: {
    display: 'flex', alignItems: 'center', gap: 10,
    width: '100%', height: 34, textAlign: 'left',
    padding: '0 10px', border: 'none', borderRadius: 'var(--r)',
    background: 'transparent', color: 'var(--text-2)',
    fontSize: 13.5, fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap', overflow: 'hidden',
    position: 'relative',
  },
  navItemActive: { background: 'var(--accent-soft)', color: 'var(--accent)', fontWeight: 600 },
  sidebarFooter: {
    marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 2,
    paddingTop: 8, borderTop: '1px solid var(--border)',
  },
  // ── Main ──
  main: { minWidth: 0, minHeight: 0, display: 'grid', gridTemplateRows: '48px minmax(0, 1fr)', position: 'relative' },
  topbar: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '0 12px 0 12px', background: 'var(--surface)', borderBottom: '1px solid var(--border)',
    minWidth: 0,
  },
  iconBtn: {
    width: 30, height: 30, display: 'grid', placeItems: 'center', flexShrink: 0,
    border: 'none', borderRadius: 'var(--r)', background: 'transparent', color: 'var(--muted)', cursor: 'pointer',
  },
  topbarTitle: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 600, color: 'var(--text)', whiteSpace: 'nowrap' },
  topbarDesc: { fontSize: 12.5, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  ctxChip: {
    display: 'inline-flex', alignItems: 'center', gap: 8, maxWidth: 360, height: 30,
    padding: '0 10px', border: '1px solid var(--border-strong)', borderRadius: 'var(--r)',
    background: 'var(--surface)', color: 'var(--text-2)', fontSize: 12.5, cursor: 'pointer', flexShrink: 1, minWidth: 0,
  },
  ctxKind: { fontSize: 10.5, fontWeight: 600, color: 'var(--muted)', letterSpacing: '.04em', textTransform: 'uppercase' },
  ctxName: { fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  scroller: { minHeight: 0, overflow: 'auto', scrollbarGutter: 'stable' },
  content: { padding: '24px 28px 40px' },
  // ── Status bar ──
  statusbar: {
    gridColumn: 2, display: 'flex', alignItems: 'center', gap: 14, minWidth: 0,
    padding: '0 8px 0 14px', background: 'var(--surface)', borderTop: '1px solid var(--border)',
    fontSize: 11.5, color: 'var(--muted)', whiteSpace: 'nowrap', position: 'relative', zIndex: 30,
  },
  sbSep: { width: 1, height: 12, background: 'var(--border-strong)', flexShrink: 0 },
  sbItem: { display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 },
  sbBtn: {
    display: 'inline-flex', alignItems: 'center', gap: 6, height: 22, padding: '0 7px',
    border: 'none', borderRadius: 'var(--r-sm)', background: 'transparent', color: 'var(--text-2)',
    fontSize: 11.5, cursor: 'pointer',
  },
  sbCount: {
    fontFamily: 'var(--font-mono)', fontSize: 10, lineHeight: '15px', padding: '0 5px', borderRadius: 3,
    background: 'var(--accent)', color: 'var(--accent-contrast)',
  },
  // ── History drawer ──
  drawer: {
    position: 'absolute', left: 0, right: 0, bottom: 0, zIndex: 20,
    background: 'var(--surface)', borderTop: '1px solid var(--border-strong)',
    boxShadow: '0 -16px 40px -20px rgba(13,17,23,.35)',
    animation: 'cf-drawer .22s var(--ease) both',
    display: 'flex', flexDirection: 'column', maxHeight: '46vh',
  },
  drawerHead: { display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--border)' },
  historyTitle: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600, color: 'var(--text)' },
  historyCount: { fontFamily: 'var(--font-mono)', fontSize: 11.5, fontWeight: 400, color: 'var(--muted)' },
  seg: { display: 'inline-flex', border: '1px solid var(--border-strong)', borderRadius: 'var(--r)', overflow: 'hidden' },
  segBtn: { padding: '3px 11px', fontSize: 12, border: 'none', borderLeft: '1px solid var(--border-strong)', background: 'var(--surface)', color: 'var(--text-2)', cursor: 'pointer' },
  segBtnActive: { background: 'var(--accent-soft)', color: 'var(--accent)', fontWeight: 600 },
  clearBtn: {
    fontSize: 12, color: 'var(--muted)', background: 'none', border: 'none',
    cursor: 'pointer', padding: '4px 8px', borderRadius: 'var(--r-sm)',
  },
  historyScroll: { display: 'flex', gap: 12, overflowX: 'auto', padding: '14px 16px 16px' },
  historyEmpty: { color: 'var(--muted)', fontSize: 13, padding: '28px 16px', textAlign: 'center' },
  historyItemWrap: { flex: '0 0 auto', width: 148, display: 'flex', flexDirection: 'column', gap: 6, position: 'relative' },
  historyThumbBox: { position: 'relative', width: 148, height: 148, borderRadius: 'var(--r)', overflow: 'hidden', background: 'var(--canvas)', boxShadow: '0 0 0 1px var(--border)' },
  historyThumb: { width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 15%', cursor: 'zoom-in', display: 'block' },
  historyDeleteBtn: {
    position: 'absolute', top: 6, left: 6, width: 22, height: 22,
    borderRadius: 'var(--r-sm)', background: 'rgba(13,17,23,.72)', border: 'none', color: '#fff',
    display: 'grid', placeItems: 'center', cursor: 'pointer', padding: 0, zIndex: 1,
  },
  lightboxOverlay: {
    position: 'fixed', inset: 0, background: 'rgba(8,9,11,.86)', backdropFilter: 'blur(6px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000, padding: 32,
    animation: 'cf-fade .18s var(--ease) both',
  },
  lightboxBox: { position: 'relative', display: 'flex', flexDirection: 'column', maxWidth: '86vw', animation: 'cf-pop .22s var(--ease) both' },
  lightboxImg: { maxWidth: '86vw', maxHeight: '76vh', borderRadius: 'var(--r)', display: 'block', objectFit: 'contain', alignSelf: 'center' },
  lightboxClose: {
    position: 'fixed', top: 18, right: 18, width: 36, height: 36, borderRadius: 'var(--r)',
    background: 'rgba(255,255,255,.1)', border: '1px solid rgba(255,255,255,.16)', color: '#fff',
    cursor: 'pointer', display: 'grid', placeItems: 'center', zIndex: 1,
  },
  lightboxFooter: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 24,
    marginTop: 12, padding: '12px 14px', borderRadius: 'var(--r-lg)',
    background: 'var(--surface)', border: '1px solid var(--border)',
  },
  badge: {
    fontSize: 10.5, borderRadius: 3, padding: '1px 6px', fontWeight: 600, lineHeight: 1.5,
    position: 'absolute', top: 6, right: 6, zIndex: 1,
  },
  badgeProcess: { background: 'var(--tint-blue-bg)', color: 'var(--tint-blue-fg)' },
  badgeGenerate: { background: 'var(--tint-purple-bg)', color: 'var(--tint-purple-fg)' },
  badgeCompose: { background: 'var(--tint-green-bg)', color: 'var(--tint-green-fg)' },
  historyMeta: { fontSize: 12, color: 'var(--text)', lineHeight: 1.45, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  historyMetaSub: { fontSize: 11, color: 'var(--muted)', lineHeight: 1.4, marginTop: 1, fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  // ── Modal ──
  modalOverlay: {
    position: 'fixed', inset: 0, background: 'var(--scrim)', backdropFilter: 'blur(3px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24,
    animation: 'cf-fade .16s var(--ease) both',
  },
  modalBox: {
    background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
    width: '100%', maxWidth: 520, maxHeight: '86vh',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
    boxShadow: 'var(--shadow-modal)', animation: 'cf-pop .22s var(--ease) both',
  },
  modalHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '12px 12px 12px 18px', borderBottom: '1px solid var(--border)',
  },
  modalTitle: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 600, color: 'var(--text)' },
  modalBody: { padding: '18px 20px 22px', overflowY: 'auto', flex: 1 },
}

// /settings/capabilities → App 狀態（初次載入與重抓共用，避免兩處欄位漂移）
function toCapability(cap) {
  return {
    ipa_supported: !!cap.ipa_supported,
    cn_supported:  !!cap.cn_supported,
    cn_fallback:   cap.cn_fallback ?? null,
    face_detailer_supported: !!cap.face_detailer_supported,
    family:        cap.family ?? 'sdxl',
    gpu_tier:      cap.gpu_tier ?? null,
    gpu_tier_source: cap.gpu_tier_source ?? '',
    hires_enabled: !!cap.hires_enabled,
  }
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
  const [tab, setTab] = useState(() => {
    const saved = localStorage.getItem('craftflow_tab')
    const visible = TABS.filter(t => !t.hidden).map(t => t.id)
    return (saved && visible.includes(saved)) ? saved : 'generate'
  })
  const [history, setHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem(_HISTORY_KEY) || '[]') }
    catch { return [] }
  })
  const [historyVisible, setHistoryVisible] = useState(
    () => localStorage.getItem('craftflow_history_visible') === 'true'
  )
  const [lightboxItem, setLightboxItem] = useState(null)
  const [checkpoints, setCheckpoints] = useState([])
  const [activeCheckpoint, setActiveCheckpoint] = useState('')
  const [workflows, setWorkflows] = useState([])
  const [activeWorkflow, setActiveWorkflow] = useState('text_to_image.json')
  // capability 由 /settings/capabilities 取得；cn_fallback＝CN 不支援時的替代路徑
  const [capability, setCapability] = useState({ ipa_supported: true, cn_supported: true, cn_fallback: null, face_detailer_supported: false, family: 'sdxl', gpu_tier: null, gpu_tier_source: '', hires_enabled: false })
  const [generationMode, setGenerationMode] = useState(
    () => localStorage.getItem('craftflow_gen_mode') ?? 'checkpoint'
  )
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [trainingOpen, setTrainingOpen] = useState(false)  // R-08：LoRA 訓練獨立入口
  const [pendingGenPrompt, setPendingGenPrompt] = useState('')
  const [historyFilter, setHistoryFilter] = useState('all')
  const [visionModels, setVisionModels] = useState([])
  const [visionOnlyModels, setVisionOnlyModels] = useState([])  // 具視覺能力者，視覺欄專用
  const [modelCaps, setModelCaps] = useState({})                // {name: [capabilities]}，供能力標籤
  const [activeVisionModel, setActiveVisionModel] = useState(
    () => localStorage.getItem('craftflow_vision_model') ?? ''
  )
  const [activeTextModel, setActiveTextModel] = useState(
    () => localStorage.getItem('craftflow_text_model') ?? ''
  )
  const [svcStatus, setSvcStatus] = useState(null)  // { services:{ollama,comfyui,database}, hints:[] }
  const [theme, setTheme] = useState(() => localStorage.getItem('craftflow_theme') ?? 'light')

  // 主題切換：data-theme 掛在 <html>，token 定義見 index.css
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('craftflow_theme', theme)
  }, [theme])

  // 輪詢系統狀態（Ollama / ComfyUI / DB），供 header 狀態燈使用
  useEffect(() => {
    let alive = true
    const poll = () => {
      fetch('/api/v1/status/')
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (alive && data) setSvcStatus(data) })
        .catch(() => { if (alive) setSvcStatus(null) })
    }
    poll()
    const id = setInterval(poll, _STATUS_POLL_MS)
    return () => { alive = false; clearInterval(id) }
  }, [])

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
        // checkpoint 模式永遠讓後端用 text_to_image.json；workflow 模式才套用自訂 workflow
        const backendWorkflow = (localStorage.getItem('craftflow_gen_mode') ?? 'checkpoint') === 'workflow'
          ? target
          : 'text_to_image.json'
        const syncNeeded = backendWorkflow !== data.active
        const doSync = syncNeeded
          ? fetch('/api/v1/settings/workflow', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ workflow: backendWorkflow }),
            }).catch(() => {})
          : Promise.resolve()
        // 等 workflow 同步後再抓 capability（確保後端 state 已更新）
        doSync.then(() => fetch('/api/v1/settings/capabilities').then(r => r.ok ? r.json() : null).then(cap => {
          if (cap) setCapability(toCapability(cap))
        }).catch(() => {}))
      })
      .catch(() => {})

    fetch('/api/v1/settings/vision-models')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return
        const models = data.models ?? []
        const visionOnly = data.vision_models ?? models   // 後端未升級時退回完整清單
        setVisionModels(models)
        setVisionOnlyModels(visionOnly)
        setModelCaps(data.caps ?? {})
        // 視覺欄只能選具視覺能力者：優先記憶值 → .env 預設（須具視覺能力）→ 第一個視覺模型
        const target = (savedVisionModel && visionOnly.includes(savedVisionModel))
          ? savedVisionModel
          : (visionOnly.includes(data.default) ? data.default : (visionOnly[0] ?? ''))
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

  // 重抓 capability（切 checkpoint / workflow / 生成模式後呼叫）
  const fetchCapability = async () => {
    try {
      const r = await fetch('/api/v1/settings/capabilities')
      if (r.ok) {
        setCapability(toCapability(await r.json()))
      }
    } catch {}
  }

  const onCheckpointChange = async (name) => {
    setActiveCheckpoint(name)
    localStorage.setItem('craftflow_checkpoint', name)
    await fetch('/api/v1/settings/checkpoint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checkpoint: name }),
    }).catch(() => {})
    fetchCapability()
  }

  const onWorkflowChange = async (name) => {
    setActiveWorkflow(name)
    localStorage.setItem('craftflow_workflow', name)
    await fetch('/api/v1/settings/workflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow: name }),
    }).catch(() => {})
    fetchCapability()
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
    fetchCapability()
  }

  const switchTab = (id) => {
    localStorage.setItem('craftflow_tab', id)
    setTab(id)
  }

  const onSendToGenerate = (promptZh) => {
    setPendingGenPrompt(promptZh)
    switchTab('generate')
  }

  useEffect(() => { ensureNotifyPermission() }, [])

  // 側欄響應式收合（手動切換持久化；視窗跨 880px 門檻時自動收／展）
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem('craftflow_sidebar_collapsed')
    if (saved !== null) return saved === 'true'
    return typeof window !== 'undefined' && window.innerWidth < 880
  })
  const toggleSidebar = () => setSidebarCollapsed(v => {
    const nv = !v
    localStorage.setItem('craftflow_sidebar_collapsed', String(nv))
    return nv
  })
  useEffect(() => {
    let lastNarrow = window.innerWidth < 880
    const onResize = () => {
      const narrow = window.innerWidth < 880
      if (narrow !== lastNarrow) {
        lastNarrow = narrow
        setSidebarCollapsed(narrow)
        localStorage.setItem('craftflow_sidebar_collapsed', String(narrow))
      }
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

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
    notifyDone('生成完成', item?.label || '圖片已生成')
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

  // Esc 關閉最上層浮層（燈箱 → 設定 / 訓練 → 歷史抽屜）
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape') return
      if (lightboxItem) setLightboxItem(null)
      else if (settingsOpen) setSettingsOpen(false)
      else if (trainingOpen) setTrainingOpen(false)
      else if (historyVisible) toggleHistoryVisible()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const activeTab = TABS.find(t => t.id === tab)
  const ctxKind = generationMode === 'workflow' ? 'Workflow' : 'Checkpoint'
  const ctxName = generationMode === 'workflow'
    ? (activeWorkflow.replace('.json', '') || '—')
    : (activeCheckpoint ? activeCheckpoint.replace(/\.[^.]+$/, '') : '未設定')
  const filteredHistory = historyFilter === 'all' ? history
    : historyFilter === 'generate' ? history.filter(h => ['generate', 'i2i', 'controlnet', 'ipadapter'].includes(h.type))
    : history.filter(h => h.type === historyFilter)

  const navBtn = (t, active, onClick) => (
    <button
      key={t.id}
      className="cf-nav-item"
      style={{ ...S.navItem, ...(active ? S.navItemActive : {}), ...(sidebarCollapsed ? { justifyContent: 'center', padding: 0 } : {}) }}
      onClick={onClick}
      title={sidebarCollapsed ? t.label : undefined}
      aria-current={active ? 'page' : undefined}
    >
      <Icon name={t.icon} size={17} style={{ color: active ? 'var(--accent)' : 'var(--muted)' }} />
      {!sidebarCollapsed && <span>{t.label}</span>}
    </button>
  )

  return (
    <div style={{ ...S.app, '--rail': sidebarCollapsed ? '60px' : 'var(--rail-w)' }}>
      <aside style={{ ...S.sidebar, ...(sidebarCollapsed ? { padding: '14px 8px 10px' } : {}) }}>
        <div style={{ ...S.brandRow, ...(sidebarCollapsed ? { justifyContent: 'center', padding: '2px 0 18px' } : {}) }}>
          <span style={S.brandMark}><span style={S.brandMarkInner} /></span>
          {!sidebarCollapsed && (
            <div style={{ minWidth: 0 }}>
              <div style={S.brand}>Craftflow</div>
              <div style={S.brandSub}>本地創作助手</div>
            </div>
          )}
        </div>
        {!sidebarCollapsed && <div style={S.navLabel}>工作區</div>}
        {TABS.filter(t => !t.hidden).map((t) => navBtn(t, tab === t.id, () => switchTab(t.id)))}
        <div style={S.sidebarFooter}>
          {navBtn({ id: 'training', label: 'LoRA 訓練', icon: 'flask-conical' }, trainingOpen, () => setTrainingOpen(true))}
          {navBtn({ id: 'settings', label: '設定', icon: 'settings' }, settingsOpen, () => setSettingsOpen(true))}
        </div>
      </aside>

      <div style={S.main}>
        <header style={S.topbar}>
          <button className="cf-link" style={S.iconBtn} onClick={toggleSidebar} title="收合 / 展開側欄" aria-label="收合或展開側欄">
            <Icon name="panel-left" size={17} />
          </button>
          <div style={S.sbSep} />
          <div style={S.topbarTitle}>{activeTab?.label}</div>
          {activeTab?.desc && <div style={S.topbarDesc}>{activeTab.desc}</div>}
          <div style={{ flex: 1 }} />
          <button style={S.ctxChip} onClick={() => setSettingsOpen(true)} title="目前的生成來源（點擊開啟設定）">
            <Icon name="cpu" size={14} style={{ color: 'var(--muted)' }} />
            <span style={S.ctxKind}>{ctxKind}</span>
            <span style={S.ctxName}>{ctxName}</span>
            <Icon name="chevron-down" size={13} style={{ color: 'var(--faint)' }} />
          </button>
        </header>

        {/* 用 display:none 切換，保留各 Tab 的 React state */}
        <div style={S.scroller}>
          <main style={S.content}>
            <div style={{ display: tab === 'process' ? 'block' : 'none' }}>
              <ProcessTab onAddHistory={addHistory} />
            </div>
            <div style={{ display: tab === 'generate' ? 'block' : 'none' }}>
              <GenerateTab
                onAddHistory={addHistory}
                pendingPrompt={pendingGenPrompt}
                onPromptConsumed={() => setPendingGenPrompt('')}
                capability={capability}
              />
            </div>
            <div style={{ display: tab === 'compose' ? 'block' : 'none' }}>
              <ComposeTab
                onAddHistory={addHistory}
                activeVisionModel={activeVisionModel}
                capability={capability}
                onSendToGenerate={onSendToGenerate}
              />
            </div>
            <div style={{ display: tab === 'novel' ? 'block' : 'none' }}>
              <NovelTab />
            </div>
            <div style={{ display: tab === 'character' ? 'block' : 'none' }}>
              <CharacterTab onAddHistory={addHistory} onSendToGenerate={onSendToGenerate} capability={capability} />
            </div>
            <div style={{ display: tab === 'artstyle' ? 'block' : 'none' }}>
              <ArtStyleTab />
            </div>
          </main>
        </div>

        {/* History drawer */}
        {historyVisible && (
          <section style={S.drawer} aria-label="歷史記錄">
            <div style={S.drawerHead}>
              <span style={S.historyTitle}>
                <Icon name="history" size={15} style={{ color: 'var(--muted)' }} />
                歷史記錄
                <span style={S.historyCount}>{history.length}/{_MAX_HISTORY}</span>
              </span>
              {history.length > 0 && (
                <div style={S.seg}>
                  {HISTORY_FILTERS.map((f, i) => (
                    <button
                      key={f.key}
                      onClick={() => setHistoryFilter(f.key)}
                      style={{ ...S.segBtn, ...(i === 0 ? { borderLeft: 'none' } : {}), ...(historyFilter === f.key ? S.segBtnActive : {}) }}
                    >{f.label}</button>
                  ))}
                </div>
              )}
              <div style={{ flex: 1 }} />
              {history.length > 0 && (
                <button className="cf-link" style={S.clearBtn} onClick={clearHistory}>清除全部</button>
              )}
              <button className="cf-link" style={S.iconBtn} onClick={toggleHistoryVisible} title="收起（Esc）" aria-label="收起歷史記錄">
                <Icon name="chevron-down" size={16} />
              </button>
            </div>

            {filteredHistory.length === 0
              ? <div style={S.historyEmpty}>{history.length === 0 ? '尚無記錄，生成後圖片會保留在此' : '此類型無記錄'}</div>
              : (
              <div style={S.historyScroll}>
                {filteredHistory.map((item) => (
                  <div key={item.id} style={S.historyItemWrap} className="cf-hover-parent">
                    <div style={S.historyThumbBox}>
                      <button
                        className="cf-reveal"
                        style={S.historyDeleteBtn}
                        onClick={() => deleteHistory(item.id)}
                        title="刪除"
                        aria-label="刪除此筆記錄"
                      ><Icon name="x" size={13} /></button>
                      <span style={{ ...S.badge, ..._badgeStyle(item.type, S) }}>
                        {_badgeLabel(item.type)}
                      </span>
                      <img
                        src={item.thumbnail ?? item.url}
                        style={S.historyThumb}
                        className="cf-card-img"
                        alt={item.label || ''}
                        onClick={() => setLightboxItem(item)}
                      />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ ...S.historyMeta, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--muted)' }}>{formatTime(item.ts)}</div>
                      {item.label && (
                        <div style={S.historyMeta} title={item.label}>{item.label}</div>
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
            )}
          </section>
        )}
      </div>

      <footer style={S.statusbar}>
        <ServiceStatus status={svcStatus} />
        <span style={S.sbSep} />
        <span style={S.sbItem} title={`${ctxKind}：${ctxName}`}>
          <Icon name="cpu" size={12} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis' }}>{ctxName}</span>
        </span>
        <span style={{ ...S.sbItem, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--faint)' }}>localhost:8188</span>
        {capability.gpu_tier && (
          <span style={{ ...S.sbItem, fontFamily: 'var(--font-mono)', fontSize: 11 }} title={`GPU 分級來源：${capability.gpu_tier_source}`}>
            GPU {capability.gpu_tier} · Hires {capability.hires_enabled ? '開' : '關'}
          </span>
        )}
        <span style={{ flex: 1 }} />
        <button style={{ ...S.sbBtn, ...(historyVisible ? { background: 'var(--accent-soft)', color: 'var(--accent)' } : {}) }} onClick={toggleHistoryVisible} title="歷史記錄">
          <Icon name="history" size={13} />
          歷史記錄
          {history.length > 0 && <span key={history[0]?.id} style={{ ...S.sbCount, animation: 'cf-pop .3s var(--ease)' }}>{history.length}</span>}
        </button>
        <button
          style={S.sbBtn}
          onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
          title={theme === 'light' ? '切換為深色模式' : '切換為淺色模式'}
          aria-label="切換淺色 / 深色主題"
        >
          <Icon name={theme === 'light' ? 'moon' : 'sun-medium'} size={13} />
        </button>
      </footer>

      {/* Settings modal */}
      {settingsOpen && (
        <div style={S.modalOverlay} onClick={e => e.target === e.currentTarget && setSettingsOpen(false)}>
          <div style={{ ...S.modalBox, maxWidth: 580 }} role="dialog" aria-modal="true" aria-label="設定">
            <div style={S.modalHeader}>
              <span style={S.modalTitle}><Icon name="settings" size={16} style={{ color: 'var(--muted)' }} />設定</span>
              <button className="cf-link" style={S.iconBtn} onClick={() => setSettingsOpen(false)} aria-label="關閉"><Icon name="x" size={16} /></button>
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
                visionOnlyModels={visionOnlyModels}
                modelCaps={modelCaps}
                activeVisionModel={activeVisionModel}
                onVisionModelChange={onVisionModelChange}
                activeTextModel={activeTextModel}
                onTextModelChange={onTextModelChange}
              />
            </div>
          </div>
        </div>
      )}

      {/* LoRA training modal（與設定同層） */}
      {trainingOpen && (
        <div style={S.modalOverlay} onClick={e => e.target === e.currentTarget && setTrainingOpen(false)}>
          <div style={{ ...S.modalBox, maxWidth: 660 }} role="dialog" aria-modal="true" aria-label="LoRA 訓練">
            <div style={S.modalHeader}>
              <span style={S.modalTitle}><Icon name="flask-conical" size={16} style={{ color: 'var(--muted)' }} />LoRA 訓練</span>
              <button className="cf-link" style={S.iconBtn} onClick={() => setTrainingOpen(false)} aria-label="關閉"><Icon name="x" size={16} /></button>
            </div>
            <div style={S.modalBody}>
              <TrainingTab />
            </div>
          </div>
        </div>
      )}

      {/* Lightbox */}
      {lightboxItem && (
        <div style={S.lightboxOverlay} onClick={() => setLightboxItem(null)}>
          <button style={S.lightboxClose} onClick={() => setLightboxItem(null)} aria-label="關閉（Esc）"><Icon name="x" size={18} /></button>
          <div style={S.lightboxBox} onClick={e => e.stopPropagation()}>
            {/* 優先原圖（本次工作階段的 blob）；重整後 url 已被換成縮圖 */}
            <img
              src={lightboxItem.url ?? lightboxItem.thumbnail}
              style={S.lightboxImg}
              alt={lightboxItem.label || ''}
            />
            <div style={S.lightboxFooter}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{ ...S.badge, position: 'static', ..._badgeStyle(lightboxItem.type, S) }}>
                    {_badgeLabel(lightboxItem.type)}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{formatTime(lightboxItem.ts)}</span>
                  {lightboxItem.model && (
                    <span style={{ fontSize: 12, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }} title={lightboxItem.model}>
                      {_shortModel(lightboxItem.model)}
                    </span>
                  )}
                </div>
                {lightboxItem.label && (
                  <div style={{ fontSize: 13, color: 'var(--text)', maxWidth: '60vw' }}>
                    {lightboxItem.label}
                  </div>
                )}
                {lightboxItem.params && (lightboxItem.params.ipa != null || lightboxItem.params.cn != null || lightboxItem.params.cnMode) && (
                  <div style={{ fontSize: 12, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
                    {lightboxItem.params.ipa != null ? `IPA ${Number(lightboxItem.params.ipa).toFixed(2)}` : 'IPA off'}
                    {' · '}
                    {lightboxItem.params.cn != null ? `CN ${Number(lightboxItem.params.cn).toFixed(2)}` : 'CN off'}
                    {lightboxItem.params.cnMode ? ` (${lightboxItem.params.cnMode})` : ''}
                  </div>
                )}
                <div style={{ maxWidth: '60vw' }}>
                  <GenerationInfo historyId={lightboxItem.historyId} />
                </div>
              </div>
              <a
                href={lightboxItem.url}
                download={lightboxItem.filename}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--accent-contrast)', background: 'var(--accent)', padding: '7px 12px', borderRadius: 'var(--r)', textDecoration: 'none', fontWeight: 600, flexShrink: 0 }}
              >
                <Icon name="download" size={14} />下載
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
