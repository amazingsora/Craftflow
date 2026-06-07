import { useState, useEffect, useRef } from 'react'
import { apiDelete, apiUrl, request } from '../api/client'

const GENRES = ['玄幻', '奇幻', '現代都市', '科幻', '古風', 'BL/GL', '輕小說', '其他']
const STATUSES = ['構思中', '撰寫中', '修稿中', '完稿']

const STATUS_COLOR = {
  '構思中': { bg: '#1e2a3a', text: '#7eb8f7' },
  '撰寫中': { bg: '#1e3a2d', text: '#7ef7b0' },
  '修稿中': { bg: '#3a2d1e', text: '#f7c87e' },
  '完稿':   { bg: '#2d1e3a', text: '#c07ef7' },
}

// ── Styles ────────────────────────────────────────────────────────────────────

const S = {
  root: { display: 'flex', flexDirection: 'column', gap: 16 },
  toolbar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 },
  toolbarTitle: { fontSize: 16, fontWeight: 700, color: 'var(--text)' },
  breadcrumb: { fontSize: 13, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6 },
  breadSep: { color: 'var(--border)' },
  breadLink: { color: 'var(--accent)', cursor: 'pointer', textDecoration: 'none' },

  addBtn: {
    padding: '8px 18px', borderRadius: 8, border: 'none',
    background: 'var(--accent)', color: '#fff', fontSize: 14,
    fontWeight: 600, cursor: 'pointer',
  },
  backBtn: {
    padding: '6px 14px', borderRadius: 8,
    border: '1px solid var(--border)', background: 'transparent',
    color: 'var(--muted)', fontSize: 13, cursor: 'pointer',
  },
  btnRow: { display: 'flex', gap: 8, flexWrap: 'wrap' },

  // Project grid
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 14 },
  card: {
    background: '#12121e', border: '1px solid var(--border)',
    borderRadius: 12, padding: 18, cursor: 'pointer',
    transition: 'border-color .15s', display: 'flex', flexDirection: 'column', gap: 8,
  },
  cardTitle: { fontSize: 15, fontWeight: 700, color: 'var(--text)' },
  cardMeta: { fontSize: 12, color: 'var(--muted)', lineHeight: 1.6 },
  badge: {
    display: 'inline-block', fontSize: 11, borderRadius: 4,
    padding: '2px 7px', fontWeight: 600, alignSelf: 'flex-start',
  },
  genreBadge: {
    display: 'inline-block', fontSize: 11, borderRadius: 4,
    padding: '2px 7px', background: '#1a1a2e',
    border: '1px solid var(--border)', color: 'var(--muted)',
  },
  charCount: { fontSize: 12, color: 'var(--muted)', marginTop: 'auto' },

  // Character + Faction mixed grid
  charGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12 },
  charCard: {
    background: '#12121e', border: '1px solid var(--border)',
    borderRadius: 10, padding: 14, cursor: 'pointer',
    transition: 'border-color .15s', display: 'flex', flexDirection: 'column', gap: 8,
  },
  portrait: {
    width: '100%', aspectRatio: '1/1', borderRadius: 8,
    background: 'var(--border)', overflow: 'hidden',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'var(--muted)', fontSize: 12,
  },
  charName: { fontSize: 14, fontWeight: 700, color: 'var(--text)' },
  charTraits: { fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 },

  // Faction tile (same size as char card, distinct style)
  factionTile: {
    background: '#0e0e1c', border: '2px dashed var(--border)',
    borderRadius: 10, padding: 14, cursor: 'pointer',
    transition: 'border-color .15s', display: 'flex', flexDirection: 'column', gap: 8,
  },
  factionThumb: {
    width: '100%', aspectRatio: '1/1', borderRadius: 8,
    background: '#1a1a2e', overflow: 'hidden',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 30, color: 'var(--muted)',
  },
  factionName: { fontSize: 14, fontWeight: 700, color: 'var(--accent)' },
  factionMeta: { fontSize: 11, color: 'var(--muted)' },

  // Color picker
  colorRow: { display: 'flex', alignItems: 'center', gap: 10 },
  colorPicker: {
    width: 38, height: 34, padding: 2, borderRadius: 6,
    border: '1px solid var(--border)', cursor: 'pointer', background: 'none',
  },
  colorCode: { fontFamily: 'monospace', fontSize: 13, color: 'var(--muted)' },
  colorDot: { width: 10, height: 10, borderRadius: '50%', flexShrink: 0 },

  // Faction chips (in char detail)
  factionChip: {
    display: 'inline-flex', alignItems: 'center', gap: 5,
    fontSize: 12, borderRadius: 20, padding: '3px 10px',
    background: '#1a1a2e', border: '1px solid var(--accent)',
    color: 'var(--accent)', cursor: 'default',
  },
  chipX: {
    cursor: 'pointer', color: 'var(--muted)', fontSize: 13,
    lineHeight: 1, padding: '0 2px',
  },

  // Delete confirm box
  deleteBox: {
    background: '#1e0d0d', border: '1px solid #5c2020',
    borderRadius: 10, padding: 16, display: 'flex', flexDirection: 'column', gap: 10,
  },
  deletePrompt: { fontSize: 13, color: '#f07070', margin: 0 },

  // Forms
  form: { display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 560 },
  label: { fontSize: 12, color: 'var(--muted)', marginBottom: 3, display: 'block' },
  input: {
    width: '100%', background: '#12121e', border: '1px solid var(--border)',
    borderRadius: 8, color: 'var(--text)', padding: '9px 12px',
    fontSize: 14, outline: 'none', boxSizing: 'border-box',
  },
  select: {
    width: '100%', background: '#12121e', border: '1px solid var(--border)',
    borderRadius: 8, color: 'var(--text)', padding: '9px 12px',
    fontSize: 14, outline: 'none', boxSizing: 'border-box',
  },
  textarea: {
    width: '100%', background: '#12121e', border: '1px solid var(--border)',
    borderRadius: 8, color: 'var(--text)', padding: '9px 12px',
    fontSize: 14, resize: 'vertical', fontFamily: 'inherit',
    outline: 'none', minHeight: 80, boxSizing: 'border-box',
  },
  btn: {
    padding: '10px 0', borderRadius: 8, border: 'none',
    background: 'var(--accent)', color: '#fff',
    fontSize: 15, fontWeight: 600, cursor: 'pointer',
  },
  btnSm: {
    padding: '6px 14px', borderRadius: 8,
    border: '1px solid var(--border)', background: 'transparent',
    color: 'var(--text)', fontSize: 13, cursor: 'pointer',
  },
  btnDanger: {
    padding: '6px 14px', borderRadius: 8,
    border: '1px solid #5c2020', background: 'transparent',
    color: '#f07070', fontSize: 13, cursor: 'pointer',
  },
  error: { color: 'var(--danger)', fontSize: 13 },
  muted: { color: 'var(--muted)', fontSize: 13 },

  // Variant tab bar
  varTabBar: { display: 'flex', gap: 4, margin: '4px 0 0', borderBottom: '1px solid var(--border)', paddingBottom: 0 },
  varTab: {
    padding: '7px 16px', border: 'none', background: 'transparent',
    color: 'var(--muted)', fontSize: 13, cursor: 'pointer',
    borderBottom: '2px solid transparent', marginBottom: -1, borderRadius: '6px 6px 0 0',
    display: 'flex', alignItems: 'center', gap: 5, transition: 'color .12s',
  },
  varTabActive: { color: 'var(--text)', borderBottom: '2px solid var(--accent)', fontWeight: 600, background: 'rgba(124,106,247,0.07)' },
  tabEditBtn: {
    width: 16, height: 16, border: 'none', background: 'transparent',
    color: 'var(--muted)', cursor: 'pointer', padding: 0, fontSize: 12, lineHeight: 1,
    display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 3,
    flexShrink: 0,
  },

  // Detail layout
  detail: { display: 'flex', gap: 20, alignItems: 'flex-start' },
  detailLeft: { flex: '0 0 290px', display: 'flex', flexDirection: 'column', gap: 14 },
  detailRight: { flex: 1, display: 'flex', flexDirection: 'column', gap: 14 },
  summaryCard: {
    background: '#0d0d18', border: '1px solid var(--border)',
    borderRadius: 10, padding: '14px 16px',
    fontSize: 13, lineHeight: 1.9, whiteSpace: 'pre-wrap',
    color: 'var(--text)', minHeight: 120,
  },
  summaryPlaceholder: {
    background: '#0d0d18', border: '2px dashed var(--border)',
    borderRadius: 10, padding: '20px 16px',
    color: 'var(--muted)', fontSize: 13, textAlign: 'center',
  },
  dropzone: {
    border: '2px dashed var(--border)', borderRadius: 10,
    minHeight: 180, display: 'flex', alignItems: 'center',
    justifyContent: 'center', cursor: 'pointer',
    overflow: 'hidden', transition: 'border-color .2s', textAlign: 'center',
  },
  dropzoneActive: { borderColor: 'var(--accent)' },
  portraitImg: { width: '100%', objectFit: 'cover', maxHeight: 220, display: 'block' },
  genImg: { width: '100%', borderRadius: 10, display: 'block', marginTop: 8 },
  spinner: {
    display: 'inline-block', width: 16, height: 16,
    border: '2px solid var(--border)', borderTop: '2px solid var(--accent)',
    borderRadius: '50%', animation: 'spin 0.9s linear infinite',
    verticalAlign: 'middle', marginRight: 5,
  },
  sectionLabel: { fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 6 },
  divider: { borderColor: 'var(--border)', margin: '4px 0' },
  row: { display: 'flex', gap: 12 },
  fieldGroup: { flex: 1, display: 'flex', flexDirection: 'column', gap: 4 },
}

// ── helpers ───────────────────────────────────────────────────────────────────

async function apiFetch(path, opts = {}) {
  return request(path, opts).then((r) => r.json())
}

function Spinner() { return <span style={S.spinner} /> }

// ── ImageLightbox ─────────────────────────────────────────────────────────────

function ImageLightbox({ src, onClose }) {
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
          color: '#fff', fontSize: 20, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          lineHeight: 1,
        }}
      >×</button>
    </div>
  )
}

function StatusBadge({ status }) {
  const c = STATUS_COLOR[status] ?? { bg: '#1a1a2e', text: 'var(--muted)' }
  return <span style={{ ...S.badge, background: c.bg, color: c.text }}>{status ?? '—'}</span>
}

// ── GenderPicker ──────────────────────────────────────────────────────────────

const GENDER_OPTIONS = [
  { value: 'male',    icon: '♂', label: '男',   active: '#3a8fd8', bg: '#1a2a40' },
  { value: 'female',  icon: '♀', label: '女',   active: '#d83a8f', bg: '#3a1a2a' },
  { value: 'neutral', icon: '⚧', label: '中性', active: '#9a5cd8', bg: '#2a1a40' },
]

function GenderPicker({ value, onChange }) {
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

function DeleteConfirm({ label, name, onConfirm, onCancel, loading = false }) {
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

// ── ProjectsView ──────────────────────────────────────────────────────────────

function ProjectsView({ onSelect, onCreateClick, onEdit }) {
  const [projects, setProjects] = useState([])
  const [charCounts, setCharCounts] = useState({})
  const [loading, setLoading] = useState(true)
  const [deletingProject, setDeletingProject] = useState(null)
  const [deletingLoading, setDeletingLoading] = useState(false)

  useEffect(() => {
    apiFetch('/projects/')
      .then(async (list) => {
        setProjects(list)
        const counts = await Promise.all(
          list.map(p =>
            apiFetch(`/projects/${p.id}/characters`)
              .then(chars => [p.id, chars.length])
              .catch(() => [p.id, 0])
          )
        )
        setCharCounts(Object.fromEntries(counts))
      })
      .finally(() => setLoading(false))
  }, [])

  const confirmDelete = async () => {
    if (!deletingProject) return
    setDeletingLoading(true)
    try {
      await apiDelete(`/projects/${deletingProject.id}`)
      setProjects(prev => prev.filter(p => p.id !== deletingProject.id))
      setDeletingProject(null)
    } catch (e) { /* silent */ }
    finally { setDeletingLoading(false) }
  }

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <span style={S.toolbarTitle}>作品管理</span>
        <button style={S.addBtn} onClick={onCreateClick}>+ 新增作品</button>
      </div>

      {deletingProject && (
        <DeleteConfirm
          label={`永久刪除作品「${deletingProject.title}」及所有角色、勢力`}
          name={deletingProject.title}
          loading={deletingLoading}
          onConfirm={confirmDelete}
          onCancel={() => setDeletingProject(null)}
        />
      )}

      {loading && <p style={S.muted}>載入中...</p>}
      {!loading && projects.length === 0 && (
        <p style={S.muted}>尚無作品。點擊「+ 新增作品」開始建立。</p>
      )}
      {!loading && projects.length > 0 && (
        <div style={S.grid}>
          {projects.map(p => (
            <div
              key={p.id} style={S.card}
              onClick={() => { if (!deletingProject) onSelect(p) }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <div style={S.cardTitle}>{p.title}</div>
                <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                  <button
                    style={{ ...S.btnSm, fontSize: 11, padding: '3px 10px' }}
                    onClick={e => { e.stopPropagation(); onEdit(p) }}
                  >編輯</button>
                  <button
                    style={{ ...S.btnDanger, fontSize: 11, padding: '3px 10px' }}
                    onClick={e => { e.stopPropagation(); setDeletingProject(p) }}
                  >刪除</button>
                </div>
              </div>
              <div style={S.btnRow}>
                <StatusBadge status={p.status} />
                {p.genre && <span style={S.genreBadge}>{p.genre}</span>}
              </div>
              {p.synopsis && (
                <div style={S.cardMeta}>{p.synopsis.slice(0, 80)}{p.synopsis.length > 80 ? '...' : ''}</div>
              )}
              <div style={S.charCount}>作者：{p.author} · {charCounts[p.id] ?? '…'} 個角色</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── ProjectCreateView ─────────────────────────────────────────────────────────

function ProjectCreateView({ onBack, onCreate }) {
  const [title, setTitle] = useState('')
  const [author, setAuthor] = useState('')
  const [synopsis, setSynopsis] = useState('')
  const [genre, setGenre] = useState('')
  const [status, setStatus] = useState('構思中')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const submit = async () => {
    if (!title.trim()) { setError('請輸入作品名稱'); return }
    if (!author.trim()) { setError('請輸入作者名稱'); return }
    setLoading(true); setError(null)
    try {
      const project = await apiFetch('/projects/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim(), author: author.trim(), synopsis: synopsis.trim() || null, genre: genre || null, status }),
      })
      onCreate(project)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <button style={S.backBtn} onClick={onBack}>← 返回作品列表</button>
        <span style={S.toolbarTitle}>新增作品</span>
      </div>
      <div style={S.form}>
        <div style={S.row}>
          <div style={{ ...S.fieldGroup, flex: 2 }}>
            <label style={S.label}>作品名稱 *</label>
            <input style={S.input} value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：月影錄" />
          </div>
          <div style={S.fieldGroup}>
            <label style={S.label}>作者</label>
            <input style={S.input} value={author} onChange={e => setAuthor(e.target.value)} placeholder="筆名" />
          </div>
        </div>
        <div style={S.row}>
          <div style={S.fieldGroup}>
            <label style={S.label}>作品類型</label>
            <select style={S.select} value={genre} onChange={e => setGenre(e.target.value)}>
              <option value="">— 不指定 —</option>
              {GENRES.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
          <div style={S.fieldGroup}>
            <label style={S.label}>創作狀態</label>
            <select style={S.select} value={status} onChange={e => setStatus(e.target.value)}>
              {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label style={S.label}>作品描述</label>
          <textarea style={{ ...S.textarea, minHeight: 120 }} value={synopsis} onChange={e => setSynopsis(e.target.value)} placeholder="作品世界觀、主線故事、核心主題..." />
        </div>
        {error && <p style={S.error}>{error}</p>}
        <button style={S.btn} disabled={loading} onClick={submit}>
          {loading ? <><Spinner />建立中...</> : '建立作品'}
        </button>
      </div>
    </div>
  )
}

// ── CharacterListView ─────────────────────────────────────────────────────────

function CharacterListView({ project: initProject, onSelectChar, onCreateChar, onBackToProjects, autoEdit = false, onSelectFaction }) {
  const [project, setProject] = useState(initProject)
  const [characters, setCharacters] = useState([])
  const [factions, setFactions] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(autoEdit)
  const [eTitle, setETitle] = useState(initProject.title)
  const [eAuthor, setEAuthor] = useState(initProject.author)
  const [eSynopsis, setESynopsis] = useState(initProject.synopsis ?? '')
  const [eGenre, setEGenre] = useState(initProject.genre ?? '')
  const [eStatus, setEStatus] = useState(initProject.status ?? '構思中')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [showCreateFaction, setShowCreateFaction] = useState(false)
  const [newFactionName, setNewFactionName] = useState('')
  const [creatingFaction, setCreatingFaction] = useState(false)
  const [deletingFaction, setDeletingFaction] = useState(null)
  const [deletingFactionLoading, setDeletingFactionLoading] = useState(false)

  useEffect(() => {
    Promise.all([
      apiFetch(`/projects/${project.id}/characters`),
      apiFetch(`/projects/${project.id}/factions`),
    ]).then(([chars, facts]) => {
      setCharacters(chars)
      setFactions(facts)
    }).finally(() => setLoading(false))
  }, [project.id])

  const saveProject = async () => {
    if (!eTitle.trim()) { setSaveError('作品名稱不能為空'); return }
    setSaving(true); setSaveError(null)
    try {
      const updated = await apiFetch(`/projects/${project.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: eTitle.trim(), author: eAuthor.trim(), synopsis: eSynopsis || null, genre: eGenre || null, status: eStatus }),
      })
      setProject(updated); setEditing(false)
    } catch (e) { setSaveError(e.message) }
    finally { setSaving(false) }
  }

  const createFaction = async () => {
    if (!newFactionName.trim()) return
    setCreatingFaction(true)
    try {
      const faction = await apiFetch(`/projects/${project.id}/factions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newFactionName.trim() }),
      })
      setFactions(prev => [...prev, faction])
      setNewFactionName(''); setShowCreateFaction(false)
    } catch (e) { /* silent */ }
    finally { setCreatingFaction(false) }
  }

  const confirmDeleteFaction = async () => {
    if (!deletingFaction) return
    setDeletingFactionLoading(true)
    try {
      await apiDelete(`/factions/${deletingFaction.id}`)
      setFactions(prev => prev.filter(f => f.id !== deletingFaction.id))
      setDeletingFaction(null)
    } catch (e) { /* silent */ }
    finally { setDeletingFactionLoading(false) }
  }

  // Characters with no faction membership
  const allFactionCharIds = new Set(factions.flatMap(f => f.characters.map(c => c.id)))
  const ungrouped = characters.filter(c => !allFactionCharIds.has(c.id))

  const CharCard = ({ c }) => (
    <div
      style={S.charCard}
      onClick={() => onSelectChar(c)}
      onMouseEnter={e => e.currentTarget.style.borderColor = c.color || 'var(--accent)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
    >
      <div style={S.portrait}>
        {(c.concept_images?.[0])
          ? <img src={apiUrl(`/characters/${c.id}/concept-images/0`)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
          : c.portrait_path
            ? <img src={apiUrl(`/characters/${c.id}/portrait`)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
            : '無概念圖'
        }
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {c.color && <span style={{ ...S.colorDot, background: c.color }} />}
        <span style={S.charName}>{c.name}</span>
      </div>
      {c.core_traits && (
        <div style={S.charTraits}>{c.core_traits.slice(0, 45)}{c.core_traits.length > 45 ? '...' : ''}</div>
      )}
    </div>
  )

  const FactionCard = ({ f }) => (
    <div
      style={S.factionTile}
      onClick={() => onSelectFaction(f)}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
    >
      <div style={S.factionThumb}>
        {f.thumbnail_path
          ? <img src={apiUrl(`/factions/${f.id}/thumbnail`)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
          : '⚑'
        }
      </div>
      <div style={S.factionName}>{f.name}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={S.factionMeta}>{f.characters.length} 名成員</span>
        <button
          style={{ ...S.btnDanger, fontSize: 11, padding: '2px 8px' }}
          onClick={e => { e.stopPropagation(); setDeletingFaction(f) }}
        >刪除</button>
      </div>
    </div>
  )

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <div style={S.breadcrumb}>
          <span style={S.breadLink} onClick={onBackToProjects}>作品管理</span>
          <span style={S.breadSep}>›</span>
          <span style={{ color: 'var(--text)', fontWeight: 600 }}>{project.title}</span>
          {project.genre && <span style={S.genreBadge}>{project.genre}</span>}
          <StatusBadge status={project.status} />
        </div>
        <div style={S.btnRow}>
          <button style={S.btnSm} onClick={() => { setSaveError(null); setEditing(e => !e) }}>{editing ? '取消' : '編輯作品'}</button>
          <button style={S.btnSm} onClick={() => setShowCreateFaction(s => !s)}>+ 新增勢力</button>
          <button style={S.addBtn} onClick={onCreateChar}>+ 新增角色</button>
        </div>
      </div>

      {editing && (
        <div style={{ ...S.form, maxWidth: 480, background: '#12121e', border: '1px solid var(--border)', borderRadius: 10, padding: 16 }}>
          <div style={S.row}>
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>作品名稱</label>
              <input style={S.input} value={eTitle} onChange={e => setETitle(e.target.value)} />
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}>作者</label>
              <input style={S.input} value={eAuthor} onChange={e => setEAuthor(e.target.value)} />
            </div>
          </div>
          <div style={S.row}>
            <div style={S.fieldGroup}>
              <label style={S.label}>類型</label>
              <select style={S.select} value={eGenre} onChange={e => setEGenre(e.target.value)}>
                <option value="">— 不指定 —</option>
                {GENRES.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}>狀態</label>
              <select style={S.select} value={eStatus} onChange={e => setEStatus(e.target.value)}>
                {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label style={S.label}>作品描述</label>
            <textarea style={{ ...S.textarea, minHeight: 80 }} value={eSynopsis} onChange={e => setESynopsis(e.target.value)} />
          </div>
          {saveError && <p style={S.error}>{saveError}</p>}
          <button style={S.btn} disabled={saving} onClick={saveProject}>
            {saving ? <><Spinner />儲存中...</> : '儲存作品資料'}
          </button>
        </div>
      )}

      {showCreateFaction && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', maxWidth: 400 }}>
          <input
            style={S.input} value={newFactionName} autoFocus
            onChange={e => setNewFactionName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') createFaction(); if (e.key === 'Escape') setShowCreateFaction(false) }}
            placeholder="勢力名稱，例如：帝國軍"
          />
          <button style={S.addBtn} disabled={creatingFaction || !newFactionName.trim()} onClick={createFaction}>
            {creatingFaction ? <Spinner /> : '建立'}
          </button>
          <button style={S.btnSm} onClick={() => setShowCreateFaction(false)}>取消</button>
        </div>
      )}

      {deletingFaction && (
        <DeleteConfirm
          label={`刪除勢力「${deletingFaction.name}」`}
          name={deletingFaction.name}
          loading={deletingFactionLoading}
          onConfirm={confirmDeleteFaction}
          onCancel={() => setDeletingFaction(null)}
        />
      )}

      {!editing && project.synopsis && (
        <p style={{ ...S.muted, lineHeight: 1.7, maxWidth: 640 }}>{project.synopsis}</p>
      )}

      {loading && <p style={S.muted}>載入中...</p>}
      {!loading && (
        <div style={S.charGrid}>
          {factions.map(f => <FactionCard key={`faction-${f.id}`} f={f} />)}
          {ungrouped.map(c => <CharCard key={`char-${c.id}`} c={c} />)}
          {factions.length === 0 && ungrouped.length === 0 && (
            <p style={S.muted}>尚無角色或勢力。點擊右上角按鈕開始建立。</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── FactionView ───────────────────────────────────────────────────────────────

function FactionView({ faction: initFaction, project, allChars, onBack, onSelectChar }) {
  const [faction, setFaction] = useState(initFaction)
  const [members, setMembers] = useState(initFaction.characters || [])
  const [editing, setEditing] = useState(false)
  const [eName, setEName] = useState(initFaction.name)
  const [saving, setSaving] = useState(false)
  const [addingMember, setAddingMember] = useState(false)
  const [uploadingThumb, setUploadingThumb] = useState(false)
  const [error, setError] = useState(null)
  const thumbRef = useRef()

  const nonMembers = allChars.filter(c => !members.some(m => m.id === c.id))

  const saveName = async () => {
    if (!eName.trim()) return
    setSaving(true)
    try {
      const updated = await apiFetch(`/factions/${faction.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: eName.trim() }),
      })
      setFaction(updated); setEditing(false)
    } catch (e) { setError(e.message) }
    finally { setSaving(false) }
  }

  const addMember = async (charId) => {
    try {
      await request(`/factions/${faction.id}/members/${charId}`, { method: 'POST' })
      const char = allChars.find(c => c.id === charId)
      if (char) setMembers(prev => [...prev, char])
      setAddingMember(false)
    } catch (e) { setError(e.message) }
  }

  const removeMember = async (charId) => {
    try {
      await apiDelete(`/factions/${faction.id}/members/${charId}`)
      setMembers(prev => prev.filter(c => c.id !== charId))
    } catch (e) { setError(e.message) }
  }

  const uploadThumb = async (file) => {
    if (!file || !file.type.startsWith('image/')) return
    setUploadingThumb(true)
    const body = new FormData()
    body.append('file', file)
    try {
      const updated = await apiFetch(`/factions/${faction.id}/thumbnail`, { method: 'POST', body })
      setFaction(updated)
    } catch (e) { setError(e.message) }
    finally { setUploadingThumb(false) }
  }

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <div style={S.breadcrumb}>
          <span style={S.breadLink} onClick={onBack}>← {project.title}</span>
          <span style={S.breadSep}>›</span>
          <span style={{ color: 'var(--accent)', fontWeight: 600 }}>⚑ {faction.name}</span>
        </div>
        <div style={S.btnRow}>
          <button style={S.btnSm} onClick={() => setEditing(e => !e)}>{editing ? '取消' : '重新命名'}</button>
          <button style={S.addBtn} onClick={() => setAddingMember(s => !s)}>+ 加入角色</button>
        </div>
      </div>

      {error && <p style={S.error}>{error}</p>}

      {editing && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', maxWidth: 360 }}>
          <input style={S.input} value={eName} autoFocus onChange={e => setEName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') saveName() }} />
          <button style={S.addBtn} disabled={saving} onClick={saveName}>
            {saving ? <Spinner /> : '儲存'}
          </button>
        </div>
      )}

      {addingMember && (
        <div style={{ background: '#12121e', border: '1px solid var(--border)', borderRadius: 10, padding: 14 }}>
          <p style={S.sectionLabel}>選擇角色加入 {faction.name}</p>
          {nonMembers.length === 0
            ? <p style={S.muted}>所有角色都已在此勢力中。</p>
            : <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                {nonMembers.map(c => (
                  <button key={c.id} style={S.btnSm} onClick={() => addMember(c.id)}>
                    {c.color && <span style={{ ...S.colorDot, background: c.color, marginRight: 5 }} />}
                    {c.name}
                  </button>
                ))}
              </div>
          }
          <button style={{ ...S.btnSm, marginTop: 10 }} onClick={() => setAddingMember(false)}>關閉</button>
        </div>
      )}

      <div style={S.detail}>
        {/* 左：勢力縮圖 */}
        <div style={{ flex: '0 0 200px' }}>
          <p style={S.sectionLabel}>勢力縮圖</p>
          <div
            style={{ ...S.dropzone, minHeight: 160, cursor: 'pointer' }}
            onClick={() => thumbRef.current.click()}
          >
            {uploadingThumb
              ? <p style={S.muted}><Spinner />上傳中...</p>
              : faction.thumbnail_path
                ? <img src={apiUrl(`/factions/${faction.id}/thumbnail?t=${faction.thumbnail_path}`)} style={S.portraitImg} alt="縮圖" />
                : <p style={{ ...S.muted, padding: 12 }}>點擊上傳縮圖</p>
            }
          </div>
          <input ref={thumbRef} type="file" accept="image/*" style={{ display: 'none' }}
            onChange={e => uploadThumb(e.target.files[0])} />
        </div>

        {/* 右：成員列表 */}
        <div style={{ flex: 1 }}>
          <p style={S.sectionLabel}>成員（{members.length} 人）</p>
          {members.length === 0
            ? <p style={S.muted}>尚無成員，點擊「+ 加入角色」添加。</p>
            : <div style={S.charGrid}>
                {members.map(c => (
                  <div
                    key={c.id} style={S.charCard}
                    onClick={() => onSelectChar(c)}
                    onMouseEnter={e => e.currentTarget.style.borderColor = c.color || 'var(--accent)'}
                    onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                  >
                    <div style={S.portrait}>
                      {(c.concept_images?.[0])
                        ? <img src={apiUrl(`/characters/${c.id}/concept-images/0`)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
                        : c.portrait_path
                          ? <img src={apiUrl(`/characters/${c.id}/portrait`)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
                          : '無概念圖'
                      }
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {c.color && <span style={{ ...S.colorDot, background: c.color }} />}
                      <span style={S.charName}>{c.name}</span>
                    </div>
                    <button
                      style={{ ...S.btnDanger, fontSize: 11, padding: '3px 8px', marginTop: 'auto' }}
                      onClick={e => { e.stopPropagation(); removeMember(c.id) }}
                    >移出勢力</button>
                  </div>
                ))}
              </div>
          }
        </div>
      </div>
    </div>
  )
}

// ── CharacterCreateView ───────────────────────────────────────────────────────

function CharacterCreateView({ project, onBack, onCreate }) {
  const [name, setName] = useState('')
  const [color, setColor] = useState('')
  const [gender, setGender] = useState(null)
  const [traits, setTraits] = useState('')
  const [behavior, setBehavior] = useState('')
  const [voice, setVoice] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const submit = async () => {
    if (!name.trim()) { setError('請輸入角色名稱'); return }
    setLoading(true); setError(null)
    try {
      const char = await apiFetch(`/projects/${project.id}/characters`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          color: color || null,
          gender: gender || null,
          core_traits: traits.trim() || null,
          behavior_rules: behavior.trim() || null,
          voice_style: voice.trim() || null,
          notes: notes.trim() || null,
        }),
      })
      onCreate(char)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <div style={S.breadcrumb}>
          <span style={S.breadLink} onClick={onBack}>← {project.title}</span>
        </div>
        <span style={S.toolbarTitle}>新增角色</span>
      </div>
      <div style={S.form}>
        <div style={S.row}>
          <div style={{ ...S.fieldGroup, flex: 2 }}>
            <label style={S.label}>角色名稱 *</label>
            <input style={S.input} value={name} onChange={e => setName(e.target.value)} placeholder="例如：白鳶" />
          </div>
          <div style={S.fieldGroup}>
            <label style={S.label}>代表色</label>
            <div style={S.colorRow}>
              <input type="color" style={S.colorPicker} value={color || '#888888'} onChange={e => setColor(e.target.value)} />
              <span style={S.colorCode}>{color || '未設定'}</span>
              {color && <button style={{ ...S.btnSm, fontSize: 11, padding: '4px 10px' }} onClick={() => setColor('')}>清除</button>}
            </div>
          </div>
        </div>
        <div>
          <label style={S.label}>性別</label>
          <GenderPicker value={gender} onChange={setGender} />
        </div>
        <div>
          <label style={S.label}>外貌 / 個性特徵</label>
          <textarea style={S.textarea} value={traits} onChange={e => setTraits(e.target.value)} placeholder="例如：銀色長髮、冷靜但內心敏感..." />
        </div>
        <div>
          <label style={S.label}>行為模式</label>
          <textarea style={S.textarea} value={behavior} onChange={e => setBehavior(e.target.value)} placeholder="例如：遇到危機會先觀察、不輕易信任人..." />
        </div>
        <div>
          <label style={S.label}>說話風格</label>
          <input style={S.input} value={voice} onChange={e => setVoice(e.target.value)} placeholder="例如：言簡意賅、偶爾冷幽默..." />
        </div>
        <div>
          <label style={S.label}>補充筆記</label>
          <textarea style={{ ...S.textarea, minHeight: 100 }} value={notes} onChange={e => setNotes(e.target.value)} placeholder="任何額外設定、背景故事..." />
        </div>
        {error && <p style={S.error}>{error}</p>}
        <button style={S.btn} disabled={loading} onClick={submit}>
          {loading ? <><Spinner />建立中...</> : '建立角色'}
        </button>
      </div>
    </div>
  )
}

// ── CharacterDetailView ───────────────────────────────────────────────────────

const DEFAULT_TAB_NAMES = ['主版本', 'Tab 2', 'Tab 3']

// Persist generate-checkbox prefs in localStorage so they survive page reload.
// Key: "craftflow_genprefs_<charId>" for main char, "craftflow_genprefs_<charId>_v<slot>" for variants.
const _genPrefsKey = (charId, slot) =>
  slot != null ? `craftflow_genprefs_${charId}_v${slot}` : `craftflow_genprefs_${charId}`

const _loadGenPrefs = (charId, slot, defaults) => {
  try {
    const raw = localStorage.getItem(_genPrefsKey(charId, slot))
    if (raw) return { ...defaults, ...JSON.parse(raw) }
  } catch {}
  return defaults
}

const _saveGenPref = (charId, slot, key, value) => {
  try {
    const k = _genPrefsKey(charId, slot)
    const prev = JSON.parse(localStorage.getItem(k) || '{}')
    localStorage.setItem(k, JSON.stringify({ ...prev, [key]: value }))
  } catch {}
}

function _initVariant(v = {}, charId = null, slot = null) {
  const prefs = _loadGenPrefs(charId, slot, {
    aiPromptEnabled: !!(v.ai_prompt),
    outfitEnabled: !!(v.outfit),
    ipaEnabled: true,
    ipaWeight: 0.6,
    cnEnabled: true,
    cnWeight: 0.85,
  })
  return {
    color: v.color ?? '', traits: v.core_traits ?? '',
    behavior: v.behavior_rules ?? '', voice: v.voice_style ?? '',
    notes: v.notes ?? '', aiPrompt: v.ai_prompt ?? '',
    aiPromptEnabled: prefs.aiPromptEnabled,
    outfit: v.outfit ?? '', outfitEnabled: prefs.outfitEnabled,
    ipaEnabled: prefs.ipaEnabled,
    ipaWeight: prefs.ipaWeight,
    cnEnabled: prefs.cnEnabled,
    cnWeight: prefs.cnWeight,
    age: v.age != null ? String(v.age) : '', height: v.height != null ? String(v.height) : '', birthday: v.birthday ?? '',
    gender: v.gender ?? null, aiSummary: v.ai_summary ?? null,
    conceptImages: v.concept_images ?? [], aiImages: v.ai_generated_images ?? [],
    pendingQueue: [], generating: false, savingGen: false, savingFields: false,
    summarizing: false, uploadingConcept: false,
    deletingConceptIdx: null, deletingAiIdx: null,
    lastDebugPrompt: null, lastRawDesc: null, lastFlatDraft: null, lastTimings: null, lastAiPromptCompiled: null, lastIpaUsed: null, showDebugPrompt: false,
  }
}

function CharacterDetailView({ character: initChar, project, allFactions, onBack, onDeleted, onAddHistory, onSendToGenerate }) {
  const [char, setChar] = useState(initChar)
  const [charName, setCharName] = useState(initChar.name)
  const [color, setColor] = useState(initChar.color ?? '')
  const [notes, setNotes] = useState(initChar.notes ?? '')
  const [traits, setTraits] = useState(initChar.core_traits ?? '')
  const [behavior, setBehavior] = useState(initChar.behavior_rules ?? '')
  const [voice, setVoice] = useState(initChar.voice_style ?? '')
  const [age, setAge] = useState(initChar.age ?? '')
  const [height, setHeight] = useState(initChar.height ?? '')
  const [birthday, setBirthday] = useState(initChar.birthday ?? '')
  const [gender, setGender] = useState(initChar.gender ?? null)
  const [aiPrompt, setAiPrompt] = useState(initChar.ai_prompt ?? '')
  const [savingFields, setSavingFields] = useState(false)
  const [summarizing, setSummarizing] = useState(false)
  const [uploadingConcept, setUploadingConcept] = useState(false)
  const [conceptImages, setConceptImages] = useState(initChar.concept_images || [])
  const [generating, setGenerating] = useState(false)
  const [pendingQueue, setPendingQueue] = useState([])
  const [savingGen, setSavingGen] = useState(false)
  const [aiImages, setAiImages] = useState(initChar.ai_generated_images || [])
  const [error, setError] = useState(null)
  const [showDelete, setShowDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [charFactionIds, setCharFactionIds] = useState(initChar.faction_ids ?? [])
  const [addingFaction, setAddingFaction] = useState(false)
  const conceptRef = useRef()
  const [deletingConceptIdx, setDeletingConceptIdx] = useState(null)
  const [deletingAiIdx, setDeletingAiIdx] = useState(null)
  const [artStyleId, setArtStyleId] = useState(initChar.art_style_id ?? null)
  const [artStyles, setArtStyles] = useState([])
  // 角色專屬 LoRA（直通欄位）
  const [loraName, setLoraName] = useState(initChar.lora_name ?? '')
  const [loraWeight, setLoraWeight] = useState(initChar.lora_weight ?? 0.8)
  const [loraList, setLoraList] = useState([])
  const [aiPromptEnabled, setAiPromptEnabled] = useState(
    () => _loadGenPrefs(initChar.id, null, { aiPromptEnabled: !!initChar.ai_prompt }).aiPromptEnabled
  )
  const [outfit, setOutfit] = useState(initChar.outfit ?? '')
  const [outfitEnabled, setOutfitEnabled] = useState(
    () => _loadGenPrefs(initChar.id, null, { outfitEnabled: !!initChar.outfit }).outfitEnabled
  )
  const [ipaEnabled, setIpaEnabled] = useState(
    () => _loadGenPrefs(initChar.id, null, { ipaEnabled: true }).ipaEnabled
  )
  const [ipaWeight, setIpaWeight] = useState(
    () => _loadGenPrefs(initChar.id, null, { ipaWeight: 0.6 }).ipaWeight
  )
  // ControlNet 與 IPA 為兩個獨立後端參數，UI 拆開避免「一個開關控制兩者」的誤解
  const [cnEnabled, setCnEnabled] = useState(
    () => _loadGenPrefs(initChar.id, null, { cnEnabled: true }).cnEnabled
  )
  const [cnWeight, setCnWeight] = useState(
    () => _loadGenPrefs(initChar.id, null, { cnWeight: 0.85 }).cnWeight
  )
  const [showDebugPrompt, setShowDebugPrompt] = useState(false)
  const [lastDebugPrompt, setLastDebugPrompt] = useState(null)
  const [lastRawDesc, setLastRawDesc] = useState(null)
  const [lastFlatDraft, setLastFlatDraft] = useState(null)
  const [lastAiPromptCompiled, setLastAiPromptCompiled] = useState(null)
  const [lastIpaUsed, setLastIpaUsed] = useState(null)
  const [lightboxSrc, setLightboxSrc] = useState(null)
  const [lastTimings, setLastTimings] = useState(null)

  // ── Tab state ──────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState(0)
  const [tabNames, setTabNames] = useState(() => {
    const n = initChar.tab_names || []
    return DEFAULT_TAB_NAMES.map((d, i) => n[i] || d)
  })
  const [editingTabIdx, setEditingTabIdx] = useState(null)
  const [editingTabNameVal, setEditingTabNameVal] = useState('')
  const [savingTabName, setSavingTabName] = useState(false)

  // Variant state: 2 slots (Tab 2 = index 0, Tab 3 = index 1)
  const [vs, setVs] = useState(() => {
    const vars = initChar.variants || []
    return [_initVariant(vars[0] || {}, initChar.id, 1), _initVariant(vars[1] || {}, initChar.id, 2)]
  })
  const setV = (slot, upd) =>
    setVs(prev => prev.map((v, i) => i === slot - 1 ? { ...v, ...upd } : v))
  // Current variant state (null when on Tab 1)
  const vState = activeTab > 0 ? vs[activeTab - 1] : null

  const charFactions = allFactions.filter(f => charFactionIds.includes(f.id))
  const availableFactions = allFactions.filter(f => !charFactionIds.includes(f.id))

  useEffect(() => {
    apiFetch('/art-styles').then(setArtStyles).catch(() => {})
    // ComfyUI 離線時 /settings/loras 會 503，靜默忽略即可
    apiFetch('/settings/loras').then(d => setLoraList(d.loras || [])).catch(() => {})
  }, [])

  const saveFields = async () => {
    if (!charName.trim()) { setError('角色名稱不能為空'); return }
    setSavingFields(true)
    try {
      const updated = await apiFetch(`/characters/${char.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: charName.trim(),
          color: color || null,
          core_traits: traits || null,
          behavior_rules: behavior || null,
          voice_style: voice || null,
          notes: notes || null,
          age: age !== '' ? parseInt(age) : null,
          height: height !== '' ? parseInt(height) : null,
          birthday: birthday.trim() || null,
          gender: gender || null,
          ai_prompt: aiPrompt.trim() || null,
          outfit: outfit.trim() || null,
          art_style_id: artStyleId || null,
          lora_name: loraName.trim() || null,
          lora_weight: loraName.trim() ? parseFloat(loraWeight) : null,
        }),
      })
      setChar(updated)
    } catch (e) { setError(e.message) }
    finally { setSavingFields(false) }
  }

  const runSummarize = async () => {
    setSummarizing(true); setError(null)
    try {
      const updated = await apiFetch(`/characters/${char.id}/summarize`, { method: 'POST' })
      setChar(updated)
    } catch (e) { setError(e.message) }
    finally { setSummarizing(false) }
  }

  const uploadConceptImage = async (file) => {
    if (!file || !file.type.startsWith('image/')) return
    setUploadingConcept(true); setError(null)
    const body = new FormData()
    body.append('file', file)
    try {
      const updated = await apiFetch(`/characters/${char.id}/concept-images`, { method: 'POST', body })
      setChar(updated)
      setConceptImages(updated.concept_images || [])
    } catch (e) { setError(e.message) }
    finally { setUploadingConcept(false) }
  }

  const deleteConceptImage = async (idx) => {
    try {
      const updated = await apiFetch(`/characters/${char.id}/concept-images/${idx}`, { method: 'DELETE' })
      setChar(updated)
      setConceptImages(updated.concept_images || [])
      setDeletingConceptIdx(null)
    } catch (e) { setError(e.message) }
  }

  const generateDesignImage = async () => {
    setGenerating(true); setError(null); setPendingQueue([])
    try {
      const params = new URLSearchParams({
        use_ai_prompt: aiPromptEnabled ? '1' : '0',
        use_outfit: outfitEnabled ? '1' : '0',
        use_ipa: ipaEnabled ? '1' : '0',
        ipa_weight: String(ipaWeight),
        use_controlnet: cnEnabled ? '1' : '0',
        cn_weight: String(cnWeight),
      })
      const resp = await request(`/characters/${char.id}/generate-design?${params}`, { method: 'POST' })
      
      // Retrieve debug prompt from header
      let debugPrompt = null
      const b64Prompt = resp.headers.get('X-Prompt')
      if (b64Prompt) {
        try {
          debugPrompt = atob(b64Prompt)
          // Decode UTF-8 if needed (atob handles latin1)
          debugPrompt = decodeURIComponent(escape(debugPrompt))
        } catch (e) { console.warn('Failed to decode debug prompt', e) }
      }

      const b64RawDesc = resp.headers.get('X-Raw-Desc')
      if (b64RawDesc) {
        try { setLastRawDesc(decodeURIComponent(escape(atob(b64RawDesc)))) }
        catch (e) { /* silent */ }
      }
      setLastFlatDraft(resp.headers.get('X-Flat-Draft') === '1')

      if (debugPrompt) setLastDebugPrompt(debugPrompt)

      const b64Timings = resp.headers.get('X-Timings')
      if (b64Timings) {
        try { setLastTimings(JSON.parse(decodeURIComponent(escape(atob(b64Timings))))) }
        catch (e) { /* silent */ }
      }

      const b64AiCompiled = resp.headers.get('X-AI-Prompt-Compiled')
      if (b64AiCompiled) {
        try { setLastAiPromptCompiled(decodeURIComponent(escape(atob(b64AiCompiled)))) }
        catch (e) { /* silent */ }
      }
      setLastIpaUsed(resp.headers.get('X-IPA-Used') === '1')

      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      setPendingQueue([{ blob, url, label: '全身人設圖' }])
      onAddHistory?.({
        type: 'character', url, filename: `${char.name}_design_${Date.now()}.png`, label: `${char.name} 人設圖`,
        model: resp.headers.get('X-Style') || null,
        params: {
          ipa: ipaEnabled ? Number(ipaWeight) : null,
          cn: cnEnabled ? Number(cnWeight) : null,
          cnMode: resp.headers.get('X-CN-Mode') || null,
        },
      })
    } catch (e) { setError(e.message) }
    finally { setGenerating(false) }
  }

  const savePendingFirst = async () => {
    if (pendingQueue.length === 0) return
    setSavingGen(true)
    const item = pendingQueue[0]
    const fd = new FormData()
    fd.append('file', item.blob, `${char.name}_${item.expression ?? 'design'}.png`)
    try {
      const updated = await apiFetch(`/characters/${char.id}/ai-images`, { method: 'POST', body: fd })
      setChar(updated)
      setAiImages(updated.ai_generated_images || [])
      URL.revokeObjectURL(item.url)
      setPendingQueue(prev => prev.slice(1))
    } catch (e) { setError(e.message) }
    finally { setSavingGen(false) }
  }

  const discardPendingFirst = () => {
    if (pendingQueue.length === 0) return
    URL.revokeObjectURL(pendingQueue[0].url)
    setPendingQueue(prev => prev.slice(1))
  }

  const discardAllPending = () => {
    pendingQueue.forEach(item => URL.revokeObjectURL(item.url))
    setPendingQueue([])
  }

  const deleteAiImage = async (idx) => {
    try {
      const updated = await apiFetch(`/characters/${char.id}/ai-images/${idx}`, { method: 'DELETE' })
      setChar(updated)
      setAiImages(updated.ai_generated_images || [])
      setDeletingAiIdx(null)
    } catch (e) { setError(e.message) }
  }

  const joinFaction = async (factionId) => {
    try {
      await request(`/factions/${factionId}/members/${char.id}`, { method: 'POST' })
      setCharFactionIds(prev => [...prev, factionId])
      setAddingFaction(false)
    } catch (e) { setError(e.message) }
  }

  const leaveFaction = async (factionId) => {
    try {
      await apiDelete(`/factions/${factionId}/members/${char.id}`)
      setCharFactionIds(prev => prev.filter(id => id !== factionId))
    } catch (e) { setError(e.message) }
  }

  const deleteChar = async () => {
    setDeleting(true)
    try {
      await apiDelete(`/characters/${char.id}`)
      onDeleted()
    } catch (e) { setError(e.message); setDeleting(false) }
  }

  // ── Tab name handlers ──────────────────────────────────────────────────
  const startEditTabName = (idx) => {
    setEditingTabIdx(idx)
    setEditingTabNameVal(tabNames[idx])
  }
  const confirmTabName = async () => {
    const name = editingTabNameVal.trim() || DEFAULT_TAB_NAMES[editingTabIdx]
    const newNames = tabNames.map((n, i) => i === editingTabIdx ? name : n)
    setSavingTabName(true)
    try {
      await apiFetch(`/characters/${char.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tab_names: newNames }),
      })
      setTabNames(newNames)
    } catch (e) { setError(e.message) }
    finally { setSavingTabName(false); setEditingTabIdx(null) }
  }

  // ── Variant field handlers ─────────────────────────────────────────────
  const saveVariantFields = async () => {
    const slot = activeTab
    setV(slot, { savingFields: true })
    try {
      const v = vs[slot - 1]
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          color: v.color || null,
          core_traits: v.traits || null,
          behavior_rules: v.behavior || null,
          voice_style: v.voice || null,
          notes: v.notes || null,
          age: v.age !== '' ? parseInt(v.age) : null,
          height: v.height !== '' ? parseInt(v.height) : null,
          birthday: v.birthday.trim() || null,
          gender: v.gender || null,
          ai_prompt: v.aiPrompt.trim() || null,
          outfit: v.outfit.trim() || null,
        }),
      })
      // Sync variant data back from server response
      const serverVar = (updated.variants || [])[slot - 1] || {}
      setV(slot, { savingFields: false, conceptImages: serverVar.concept_images ?? v.conceptImages, aiImages: serverVar.ai_generated_images ?? v.aiImages })
    } catch (e) { setError(e.message); setV(slot, { savingFields: false }) }
  }

  const runVariantSummarize = async () => {
    const slot = activeTab
    setV(slot, { summarizing: true })
    try {
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/summarize`, { method: 'POST' })
      const serverVar = (updated.variants || [])[slot - 1] || {}
      setV(slot, { summarizing: false, aiSummary: serverVar.ai_summary ?? null })
    } catch (e) { setError(e.message); setV(slot, { summarizing: false }) }
  }

  const uploadVariantConceptImage = async (slot, file) => {
    console.log('[vConc] uploadVariantConceptImage called', { slot, fileName: file?.name, fileType: file?.type, activeTab })
    if (!file || !file.type.startsWith('image/')) {
      console.warn('[vConc] rejected: not an image or no file', file)
      return
    }
    setV(slot, { uploadingConcept: true })
    const body = new FormData()
    body.append('file', file)
    try {
      console.log('[vConc] POST', `/characters/${char.id}/variants/${slot}/concept-images`)
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/concept-images`, { method: 'POST', body })
      console.log('[vConc] success, variants:', updated?.variants)
      const serverVar = (updated.variants || [])[slot - 1] || {}
      console.log('[vConc] serverVar.concept_images:', serverVar.concept_images, '→ setV slot', slot)
      setV(slot, { uploadingConcept: false, conceptImages: serverVar.concept_images ?? [] })
      console.log('[vConc] setV called, current activeTab:', activeTab)
    } catch (e) {
      console.error('[vConc] error:', e.message)
      setError(e.message)
      setV(slot, { uploadingConcept: false })
    }
  }

  const deleteVariantConceptImage = async (slot, idx) => {
    try {
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/concept-images/${idx}`, { method: 'DELETE' })
      const serverVar = (updated.variants || [])[slot - 1] || {}
      setV(slot, { deletingConceptIdx: null, conceptImages: serverVar.concept_images ?? [] })
    } catch (e) { setError(e.message) }
  }

  const generateVariantDesignImage = async () => {
    const slot = activeTab
    setV(slot, { generating: true, pendingQueue: [] })
    try {
      const vParams = new URLSearchParams({
        use_ai_prompt: vState.aiPromptEnabled ? '1' : '0',
        use_outfit: vState.outfitEnabled ? '1' : '0',
        use_ipa: vState.ipaEnabled ? '1' : '0',
        ipa_weight: String(vState.ipaWeight ?? 0.6),
        use_controlnet: (vState.cnEnabled ?? true) ? '1' : '0',
        cn_weight: String(vState.cnWeight ?? 0.85),
      })
      const resp = await request(`/characters/${char.id}/variants/${slot}/generate-design?${vParams}`, { method: 'POST' })
      let debugPrompt = null
      const b64Prompt = resp.headers.get('X-Prompt')
      if (b64Prompt) { try { debugPrompt = decodeURIComponent(escape(atob(b64Prompt))) } catch (e) { /* silent */ } }
      let rawDesc = null
      const b64RawDesc = resp.headers.get('X-Raw-Desc')
      if (b64RawDesc) { try { rawDesc = decodeURIComponent(escape(atob(b64RawDesc))) } catch (e) { /* silent */ } }
      const flatDraft = resp.headers.get('X-Flat-Draft') === '1'
      let timings = null
      const b64Timings = resp.headers.get('X-Timings')
      if (b64Timings) { try { timings = JSON.parse(decodeURIComponent(escape(atob(b64Timings)))) } catch (e) { /* silent */ } }
      let aiPromptCompiled = null
      const b64AiCompiled = resp.headers.get('X-AI-Prompt-Compiled')
      if (b64AiCompiled) { try { aiPromptCompiled = decodeURIComponent(escape(atob(b64AiCompiled))) } catch (e) { /* silent */ } }
      const ipaUsed = resp.headers.get('X-IPA-Used') === '1'
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      setV(slot, {
        generating: false,
        lastDebugPrompt: debugPrompt,
        lastRawDesc: rawDesc,
        lastFlatDraft: flatDraft,
        lastTimings: timings,
        lastAiPromptCompiled: aiPromptCompiled,
        lastIpaUsed: ipaUsed,
        pendingQueue: [{ blob, url, label: '全身人設圖' }],
      })
      onAddHistory?.({
        type: 'character', url, filename: `${char.name}_v${slot}_design_${Date.now()}.png`, label: `${char.name} 人設圖（Tab ${slot}）`,
        model: resp.headers.get('X-Style') || null,
        params: {
          ipa: vState.ipaEnabled ? Number(vState.ipaWeight ?? 0.6) : null,
          cn: (vState.cnEnabled ?? true) ? Number(vState.cnWeight ?? 0.85) : null,
          cnMode: resp.headers.get('X-CN-Mode') || null,
        },
      })
    } catch (e) { setError(e.message); setV(slot, { generating: false }) }
  }

  const saveVariantPendingFirst = async () => {
    const slot = activeTab
    const v = vs[slot - 1]
    if (!v.pendingQueue.length) return
    const item = v.pendingQueue[0]
    setV(slot, { savingGen: true })
    const fd = new FormData()
    fd.append('file', item.blob, `${char.name}_v${slot}_design.png`)
    try {
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/ai-images`, { method: 'POST', body: fd })
      const serverVar = (updated.variants || [])[slot - 1] || {}
      URL.revokeObjectURL(item.url)
      setVs(prev => prev.map((vs, i) => i === slot - 1 ? {
        ...vs,
        savingGen: false,
        aiImages: serverVar.ai_generated_images ?? [],
        pendingQueue: vs.pendingQueue.slice(1),
      } : vs))
    } catch (e) { setError(e.message); setV(slot, { savingGen: false }) }
  }

  const deleteVariantAiImage = async (slot, idx) => {
    try {
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/ai-images/${idx}`, { method: 'DELETE' })
      const serverVar = (updated.variants || [])[slot - 1] || {}
      setV(slot, { deletingAiIdx: null, aiImages: serverVar.ai_generated_images ?? [] })
    } catch (e) { setError(e.message) }
  }

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <div style={S.breadcrumb}>
          <span style={S.breadLink} onClick={onBack}>← {project.title}</span>
          <span style={S.breadSep}>›</span>
          {char.color && <span style={{ ...S.colorDot, background: char.color }} />}
          <span style={{ color: 'var(--text)', fontWeight: 600 }}>{char.name}</span>
        </div>
        {onSendToGenerate && (
          <button
            style={{ fontSize: 12, padding: '6px 14px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontWeight: 600 }}
            onClick={() => {
              const parts = [char.name]
              if (char.core_traits) parts.push(char.core_traits)
              if (char.outfit) parts.push(`服裝：${char.outfit}`)
              onSendToGenerate(parts.join('，'))
            }}
            title="將角色特徵帶入文字→生圖 Tab"
          >→ 以此角色生圖</button>
        )}
      </div>

      {/* ── Tab bar ── */}
      {editingTabIdx !== null ? (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', maxWidth: 260 }}>
          <input
            style={{ ...S.input, flex: 1, padding: '5px 10px', fontSize: 13 }}
            value={editingTabNameVal} autoFocus
            onChange={e => setEditingTabNameVal(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') confirmTabName(); if (e.key === 'Escape') setEditingTabIdx(null) }}
          />
          <button style={{ ...S.btnSm, fontSize: 12, padding: '4px 10px' }} disabled={savingTabName} onClick={confirmTabName}>
            {savingTabName ? <Spinner /> : '確認'}
          </button>
          <button style={{ ...S.btnSm, fontSize: 12, padding: '4px 10px' }} onClick={() => setEditingTabIdx(null)}>取消</button>
        </div>
      ) : (
        <div style={S.varTabBar}>
          {tabNames.map((name, idx) => (
            <button
              key={idx}
              style={{ ...S.varTab, ...(activeTab === idx ? S.varTabActive : {}) }}
              onClick={() => setActiveTab(idx)}
            >
              {name}
              <span
                style={S.tabEditBtn}
                title="重新命名"
                onClick={e => { e.stopPropagation(); startEditTabName(idx) }}
              >✎</span>
            </button>
          ))}
        </div>
      )}

      {error && <p style={S.error}>{error}</p>}

      {activeTab === 0 ? (
      <div style={S.detail}>
        {/* ── 左欄 ── */}
        <div style={S.detailLeft}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={S.sectionLabel}>AI 整理資訊</span>
              <button style={S.btnSm} onClick={runSummarize} disabled={summarizing}>
                {summarizing ? <><Spinner />整理中...</> : 'AI 重新整理'}
              </button>
            </div>
            {char.ai_summary
              ? <div style={S.summaryCard}>{char.ai_summary}</div>
              : <div style={S.summaryPlaceholder}>點擊「AI 重新整理」讓 AI 根據角色資料生成設定檔</div>
            }
          </div>

          {/* 概念圖（最多3張） */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={S.sectionLabel}>概念圖（{conceptImages.length}/3）</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
              {conceptImages.map((img, idx) => (
                <div key={idx} style={{ position: 'relative', aspectRatio: '1/1', borderRadius: 8, overflow: 'hidden', background: 'var(--border)' }}>
                  <img
                    src={apiUrl(`/characters/${char.id}/concept-images/${idx}?t=${img}`)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover', cursor: 'zoom-in' }}
                    alt={`概念圖${idx + 1}`}
                    title="點擊放大"
                    onClick={() => setLightboxSrc(apiUrl(`/characters/${char.id}/concept-images/${idx}?t=${img}`))}
                  />
                  {deletingConceptIdx === idx
                    ? <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.75)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                        <span style={{ fontSize: 11, color: '#f07070' }}>確認刪除？</span>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button onClick={() => deleteConceptImage(idx)} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: 'none', background: '#5c2020', color: '#f07070', cursor: 'pointer' }}>刪除</button>
                          <button onClick={() => setDeletingConceptIdx(null)} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'transparent', color: 'var(--muted)', cursor: 'pointer' }}>取消</button>
                        </div>
                      </div>
                    : <button
                        onClick={() => setDeletingConceptIdx(idx)}
                        style={{ position: 'absolute', top: 3, right: 3, width: 20, height: 20, borderRadius: '50%', border: 'none', background: 'rgba(0,0,0,0.72)', color: '#fff', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}
                      >×</button>
                  }
                </div>
              ))}
              {conceptImages.length < 3 && (
                <div
                  style={{ aspectRatio: '1/1', borderRadius: 8, border: '2px dashed var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--muted)', fontSize: 24, transition: 'border-color .2s' }}
                  onClick={() => conceptRef.current.click()}
                  onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                >
                  {uploadingConcept ? <Spinner /> : '+'}
                </div>
              )}
            </div>
            <input ref={conceptRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={e => { if (e.target.files[0]) uploadConceptImage(e.target.files[0]); e.target.value = '' }} />
          </div>

          {/* AI 人設圖 */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: ipaEnabled ? 8 : 6 }}>
              <span style={S.sectionLabel}>AI 人設圖（{aiImages.length}/8）</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: ipaEnabled ? '#7eb8f7' : '#666', cursor: 'pointer', userSelect: 'none' }}>
                  <input type="checkbox" checked={ipaEnabled} onChange={e => { setIpaEnabled(e.target.checked); _saveGenPref(initChar.id, null, 'ipaEnabled', e.target.checked) }}
                    style={{ cursor: 'pointer', accentColor: '#7eb8f7' }} />
                  概念圖參考
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: cnEnabled ? '#7eb8f7' : '#666', cursor: 'pointer', userSelect: 'none' }}>
                  <input type="checkbox" checked={cnEnabled} onChange={e => { setCnEnabled(e.target.checked); _saveGenPref(initChar.id, null, 'cnEnabled', e.target.checked) }}
                    style={{ cursor: 'pointer', accentColor: '#7eb8f7' }} />
                  ControlNet
                </label>
                <button style={S.btnSm} disabled={generating} onClick={generateDesignImage}>
                  {generating ? <><Spinner />生成中...</> : '生成人設圖'}
                </button>
              </div>
            </div>
            {ipaEnabled && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>IPA 強度</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                <input type="range" min={0.1} max={1.5} step={0.05} value={ipaWeight}
                  style={{ flex: 1, accentColor: '#7eb8f7' }}
                  onChange={e => { const v = Number(e.target.value); setIpaWeight(v); _saveGenPref(initChar.id, null, 'ipaWeight', v) }} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
                <span style={{ fontSize: 12, color: '#7eb8f7', minWidth: 30, textAlign: 'right' }}>{ipaWeight.toFixed(2)}</span>
              </div>
            )}
            {cnEnabled && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>CN 強度</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                <input type="range" min={0.1} max={1.5} step={0.05} value={cnWeight}
                  style={{ flex: 1, accentColor: '#7eb8f7' }}
                  onChange={e => { const v = Number(e.target.value); setCnWeight(v); _saveGenPref(initChar.id, null, 'cnWeight', v) }} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
                <span style={{ fontSize: 12, color: '#7eb8f7', minWidth: 30, textAlign: 'right' }}>{cnWeight.toFixed(2)}</span>
              </div>
            )}

            {/* 待確認佇列（一次顯示一張） */}
            {pendingQueue.length > 0 && (
              <div style={{ marginBottom: 10, border: '1px solid var(--border)', borderRadius: 10, padding: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
                    {pendingQueue[0].label}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    待確認 {pendingQueue.length} 張
                  </span>
                </div>
                
                <img
                  src={pendingQueue[0].url}
                  style={{ ...S.genImg, marginTop: 0, cursor: 'zoom-in' }}
                  alt={pendingQueue[0].label}
                  title="點擊放大"
                  onClick={() => setLightboxSrc(pendingQueue[0].url)}
                />

                <div style={{ ...S.btnRow, marginTop: 6 }}>
                  <button
                    style={{ ...S.btn, flex: 1, padding: '7px 0', fontSize: 13 }}
                    disabled={savingGen || aiImages.length >= 8}
                    onClick={savePendingFirst}
                  >
                    {savingGen ? <><Spinner />儲存中...</> : aiImages.length >= 8 ? '已達上限' : '儲存此圖'}
                  </button>
                  <button style={S.btnSm} onClick={discardPendingFirst}>捨棄</button>
                  {pendingQueue.length > 1 && (
                    <button style={{ ...S.btnSm, color: 'var(--danger)' }} onClick={discardAllPending}>全捨棄</button>
                  )}
                </div>

                {lastTimings && (
                  <div style={{ marginTop: 8, padding: '8px 10px', background: '#0d0d18', borderRadius: 8, border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 5, fontWeight: 600, letterSpacing: 0.5 }}>⏱ 生成耗時</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                      {[
                        lastTimings.vision_extract    != null && ['視覺分析',  lastTimings.models?.vision,   lastTimings.vision_extract],
                        lastTimings.body_coverage     != null && ['姿態偵測',  lastTimings.models?.vision,   lastTimings.body_coverage],
                        lastTimings.compile_prompt    != null && ['提示詞編譯', lastTimings.models?.text,    lastTimings.compile_prompt],
                        lastTimings.compile_ai_prompt != null && ['AI提示詞',  lastTimings.models?.text,    lastTimings.compile_ai_prompt],
                        lastTimings.canvas_expand     != null && ['Canvas Expand (Flux)', lastTimings.models?.workflow, lastTimings.canvas_expand],
                        lastTimings.upload            != null && ['圖片上傳',  null,                         lastTimings.upload],
                        lastTimings.comfyui           != null && ['ComfyUI 生成', lastTimings.models?.workflow, lastTimings.comfyui],
                      ].filter(Boolean).map(([label, model, sec]) => (
                        <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                          <span style={{ color: 'var(--muted)' }}>
                            {label}
                            {model && <span style={{ color: '#555', marginLeft: 4, fontSize: 10 }}>({model})</span>}
                          </span>
                          <span style={{ color: 'var(--text)', fontFamily: 'monospace' }}>{sec}s</span>
                        </div>
                      ))}
                      {(() => {
                        const keys = ['vision_extract','body_coverage','compile_prompt','compile_ai_prompt','canvas_expand','upload','comfyui']
                        const sum = keys.reduce((a, k) => a + (lastTimings[k] ?? 0), 0)
                        const other = Math.round((lastTimings.total - sum) * 10) / 10
                        return other > 0.5 ? (
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                            <span style={{ color: 'var(--muted)' }}>其他</span>
                            <span style={{ color: 'var(--text)', fontFamily: 'monospace' }}>{other}s</span>
                          </div>
                        ) : null
                      })()}
                      <div style={{ borderTop: '1px solid var(--border)', marginTop: 3, paddingTop: 3, display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                        <span style={{ color: 'var(--accent)', fontWeight: 600 }}>總計</span>
                        <span style={{ color: 'var(--accent)', fontFamily: 'monospace', fontWeight: 600 }}>{lastTimings.total}s</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 已儲存的 AI 圖 */}
            {aiImages.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {aiImages.map((img, idx) => (
                  <div key={idx} style={{ borderRadius: 8, overflow: 'hidden' }}>
                    <img
                      src={apiUrl(`/characters/${char.id}/ai-images/${idx}?t=${img}`)}
                      style={{ width: '100%', display: 'block', borderRadius: 8, cursor: 'zoom-in' }}
                      alt={`AI圖${idx + 1}`}
                      title="點擊放大"
                      onClick={() => setLightboxSrc(apiUrl(`/characters/${char.id}/ai-images/${idx}?t=${img}`))}
                    />
                    <div style={{ display: 'flex', gap: 4, marginTop: 4, justifyContent: 'center' }}>
                      <a href={apiUrl(`/characters/${char.id}/ai-images/${idx}`)} download={`${char.name}_ai_${idx + 1}.png`} style={{ ...S.btnSm, fontSize: 11, padding: '3px 8px', textDecoration: 'none', textAlign: 'center' }}>下載</a>
                      {deletingAiIdx === idx
                        ? <>
                            <button style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: 'none', background: '#5c2020', color: '#f07070', cursor: 'pointer' }} onClick={() => deleteAiImage(idx)}>確認</button>
                            <button style={{ ...S.btnSm, fontSize: 11, padding: '3px 8px' }} onClick={() => setDeletingAiIdx(null)}>取消</button>
                          </>
                        : <button style={{ ...S.btnDanger, fontSize: 11, padding: '3px 8px' }} onClick={() => setDeletingAiIdx(idx)}>移除</button>
                      }
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 刪除角色 */}
          <div>
            {!showDelete
              ? <button style={{ ...S.btnDanger, width: '100%', padding: '8px 0', textAlign: 'center' }} onClick={() => setShowDelete(true)}>刪除角色</button>
              : <DeleteConfirm
                  label={`永久刪除角色「${char.name}」`}
                  name={char.name}
                  loading={deleting}
                  onConfirm={deleteChar}
                  onCancel={() => setShowDelete(false)}
                />
            }
          </div>
        </div>

        {/* ── 右欄 ── */}
        <div style={S.detailRight}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={S.sectionLabel}>角色資料（可編輯）</span>
            <button style={S.btnSm} disabled={savingFields} onClick={saveFields}>
              {savingFields ? <><Spinner />儲存中...</> : '儲存所有變更'}
            </button>
          </div>

          <div style={S.row}>
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>角色名稱</label>
              <input style={S.input} value={charName} onChange={e => setCharName(e.target.value)} />
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}>代表色</label>
              <div style={S.colorRow}>
                <input type="color" style={S.colorPicker} value={color || '#888888'} onChange={e => setColor(e.target.value)} />
                <span style={S.colorCode}>{color || '未設定'}</span>
                {color && <button style={{ ...S.btnSm, fontSize: 11, padding: '4px 10px' }} onClick={() => setColor('')}>清除</button>}
              </div>
            </div>
          </div>

          <div style={S.row}>
            <div style={S.fieldGroup}>
              <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>年齡</label>
              <input type="number" style={S.input} value={age} onChange={e => setAge(e.target.value)} placeholder="例如：18" min="0" max="9999" />
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>身高 (cm)</label>
              <input type="number" style={S.input} value={height} onChange={e => setHeight(e.target.value)} placeholder="例如：162" min="50" max="250" />
            </div>
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>生日</label>
              <input style={S.input} value={birthday} onChange={e => setBirthday(e.target.value)} placeholder="例如：5月16日 或 1998-05-16" />
            </div>
          </div>

          <div>
            <label style={S.label}>
              性別
              {gender && age !== '' && (
                <span style={{ marginLeft: 8, fontFamily: 'monospace', fontSize: 11, color: 'var(--accent)' }}>
                  → {gender === 'female' ? (parseInt(age) < 25 ? '1girl' : parseInt(age) < 40 ? '1woman' : '1woman, mature female') : gender === 'male' ? (parseInt(age) < 25 ? '1boy' : parseInt(age) < 40 ? '1man' : '1man, mature male') : 'androgynous'}
                </span>
              )}
            </label>
            <GenderPicker value={gender} onChange={setGender} />
          </div>

          {/* 畫風 */}
          <div>
            <label style={S.label}>預設畫風</label>
            <select
              style={S.select}
              value={artStyleId ?? ''}
              onChange={e => setArtStyleId(e.target.value ? parseInt(e.target.value) : null)}
            >
              <option value="">（不設定，依全域 checkpoint 自動偵測）</option>
              {artStyles.map(s => (
                <option key={s.id} value={s.id}>{s.name} [{s.base_style}]</option>
              ))}
            </select>
          </div>

          {/* 角色專屬 LoRA（直通欄位，獨立於畫風） */}
          <div>
            <label style={S.label}>專屬 LoRA</label>
            <select
              style={S.select}
              value={loraName}
              onChange={e => setLoraName(e.target.value)}
            >
              <option value="">（不使用專屬 LoRA）</option>
              {/* 已選但清單中沒有（ComfyUI 離線）時仍保留目前值 */}
              {loraName && !loraList.includes(loraName) && (
                <option value={loraName}>{loraName}（目前設定）</option>
              )}
              {loraList.map(l => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
            {loraName && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>權重</span>
                <input
                  type="range" min="0" max="1" step="0.05"
                  value={loraWeight}
                  onChange={e => setLoraWeight(parseFloat(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ fontSize: 12, color: 'var(--text)', width: 32, textAlign: 'right' }}>
                  {Number(loraWeight).toFixed(2)}
                </span>
              </div>
            )}
          </div>

          {/* 所屬勢力 */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <label style={S.label}>所屬勢力</label>
              {availableFactions.length > 0 && (
                <button style={{ ...S.btnSm, fontSize: 11, padding: '3px 10px' }} onClick={() => setAddingFaction(s => !s)}>
                  {addingFaction ? '取消' : '+ 加入勢力'}
                </button>
              )}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {charFactions.length === 0 && !addingFaction && <span style={S.muted}>無</span>}
              {charFactions.map(f => (
                <span key={f.id} style={S.factionChip}>
                  {f.name}
                  <span style={S.chipX} onClick={() => leaveFaction(f.id)}>×</span>
                </span>
              ))}
            </div>
            {addingFaction && availableFactions.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                {availableFactions.map(f => (
                  <button key={f.id} style={S.btnSm} onClick={() => joinFaction(f.id)}>{f.name}</button>
                ))}
              </div>
            )}
          </div>

          <div>
            <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>外貌 / 個性特徵</label>
            <textarea style={{ ...S.textarea, minHeight: 70 }} value={traits} onChange={e => setTraits(e.target.value)} placeholder="髮色、體型、個性..." />
          </div>
          <div>
            <label style={S.label}>行為模式</label>
            <textarea style={{ ...S.textarea, minHeight: 70 }} value={behavior} onChange={e => setBehavior(e.target.value)} placeholder="面對危機的反應、習慣..." />
          </div>
          <div>
            <label style={S.label}>說話風格</label>
            <textarea style={{ ...S.textarea, minHeight: 50 }} value={voice} onChange={e => setVoice(e.target.value)} placeholder="語氣、口頭禪..." />
          </div>
          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={outfitEnabled}
                onChange={e => { setOutfitEnabled(e.target.checked); _saveGenPref(initChar.id, null, 'outfitEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
              />
              <span style={{ color: 'var(--accent)' }}>✦ </span>服裝設定
            </label>
            {outfitEnabled && (
              <>
                <textarea
                  style={{ ...S.textarea, minHeight: 60 }}
                  value={outfit}
                  onChange={e => setOutfit(e.target.value)}
                  placeholder="例如：白色禮服、黑色窄裙、學生制服、和服..."
                />
                <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>服裝描述會加入生成提示詞，影響圖片中的穿著</p>
              </>
            )}
          </div>

          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={aiPromptEnabled}
                onChange={e => { setAiPromptEnabled(e.target.checked); _saveGenPref(initChar.id, null, 'aiPromptEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
              />
              <span style={{ color: 'var(--accent)' }}>✦ </span>AI 提示詞
            </label>
            {aiPromptEnabled && (
              <>
                <textarea
                  style={{ ...S.textarea, minHeight: 60, fontFamily: 'monospace', fontSize: 13 }}
                  value={aiPrompt}
                  onChange={e => setAiPrompt(e.target.value)}
                  placeholder="中英文皆可，例如：flat color, clean lineart 或 戲劇性光影、強烈對比"
                />
                <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>中英文皆接受，獨立編譯後置於 prompt 最前端，強制力優先於角色描述</p>
              </>
            )}
          </div>

          <div>
            <label style={S.label}>創作筆記</label>
            <textarea style={{ ...S.textarea, minHeight: 120 }} value={notes} onChange={e => setNotes(e.target.value)} placeholder="隨時新增想法..." />
            <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>供「AI 重新整理」及問答使用，不影響圖片生成</p>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ ...S.label, marginBottom: 0, fontFamily: 'monospace', letterSpacing: 1 }}>DEBUG PROMPT</span>
              <button
                style={{ ...S.btnSm, fontSize: 11, padding: '3px 10px' }}
                onClick={() => setShowDebugPrompt(s => !s)}
              >
                {showDebugPrompt ? '隱藏' : '顯示'}
              </button>
            </div>
            {showDebugPrompt && (
              lastDebugPrompt
                ? <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontSize: 10, color: '#7eb8f7', letterSpacing: 1, fontFamily: 'monospace' }}>中文描述（AI 翻譯前）</div>
                      {lastFlatDraft != null && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: lastFlatDraft ? '#2a1e0e' : '#0e2a1e',
                          color: lastFlatDraft ? '#f7c87e' : '#7ef7c8',
                          border: `1px solid ${lastFlatDraft ? '#6a4a1e' : '#1e6a4a'}` }}>
                          {lastFlatDraft ? '單色稿 → 文字優先' : '正式上色 → 視覺優先'}
                        </div>
                      )}
                      {lastIpaUsed != null && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: lastIpaUsed ? '#0e1a2a' : '#1e1e1e',
                          color: lastIpaUsed ? '#7eb8f7' : '#666',
                          border: `1px solid ${lastIpaUsed ? '#2a5080' : '#444'}` }}>
                          {lastIpaUsed ? 'IP-Adapter ON' : 'IP-Adapter OFF'}
                        </div>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: '#7ef7c8', background: '#0e1e2a', padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, border: '1px solid #1e4a3a', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                      {lastRawDesc ?? '—'}
                    </div>
                    {lastAiPromptCompiled !== null && (
                      <>
                        <div style={{ fontSize: 10, letterSpacing: 1, fontFamily: 'monospace', marginTop: 2,
                          color: lastAiPromptCompiled === '[compilation_failed]' ? '#f07070' : '#f7c87e' }}>
                          AI 提示詞編譯結果{lastAiPromptCompiled === '[compilation_failed]' ? ' ⚠ 失敗' : '（置於 prompt 首位）'}
                        </div>
                        <div style={{ fontSize: 11, padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, fontFamily: 'monospace',
                          color: lastAiPromptCompiled === '[compilation_failed]' ? '#f07070' : '#f7c87e',
                          background: lastAiPromptCompiled === '[compilation_failed]' ? '#1e0d0d' : '#1e1a0a',
                          border: `1px solid ${lastAiPromptCompiled === '[compilation_failed]' ? '#5c2020' : '#6a5a1e'}` }}>
                          {lastAiPromptCompiled === '[compilation_failed]' ? 'AI 提示詞未套用（Ollama 翻譯錯誤）' : lastAiPromptCompiled}
                        </div>
                      </>
                    )}
                    <div style={{ fontSize: 10, color: '#b09ef0', letterSpacing: 1, fontFamily: 'monospace', marginTop: 2 }}>最終 Prompt（英文）</div>
                    <div style={{ fontSize: 11, color: '#b09ef0', background: '#1e1a3a', padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, border: '1px solid #3a2d6a', fontFamily: 'monospace' }}>
                      {lastDebugPrompt}
                    </div>
                  </div>
                : <p style={{ ...S.muted, fontSize: 11 }}>尚未生成人設圖，無 prompt 記錄</p>
            )}
          </div>
        </div>
      </div>
      ) : (
      /* ── Variant detail (Tab 2 / Tab 3) ── */
      <div style={S.detail}>
        {/* Left col: variant images */}
        <div style={S.detailLeft}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={S.sectionLabel}>AI 整理資訊</span>
              <button style={S.btnSm} onClick={runVariantSummarize} disabled={vState.summarizing}>
                {vState.summarizing ? <><Spinner />整理中...</> : 'AI 重新整理'}
              </button>
            </div>
            {vState.aiSummary
              ? <div style={S.summaryCard}>{vState.aiSummary}</div>
              : <div style={S.summaryPlaceholder}>點擊「AI 重新整理」生成此版本設定檔</div>
            }
          </div>

          {/* Variant concept images */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={S.sectionLabel}>概念圖（{vState.conceptImages.length}/3）</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
              {vState.conceptImages.map((img, idx) => (
                <div key={idx} style={{ position: 'relative', aspectRatio: '1/1', borderRadius: 8, overflow: 'hidden', background: 'var(--border)' }}>
                  <img
                    src={apiUrl(`/characters/${char.id}/variants/${activeTab}/concept-images/${idx}?t=${img}`)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover', cursor: 'zoom-in' }}
                    alt={`概念圖${idx + 1}`}
                    onClick={() => setLightboxSrc(apiUrl(`/characters/${char.id}/variants/${activeTab}/concept-images/${idx}?t=${img}`))}
                  />
                  {vState.deletingConceptIdx === idx
                    ? <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.75)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                        <span style={{ fontSize: 11, color: '#f07070' }}>確認刪除？</span>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button onClick={() => deleteVariantConceptImage(activeTab, idx)} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: 'none', background: '#5c2020', color: '#f07070', cursor: 'pointer' }}>刪除</button>
                          <button onClick={() => setV(activeTab, { deletingConceptIdx: null })} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'transparent', color: 'var(--muted)', cursor: 'pointer' }}>取消</button>
                        </div>
                      </div>
                    : <button onClick={() => setV(activeTab, { deletingConceptIdx: idx })}
                        style={{ position: 'absolute', top: 3, right: 3, width: 20, height: 20, borderRadius: '50%', border: 'none', background: 'rgba(0,0,0,0.72)', color: '#fff', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}
                      >×</button>
                  }
                </div>
              ))}
              {vState.conceptImages.length < 3 && (
                <label
                  htmlFor={`vconc-slot-${activeTab}`}
                  style={{ aspectRatio: '1/1', borderRadius: 8, border: '2px dashed var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--muted)', fontSize: 24, transition: 'border-color .2s' }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                  onClick={() => console.log('[vConc] label clicked, activeTab:', activeTab, 'htmlFor:', `vconc-slot-${activeTab}`)}
                >
                  {vState.uploadingConcept ? <Spinner /> : '+'}
                </label>
              )}
            </div>
            {[1, 2].map(slot => (
              <input key={slot} id={`vconc-slot-${slot}`} type="file" accept="image/*" style={{ display: 'none' }}
                onChange={e => {
                  console.log('[vConc] input onChange', { inputSlot: slot, activeTab, file: e.target.files[0]?.name })
                  if (e.target.files[0]) uploadVariantConceptImage(slot, e.target.files[0])
                  e.target.value = ''
                }} />
            ))}
          </div>

          {/* Variant AI images */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: vState.ipaEnabled ? 8 : 6 }}>
              <span style={S.sectionLabel}>AI 人設圖（{vState.aiImages.length}/8）</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: vState.ipaEnabled ? '#7eb8f7' : '#666', cursor: 'pointer', userSelect: 'none' }}>
                  <input type="checkbox" checked={vState.ipaEnabled} onChange={e => { setV(activeTab, { ipaEnabled: e.target.checked }); _saveGenPref(initChar.id, activeTab, 'ipaEnabled', e.target.checked) }}
                    style={{ cursor: 'pointer', accentColor: '#7eb8f7' }} />
                  概念圖參考
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: (vState.cnEnabled ?? true) ? '#7eb8f7' : '#666', cursor: 'pointer', userSelect: 'none' }}>
                  <input type="checkbox" checked={vState.cnEnabled ?? true} onChange={e => { setV(activeTab, { cnEnabled: e.target.checked }); _saveGenPref(initChar.id, activeTab, 'cnEnabled', e.target.checked) }}
                    style={{ cursor: 'pointer', accentColor: '#7eb8f7' }} />
                  ControlNet
                </label>
                <button style={S.btnSm} disabled={vState.generating} onClick={generateVariantDesignImage}>
                  {vState.generating ? <><Spinner />生成中...</> : '生成人設圖'}
                </button>
              </div>
            </div>
            {vState.ipaEnabled && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>IPA 強度</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                <input type="range" min={0.1} max={1.5} step={0.05} value={vState.ipaWeight ?? 0.6}
                  style={{ flex: 1, accentColor: '#7eb8f7' }}
                  onChange={e => { const v = Number(e.target.value); setV(activeTab, { ipaWeight: v }); _saveGenPref(initChar.id, activeTab, 'ipaWeight', v) }} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
                <span style={{ fontSize: 12, color: '#7eb8f7', minWidth: 30, textAlign: 'right' }}>{(vState.ipaWeight ?? 0.6).toFixed(2)}</span>
              </div>
            )}
            {(vState.cnEnabled ?? true) && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>CN 強度</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                <input type="range" min={0.1} max={1.5} step={0.05} value={vState.cnWeight ?? 0.85}
                  style={{ flex: 1, accentColor: '#7eb8f7' }}
                  onChange={e => { const v = Number(e.target.value); setV(activeTab, { cnWeight: v }); _saveGenPref(initChar.id, activeTab, 'cnWeight', v) }} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
                <span style={{ fontSize: 12, color: '#7eb8f7', minWidth: 30, textAlign: 'right' }}>{(vState.cnWeight ?? 0.85).toFixed(2)}</span>
              </div>
            )}
            {vState.pendingQueue.length > 0 && (
              <div style={{ marginBottom: 10, border: '1px solid var(--border)', borderRadius: 10, padding: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>{vState.pendingQueue[0].label}</span>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>待確認 {vState.pendingQueue.length} 張</span>
                </div>
                <img src={vState.pendingQueue[0].url} style={{ ...S.genImg, marginTop: 0, cursor: 'zoom-in' }} alt="pending"
                  onClick={() => setLightboxSrc(vState.pendingQueue[0].url)} />
                <div style={{ ...S.btnRow, marginTop: 6 }}>
                  <button style={{ ...S.btn, flex: 1, padding: '7px 0', fontSize: 13 }}
                    disabled={vState.savingGen || vState.aiImages.length >= 8} onClick={saveVariantPendingFirst}>
                    {vState.savingGen ? <><Spinner />儲存中...</> : vState.aiImages.length >= 8 ? '已達上限' : '儲存此圖'}
                  </button>
                  <button style={S.btnSm} disabled={vState.savingGen} onClick={() => { URL.revokeObjectURL(vState.pendingQueue[0].url); setV(activeTab, { pendingQueue: vState.pendingQueue.slice(1) }) }}>捨棄</button>
                </div>
                {vState.lastTimings && (
                  <div style={{ marginTop: 8, padding: '8px 10px', background: '#0d0d18', borderRadius: 8, border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 5, fontWeight: 600 }}>⏱ 生成耗時</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                      {[
                        vState.lastTimings.vision_extract    != null && ['視覺分析',   vState.lastTimings.models?.vision,   vState.lastTimings.vision_extract],
                        vState.lastTimings.body_coverage     != null && ['姿態偵測',   vState.lastTimings.models?.vision,   vState.lastTimings.body_coverage],
                        vState.lastTimings.compile_prompt    != null && ['提示詞編譯', vState.lastTimings.models?.text,     vState.lastTimings.compile_prompt],
                        vState.lastTimings.compile_ai_prompt != null && ['AI提示詞',  vState.lastTimings.models?.text,     vState.lastTimings.compile_ai_prompt],
                        vState.lastTimings.pass1             != null && ['Pass 1 粗稿', vState.lastTimings.models?.workflow, vState.lastTimings.pass1],
                        vState.lastTimings.upload            != null && ['圖片上傳',  null,                                 vState.lastTimings.upload],
                        vState.lastTimings.comfyui           != null && ['ComfyUI 生成', vState.lastTimings.models?.workflow, vState.lastTimings.comfyui],
                      ].filter(Boolean).map(([label, model, sec]) => (
                        <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                          <span style={{ color: 'var(--muted)' }}>
                            {label}
                            {model && <span style={{ color: '#555', marginLeft: 4, fontSize: 10 }}>({model})</span>}
                          </span>
                          <span style={{ fontFamily: 'monospace' }}>{sec}s</span>
                        </div>
                      ))}
                      {(() => {
                        const keys = ['vision_extract','body_coverage','compile_prompt','compile_ai_prompt','canvas_expand','upload','comfyui']
                        const sum = keys.reduce((a, k) => a + (vState.lastTimings[k] ?? 0), 0)
                        const other = Math.round((vState.lastTimings.total - sum) * 10) / 10
                        return other > 0.5 ? (
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                            <span style={{ color: 'var(--muted)' }}>其他</span>
                            <span style={{ fontFamily: 'monospace' }}>{other}s</span>
                          </div>
                        ) : null
                      })()}
                      <div style={{ borderTop: '1px solid var(--border)', marginTop: 3, paddingTop: 3, display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                        <span style={{ color: 'var(--accent)', fontWeight: 600 }}>總計</span>
                        <span style={{ color: 'var(--accent)', fontFamily: 'monospace', fontWeight: 600 }}>{vState.lastTimings.total}s</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
            {vState.aiImages.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {vState.aiImages.map((img, idx) => (
                  <div key={idx} style={{ borderRadius: 8, overflow: 'hidden' }}>
                    <img src={apiUrl(`/characters/${char.id}/variants/${activeTab}/ai-images/${idx}?t=${img}`)}
                      style={{ width: '100%', display: 'block', borderRadius: 8, cursor: 'zoom-in' }} alt={`AI圖${idx + 1}`}
                      onClick={() => setLightboxSrc(apiUrl(`/characters/${char.id}/variants/${activeTab}/ai-images/${idx}?t=${img}`))} />
                    <div style={{ display: 'flex', gap: 4, marginTop: 4, justifyContent: 'center' }}>
                      <a href={apiUrl(`/characters/${char.id}/variants/${activeTab}/ai-images/${idx}`)}
                        download={`${char.name}_v${activeTab}_ai_${idx + 1}.png`}
                        style={{ ...S.btnSm, fontSize: 11, padding: '3px 8px', textDecoration: 'none', textAlign: 'center' }}>下載</a>
                      {vState.deletingAiIdx === idx
                        ? <>
                            <button style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: 'none', background: '#5c2020', color: '#f07070', cursor: 'pointer' }} onClick={() => deleteVariantAiImage(activeTab, idx)}>確認</button>
                            <button style={{ ...S.btnSm, fontSize: 11, padding: '3px 8px' }} onClick={() => setV(activeTab, { deletingAiIdx: null })}>取消</button>
                          </>
                        : <button style={{ ...S.btnDanger, fontSize: 11, padding: '3px 8px' }} onClick={() => setV(activeTab, { deletingAiIdx: idx })}>移除</button>
                      }
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right col: variant fields (name locked) */}
        <div style={S.detailRight}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={S.sectionLabel}>角色資料（可編輯）</span>
            <button style={S.btnSm} disabled={vState.savingFields} onClick={saveVariantFields}>
              {vState.savingFields ? <><Spinner />儲存中...</> : '儲存所有變更'}
            </button>
          </div>
          <div style={S.row}>
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>角色名稱（鎖定）</label>
              <input style={{ ...S.input, opacity: 0.5, cursor: 'not-allowed' }} value={char.name} readOnly />
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}>代表色</label>
              <div style={S.colorRow}>
                <input type="color" style={S.colorPicker} value={vState.color || '#888888'} onChange={e => setV(activeTab, { color: e.target.value })} />
                <span style={S.colorCode}>{vState.color || '未設定'}</span>
                {vState.color && <button style={{ ...S.btnSm, fontSize: 11, padding: '4px 10px' }} onClick={() => setV(activeTab, { color: '' })}>清除</button>}
              </div>
            </div>
          </div>
          <div style={S.row}>
            <div style={S.fieldGroup}>
              <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>年齡</label>
              <input type="number" style={S.input} value={vState.age} onChange={e => setV(activeTab, { age: e.target.value })} placeholder="例如：18" min="0" max="9999" />
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>身高 (cm)</label>
              <input type="number" style={S.input} value={vState.height} onChange={e => setV(activeTab, { height: e.target.value })} placeholder="例如：162" min="50" max="250" />
            </div>
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>生日</label>
              <input style={S.input} value={vState.birthday} onChange={e => setV(activeTab, { birthday: e.target.value })} placeholder="例如：5月16日" />
            </div>
          </div>
          <div>
            <label style={S.label}>性別</label>
            <GenderPicker value={vState.gender} onChange={v => setV(activeTab, { gender: v })} />
          </div>
          <div>
            <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>外貌 / 個性特徵</label>
            <textarea style={{ ...S.textarea, minHeight: 70 }} value={vState.traits} onChange={e => setV(activeTab, { traits: e.target.value })} placeholder="髮色、體型、個性..." />
          </div>
          <div>
            <label style={S.label}>行為模式</label>
            <textarea style={{ ...S.textarea, minHeight: 70 }} value={vState.behavior} onChange={e => setV(activeTab, { behavior: e.target.value })} placeholder="面對危機的反應、習慣..." />
          </div>
          <div>
            <label style={S.label}>說話風格</label>
            <textarea style={{ ...S.textarea, minHeight: 50 }} value={vState.voice} onChange={e => setV(activeTab, { voice: e.target.value })} placeholder="語氣、口頭禪..." />
          </div>
          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={vState.outfitEnabled} onChange={e => { setV(activeTab, { outfitEnabled: e.target.checked }); _saveGenPref(initChar.id, activeTab, 'outfitEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
              <span style={{ color: 'var(--accent)' }}>✦ </span>服裝設定
            </label>
            {vState.outfitEnabled && (
              <>
                <textarea style={{ ...S.textarea, minHeight: 60 }}
                  value={vState.outfit} onChange={e => setV(activeTab, { outfit: e.target.value })}
                  placeholder="例如：白色禮服、黑色窄裙、學生制服、和服..." />
                <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>服裝描述會加入生成提示詞，影響圖片中的穿著</p>
              </>
            )}
          </div>

          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={vState.aiPromptEnabled} onChange={e => { setV(activeTab, { aiPromptEnabled: e.target.checked }); _saveGenPref(initChar.id, activeTab, 'aiPromptEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
              <span style={{ color: 'var(--accent)' }}>✦ </span>AI 提示詞
            </label>
            {vState.aiPromptEnabled && (
              <>
                <textarea style={{ ...S.textarea, minHeight: 60, fontFamily: 'monospace', fontSize: 13 }}
                  value={vState.aiPrompt} onChange={e => setV(activeTab, { aiPrompt: e.target.value })}
                  placeholder="中英文皆可，例如：flat color, clean lineart" />
                <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>中英文皆接受，獨立編譯後置於 prompt 最前端</p>
              </>
            )}
          </div>
          <div>
            <label style={S.label}>創作筆記</label>
            <textarea style={{ ...S.textarea, minHeight: 120 }} value={vState.notes} onChange={e => setV(activeTab, { notes: e.target.value })} placeholder="隨時新增想法..." />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ ...S.label, marginBottom: 0, fontFamily: 'monospace', letterSpacing: 1 }}>DEBUG PROMPT</span>
              <button style={{ ...S.btnSm, fontSize: 11, padding: '3px 10px' }} onClick={() => setV(activeTab, { showDebugPrompt: !vState.showDebugPrompt })}>
                {vState.showDebugPrompt ? '隱藏' : '顯示'}
              </button>
            </div>
            {vState.showDebugPrompt && (
              vState.lastDebugPrompt
                ? <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontSize: 10, color: '#7eb8f7', letterSpacing: 1, fontFamily: 'monospace' }}>中文描述（AI 翻譯前）</div>
                      {vState.lastFlatDraft != null && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: vState.lastFlatDraft ? '#2a1e0e' : '#0e2a1e',
                          color: vState.lastFlatDraft ? '#f7c87e' : '#7ef7c8',
                          border: `1px solid ${vState.lastFlatDraft ? '#6a4a1e' : '#1e6a4a'}` }}>
                          {vState.lastFlatDraft ? '單色稿 → 文字優先' : '正式上色 → 視覺優先'}
                        </div>
                      )}
                      {vState.lastIpaUsed != null && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: vState.lastIpaUsed ? '#0e1a2a' : '#1e1e1e',
                          color: vState.lastIpaUsed ? '#7eb8f7' : '#666',
                          border: `1px solid ${vState.lastIpaUsed ? '#2a5080' : '#444'}` }}>
                          {vState.lastIpaUsed ? 'IP-Adapter ON' : 'IP-Adapter OFF'}
                        </div>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: '#7ef7c8', background: '#0e1e2a', padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, border: '1px solid #1e4a3a', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                      {vState.lastRawDesc ?? '—'}
                    </div>
                    {vState.lastAiPromptCompiled !== null && (
                      <>
                        <div style={{ fontSize: 10, letterSpacing: 1, fontFamily: 'monospace', marginTop: 2,
                          color: vState.lastAiPromptCompiled === '[compilation_failed]' ? '#f07070' : '#f7c87e' }}>
                          AI 提示詞編譯結果{vState.lastAiPromptCompiled === '[compilation_failed]' ? ' ⚠ 失敗' : '（置於 prompt 首位）'}
                        </div>
                        <div style={{ fontSize: 11, padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, fontFamily: 'monospace',
                          color: vState.lastAiPromptCompiled === '[compilation_failed]' ? '#f07070' : '#f7c87e',
                          background: vState.lastAiPromptCompiled === '[compilation_failed]' ? '#1e0d0d' : '#1e1a0a',
                          border: `1px solid ${vState.lastAiPromptCompiled === '[compilation_failed]' ? '#5c2020' : '#6a5a1e'}` }}>
                          {vState.lastAiPromptCompiled === '[compilation_failed]' ? 'AI 提示詞未套用（Ollama 翻譯錯誤）' : vState.lastAiPromptCompiled}
                        </div>
                      </>
                    )}
                    <div style={{ fontSize: 10, color: '#b09ef0', letterSpacing: 1, fontFamily: 'monospace', marginTop: 2 }}>最終 Prompt（英文）</div>
                    <div style={{ fontSize: 11, color: '#b09ef0', background: '#1e1a3a', padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, border: '1px solid #3a2d6a', fontFamily: 'monospace' }}>{vState.lastDebugPrompt}</div>
                  </div>
                : <p style={{ ...S.muted, fontSize: 11 }}>尚未生成人設圖，無 prompt 記錄</p>
            )}
          </div>
        </div>
      </div>
      )}

      {lightboxSrc && <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function CharacterTab({ onAddHistory, onSendToGenerate }) {
  // view: 'projects' | 'project_create' | 'char_list' | 'faction_detail' | 'char_create' | 'char_detail'
  const [view, setView] = useState('projects')
  const [selectedProject, setSelectedProject] = useState(null)
  const [selectedChar, setSelectedChar] = useState(null)
  const [selectedFaction, setSelectedFaction] = useState(null)
  const [allChars, setAllChars] = useState([])       // all chars in current project (for FactionView add-member)
  const [allFactions, setAllFactions] = useState([]) // all factions in current project (for CharacterDetailView)
  const [projectsKey, setProjectsKey] = useState(0)
  const [charListKey, setCharListKey] = useState(0)
  const [autoEditProject, setAutoEditProject] = useState(false)
  const [returnTo, setReturnTo] = useState('char_list') // where to go back from char_detail

  const goProjects = () => { setView('projects'); setProjectsKey(k => k + 1); setAutoEditProject(false) }
  const goCharList = () => { setView('char_list'); setCharListKey(k => k + 1) }
  const goFactionDetail = () => setView('faction_detail')

  // Load project-level data when entering char_list or faction_detail
  const loadProjectData = async (projectId) => {
    const [chars, facts] = await Promise.all([
      apiFetch(`/projects/${projectId}/characters`).catch(() => []),
      apiFetch(`/projects/${projectId}/factions`).catch(() => []),
    ])
    setAllChars(chars)
    setAllFactions(facts)
  }

  if (view === 'project_create') {
    return (
      <ProjectCreateView
        onBack={goProjects}
        onCreate={(p) => { setSelectedProject(p); setView('char_list') }}
      />
    )
  }

  if (view === 'char_create' && selectedProject) {
    return (
      <CharacterCreateView
        project={selectedProject}
        onBack={goCharList}
        onCreate={(c) => { setSelectedChar(c); setReturnTo('char_list'); setView('char_detail') }}
      />
    )
  }

  if (view === 'char_detail' && selectedChar && selectedProject) {
    return (
      <CharacterDetailView
        character={selectedChar}
        project={selectedProject}
        allFactions={allFactions}
        onBack={() => returnTo === 'faction_detail' ? goFactionDetail() : goCharList()}
        onDeleted={goCharList}
        onAddHistory={onAddHistory}
        onSendToGenerate={onSendToGenerate}
      />
    )
  }

  if (view === 'faction_detail' && selectedFaction && selectedProject) {
    return (
      <FactionView
        faction={selectedFaction}
        project={selectedProject}
        allChars={allChars}
        onBack={goCharList}
        onSelectChar={(c) => { setSelectedChar(c); setReturnTo('faction_detail'); setView('char_detail') }}
      />
    )
  }

  if (view === 'char_list' && selectedProject) {
    return (
      <CharacterListView
        key={charListKey}
        project={selectedProject}
        autoEdit={autoEditProject}
        onBackToProjects={goProjects}
        onSelectChar={(c) => {
          loadProjectData(selectedProject.id)
          setSelectedChar(c); setReturnTo('char_list'); setView('char_detail')
        }}
        onCreateChar={() => setView('char_create')}
        onSelectFaction={(f) => {
          loadProjectData(selectedProject.id)
          setSelectedFaction(f); setView('faction_detail')
        }}
      />
    )
  }

  return (
    <ProjectsView
      key={projectsKey}
      onSelect={(p) => { setAutoEditProject(false); setSelectedProject(p); setView('char_list') }}
      onCreateClick={() => setView('project_create')}
      onEdit={(p) => { setAutoEditProject(true); setSelectedProject(p); setCharListKey(k => k + 1); setView('char_list') }}
    />
  )
}
