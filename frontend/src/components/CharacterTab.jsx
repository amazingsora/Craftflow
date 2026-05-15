import { useState, useEffect, useRef } from 'react'

const API = '/api/v1'

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
  const r = await fetch(`${API}${path}`, opts)
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(err.detail || r.statusText)
  }
  return r.json()
}

async function apiDelete(path) {
  const r = await fetch(`${API}${path}`, { method: 'DELETE' })
  if (!r.ok && r.status !== 204) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(err.detail || r.statusText)
  }
}

function Spinner() { return <span style={S.spinner} /> }

function StatusBadge({ status }) {
  const c = STATUS_COLOR[status] ?? { bg: '#1a1a2e', text: 'var(--muted)' }
  return <span style={{ ...S.badge, background: c.bg, color: c.text }}>{status ?? '—'}</span>
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
          ? <img src={`${API}/characters/${c.id}/concept-images/0`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
          : c.portrait_path
            ? <img src={`${API}/characters/${c.id}/portrait`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
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
          ? <img src={`${API}/factions/${f.id}/thumbnail`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
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
      await fetch(`${API}/factions/${faction.id}/members/${charId}`, { method: 'POST' })
      const char = allChars.find(c => c.id === charId)
      if (char) setMembers(prev => [...prev, char])
      setAddingMember(false)
    } catch (e) { setError(e.message) }
  }

  const removeMember = async (charId) => {
    try {
      await fetch(`${API}/factions/${faction.id}/members/${charId}`, { method: 'DELETE' })
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
                ? <img src={`${API}/factions/${faction.id}/thumbnail?t=${faction.thumbnail_path}`} style={S.portraitImg} alt="縮圖" />
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
                        ? <img src={`${API}/characters/${c.id}/concept-images/0`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
                        : c.portrait_path
                          ? <img src={`${API}/characters/${c.id}/portrait`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
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

function CharacterDetailView({ character: initChar, project, allFactions, onBack, onDeleted }) {
  const [char, setChar] = useState(initChar)
  const [charName, setCharName] = useState(initChar.name)
  const [color, setColor] = useState(initChar.color ?? '')
  const [notes, setNotes] = useState(initChar.notes ?? '')
  const [traits, setTraits] = useState(initChar.core_traits ?? '')
  const [behavior, setBehavior] = useState(initChar.behavior_rules ?? '')
  const [voice, setVoice] = useState(initChar.voice_style ?? '')
  const [age, setAge] = useState(initChar.age ?? '')
  const [birthday, setBirthday] = useState(initChar.birthday ?? '')
  const [aiPrompt, setAiPrompt] = useState(initChar.ai_prompt ?? '')
  const [savingFields, setSavingFields] = useState(false)
  const [summarizing, setSummarizing] = useState(false)
  const [uploadingConcept, setUploadingConcept] = useState(false)
  const [conceptImages, setConceptImages] = useState(initChar.concept_images || [])
  const [generating, setGenerating] = useState(false)
  const [pendingQueue, setPendingQueue] = useState([]) // [{blob, url, label}]
  const [savingGen, setSavingGen] = useState(false)
  const [aiImages, setAiImages] = useState(initChar.ai_generated_images || [])
  const [error, setError] = useState(null)
  const [showDelete, setShowDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // Faction membership
  const [charFactionIds, setCharFactionIds] = useState(initChar.faction_ids ?? [])
  const [addingFaction, setAddingFaction] = useState(false)
  const conceptRef = useRef()

  const charFactions = allFactions.filter(f => charFactionIds.includes(f.id))
  const availableFactions = allFactions.filter(f => !charFactionIds.includes(f.id))

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
          birthday: birthday.trim() || null,
          ai_prompt: aiPrompt.trim() || null,
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
    if (!window.confirm('確定刪除這張概念圖？')) return
    try {
      const updated = await apiFetch(`/characters/${char.id}/concept-images/${idx}`, { method: 'DELETE' })
      setChar(updated)
      setConceptImages(updated.concept_images || [])
    } catch (e) { setError(e.message) }
  }

  const generateDesignImage = async () => {
    setGenerating(true); setError(null); setPendingQueue([])
    try {
      const resp = await fetch(`${API}/characters/${char.id}/generate-design`, { method: 'POST' })
      if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail ?? resp.statusText)
      const blob = await resp.blob()
      setPendingQueue([{ blob, url: URL.createObjectURL(blob), label: '全身人設圖' }])
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
    if (!window.confirm('確定移除這張 AI 生成圖？')) return
    try {
      const updated = await apiFetch(`/characters/${char.id}/ai-images/${idx}`, { method: 'DELETE' })
      setChar(updated)
      setAiImages(updated.ai_generated_images || [])
    } catch (e) { setError(e.message) }
  }

  const joinFaction = async (factionId) => {
    try {
      await fetch(`${API}/factions/${factionId}/members/${char.id}`, { method: 'POST' })
      setCharFactionIds(prev => [...prev, factionId])
      setAddingFaction(false)
    } catch (e) { setError(e.message) }
  }

  const leaveFaction = async (factionId) => {
    try {
      await fetch(`${API}/factions/${factionId}/members/${char.id}`, { method: 'DELETE' })
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

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <div style={S.breadcrumb}>
          <span style={S.breadLink} onClick={onBack}>← {project.title}</span>
          <span style={S.breadSep}>›</span>
          {char.color && <span style={{ ...S.colorDot, background: char.color }} />}
          <span style={{ color: 'var(--text)', fontWeight: 600 }}>{char.name}</span>
        </div>
      </div>

      {error && <p style={S.error}>{error}</p>}

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
                    src={`${API}/characters/${char.id}/concept-images/${idx}?t=${img}`}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    alt={`概念圖${idx + 1}`}
                  />
                  <button
                    onClick={() => deleteConceptImage(idx)}
                    style={{ position: 'absolute', top: 3, right: 3, width: 20, height: 20, borderRadius: '50%', border: 'none', background: 'rgba(0,0,0,0.72)', color: '#fff', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}
                  >×</button>
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={S.sectionLabel}>AI 人設圖（{aiImages.length}/8）</span>
              <button style={S.btnSm} disabled={generating} onClick={generateDesignImage}>
                {generating ? <><Spinner />生成中...</> : '生成人設圖'}
              </button>
            </div>

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
                <img src={pendingQueue[0].url} style={{ ...S.genImg, marginTop: 0 }} alt={pendingQueue[0].label} />
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
              </div>
            )}

            {/* 已儲存的 AI 圖 */}
            {aiImages.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {aiImages.map((img, idx) => (
                  <div key={idx} style={{ borderRadius: 8, overflow: 'hidden' }}>
                    <img src={`${API}/characters/${char.id}/ai-images/${idx}?t=${img}`} style={{ width: '100%', display: 'block', borderRadius: 8 }} alt={`AI圖${idx + 1}`} />
                    <div style={{ display: 'flex', gap: 4, marginTop: 4, justifyContent: 'center' }}>
                      <a href={`${API}/characters/${char.id}/ai-images/${idx}`} download={`${char.name}_ai_${idx + 1}.png`} style={{ ...S.btnSm, fontSize: 11, padding: '3px 8px', textDecoration: 'none', textAlign: 'center' }}>下載</a>
                      <button style={{ ...S.btnDanger, fontSize: 11, padding: '3px 8px' }} onClick={() => deleteAiImage(idx)}>移除</button>
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
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>生日</label>
              <input style={S.input} value={birthday} onChange={e => setBirthday(e.target.value)} placeholder="例如：5月16日 或 1998-05-16" />
            </div>
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
            <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>AI 提示詞</label>
            <textarea
              style={{ ...S.textarea, minHeight: 60, fontFamily: 'monospace', fontSize: 13 }}
              value={aiPrompt}
              onChange={e => setAiPrompt(e.target.value)}
              placeholder="中英文皆可，例如：flat color, clean lineart 或 戲劇性光影、強烈對比"
            />
            <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>中英文皆接受，獨立編譯後置於 prompt 最前端，強制力優先於角色描述</p>
          </div>

          <div>
            <label style={S.label}>創作筆記</label>
            <textarea style={{ ...S.textarea, minHeight: 120 }} value={notes} onChange={e => setNotes(e.target.value)} placeholder="隨時新增想法..." />
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function CharacterTab() {
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
