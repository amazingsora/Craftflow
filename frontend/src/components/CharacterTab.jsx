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

  // Character grid
  charGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 },
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

function Spinner() { return <span style={S.spinner} /> }

function StatusBadge({ status }) {
  const c = STATUS_COLOR[status] ?? { bg: '#1a1a2e', text: 'var(--muted)' }
  return <span style={{ ...S.badge, background: c.bg, color: c.text }}>{status ?? '—'}</span>
}

// ── ProjectsView ──────────────────────────────────────────────────────────────

function ProjectsView({ onSelect, onCreateClick }) {
  const [projects, setProjects] = useState([])
  const [charCounts, setCharCounts] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/projects/')
      .then(async (list) => {
        setProjects(list)
        // fetch character counts in parallel
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

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <span style={S.toolbarTitle}>作品管理</span>
        <button style={S.addBtn} onClick={onCreateClick}>+ 新增作品</button>
      </div>

      {loading && <p style={S.muted}>載入中...</p>}
      {!loading && projects.length === 0 && (
        <p style={S.muted}>尚無作品。點擊「+ 新增作品」開始建立。</p>
      )}
      {!loading && projects.length > 0 && (
        <div style={S.grid}>
          {projects.map(p => (
            <div
              key={p.id} style={S.card}
              onClick={() => onSelect(p)}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
            >
              <div style={S.cardTitle}>{p.title}</div>
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
        body: JSON.stringify({
          title: title.trim(),
          author: author.trim(),
          synopsis: synopsis.trim() || null,
          genre: genre || null,
          status,
        }),
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
          <textarea
            style={{ ...S.textarea, minHeight: 120 }}
            value={synopsis}
            onChange={e => setSynopsis(e.target.value)}
            placeholder="作品世界觀、主線故事、核心主題...（可隨時補充）"
          />
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

function CharacterListView({ project: initProject, onSelectChar, onCreateChar, onBackToProjects }) {
  const [project, setProject] = useState(initProject)
  const [characters, setCharacters] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [eTitle, setETitle] = useState(initProject.title)
  const [eAuthor, setEAuthor] = useState(initProject.author)
  const [eSynopsis, setESynopsis] = useState(initProject.synopsis ?? '')
  const [eGenre, setEGenre] = useState(initProject.genre ?? '')
  const [eStatus, setEStatus] = useState(initProject.status ?? '構思中')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    apiFetch(`/projects/${project.id}/characters`)
      .then(setCharacters)
      .finally(() => setLoading(false))
  }, [project.id])

  const saveProject = async () => {
    setSaving(true)
    try {
      const updated = await apiFetch(`/projects/${project.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: eTitle, author: eAuthor, synopsis: eSynopsis || null, genre: eGenre || null, status: eStatus }),
      })
      setProject(updated); setEditing(false)
    } catch (e) { console.error(e) }
    finally { setSaving(false) }
  }

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
          <button style={S.btnSm} onClick={() => setEditing(e => !e)}>{editing ? '取消' : '編輯作品'}</button>
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
          <button style={S.btn} disabled={saving} onClick={saveProject}>
            {saving ? <><Spinner />儲存中...</> : '儲存作品資料'}
          </button>
        </div>
      )}

      {!editing && project.synopsis && (
        <p style={{ ...S.muted, lineHeight: 1.7, maxWidth: 640 }}>{project.synopsis}</p>
      )}

      {loading && <p style={S.muted}>載入中...</p>}
      {!loading && characters.length === 0 && (
        <p style={S.muted}>這個作品還沒有角色。點擊「+ 新增角色」開始建立。</p>
      )}
      {!loading && characters.length > 0 && (
        <div style={S.charGrid}>
          {characters.map(c => (
            <div
              key={c.id} style={S.charCard}
              onClick={() => onSelectChar(c)}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
            >
              <div style={S.portrait}>
                {c.portrait_path
                  ? <img src={`${API}/characters/${c.id}/portrait`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="" />
                  : '無概念圖'
                }
              </div>
              <div style={S.charName}>{c.name}</div>
              {c.core_traits && (
                <div style={S.charTraits}>{c.core_traits.slice(0, 50)}{c.core_traits.length > 50 ? '...' : ''}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── CharacterCreateView ───────────────────────────────────────────────────────

function CharacterCreateView({ project, onBack, onCreate }) {
  const [name, setName] = useState('')
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
        <div>
          <label style={S.label}>角色名稱 *</label>
          <input style={S.input} value={name} onChange={e => setName(e.target.value)} placeholder="例如：白鳶" />
        </div>
        <div>
          <label style={S.label}>外貌 / 個性特徵</label>
          <textarea style={S.textarea} value={traits} onChange={e => setTraits(e.target.value)}
            placeholder="例如：銀色長髮、冷靜但內心敏感..." />
        </div>
        <div>
          <label style={S.label}>行為模式</label>
          <textarea style={S.textarea} value={behavior} onChange={e => setBehavior(e.target.value)}
            placeholder="例如：遇到危機會先觀察、不輕易信任人..." />
        </div>
        <div>
          <label style={S.label}>說話風格</label>
          <input style={S.input} value={voice} onChange={e => setVoice(e.target.value)}
            placeholder="例如：言簡意賅、偶爾冷幽默..." />
        </div>
        <div>
          <label style={S.label}>補充筆記</label>
          <textarea style={{ ...S.textarea, minHeight: 100 }} value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="任何額外設定、背景故事..." />
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

function CharacterDetailView({ character: initChar, project, onBack }) {
  const [char, setChar] = useState(initChar)
  const [notes, setNotes] = useState(initChar.notes ?? '')
  const [traits, setTraits] = useState(initChar.core_traits ?? '')
  const [behavior, setBehavior] = useState(initChar.behavior_rules ?? '')
  const [voice, setVoice] = useState(initChar.voice_style ?? '')
  const [savingFields, setSavingFields] = useState(false)
  const [savingNotes, setSavingNotes] = useState(false)
  const [summarizing, setSummarizing] = useState(false)
  const [uploadingPortrait, setUploadingPortrait] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [genImage, setGenImage] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState(null)
  const fileRef = useRef()

  const saveFields = async () => {
    setSavingFields(true)
    try {
      const updated = await apiFetch(`/characters/${char.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ core_traits: traits || null, behavior_rules: behavior || null, voice_style: voice || null, notes: notes || null }),
      })
      setChar(updated)
    } catch (e) { setError(e.message) }
    finally { setSavingFields(false) }
  }

  const saveNotes = saveFields

  const runSummarize = async () => {
    setSummarizing(true); setError(null)
    try {
      const updated = await apiFetch(`/characters/${char.id}/summarize`, { method: 'POST' })
      setChar(updated)
    } catch (e) { setError(e.message) }
    finally { setSummarizing(false) }
  }

  const uploadPortrait = async (file) => {
    if (!file || !file.type.startsWith('image/')) return
    setUploadingPortrait(true); setError(null)
    const body = new FormData()
    body.append('file', file)
    try {
      const updated = await apiFetch(`/characters/${char.id}/portrait`, { method: 'POST', body })
      setChar(updated)
    } catch (e) { setError(e.message) }
    finally { setUploadingPortrait(false) }
  }

  const generateAIImage = async () => {
    setGenerating(true); setError(null); setGenImage(null)
    try {
      const desc = [
        char.name,
        char.core_traits && `外貌：${char.core_traits}`,
        char.voice_style && `風格：${char.voice_style}`,
        '角色插畫，動漫風格',
      ].filter(Boolean).join('，')

      const compiled = await apiFetch('/art/compile-prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: desc }),
      })
      const resp = await fetch(`${API}/art/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: compiled.positive,
          negative_prompt: compiled.negative,
          width: 768, height: 1024, steps: 20, seed: -1,
        }),
      })
      if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail ?? resp.statusText)
      const blob = await resp.blob()
      setGenImage(URL.createObjectURL(blob))
    } catch (e) { setError(e.message) }
    finally { setGenerating(false) }
  }

  const dzStyle = { ...S.dropzone, ...(dragging ? S.dropzoneActive : {}) }

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <div style={S.breadcrumb}>
          <span style={S.breadLink} onClick={onBack}>← {project.title}</span>
          <span style={S.breadSep}>›</span>
          <span style={{ color: 'var(--text)', fontWeight: 600 }}>{char.name}</span>
        </div>
      </div>

      {error && <p style={S.error}>{error}</p>}

      <div style={S.detail}>
        {/* ── 左欄 ── */}
        <div style={S.detailLeft}>
          {/* 左上：AI 整理資訊 */}
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

          {/* 左下：概念圖 */}
          <div>
            <span style={S.sectionLabel}>概念圖</span>
            <div
              style={dzStyle}
              onDrop={e => { e.preventDefault(); setDragging(false); uploadPortrait(e.dataTransfer.files[0]) }}
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onClick={() => fileRef.current.click()}
            >
              {uploadingPortrait
                ? <p style={S.muted}><Spinner />上傳中...</p>
                : char.portrait_path
                  ? <img src={`${API}/characters/${char.id}/portrait?t=${char.portrait_path}`} style={S.portraitImg} alt="概念圖" />
                  : <p style={{ ...S.muted, padding: 16 }}>拖曳或點擊上傳概念圖<br /><span style={{ fontSize: 11 }}>(草稿、線稿、完稿皆可)</span></p>
              }
            </div>
            <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={e => uploadPortrait(e.target.files[0])} />
          </div>

          {/* 根據角色生成 AI 圖 */}
          <div>
            <button style={{ ...S.btn, width: '100%' }} disabled={generating} onClick={generateAIImage}>
              {generating ? <><Spinner />AI 生成中...</> : '根據角色生成 AI 圖'}
            </button>
            {genImage && (
              <>
                <img src={genImage} style={S.genImg} alt="AI generated" />
                <a href={genImage} download={`${char.name}_ai.png`}
                  style={{ ...S.btnSm, display: 'inline-block', marginTop: 6, textDecoration: 'none', textAlign: 'center' }}>
                  下載圖片
                </a>
              </>
            )}
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

          <div>
            <label style={S.label}>外貌 / 個性特徵</label>
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
  // view: 'projects' | 'project_create' | 'char_list' | 'char_create' | 'char_detail'
  const [view, setView] = useState('projects')
  const [selectedProject, setSelectedProject] = useState(null)
  const [selectedChar, setSelectedChar] = useState(null)
  const [projectsKey, setProjectsKey] = useState(0)
  const [charListKey, setCharListKey] = useState(0)

  const goProjects = () => { setView('projects'); setProjectsKey(k => k + 1) }
  const goCharList = () => { setView('char_list'); setCharListKey(k => k + 1) }

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
        onCreate={(c) => { setSelectedChar(c); setView('char_detail') }}
      />
    )
  }

  if (view === 'char_detail' && selectedChar && selectedProject) {
    return (
      <CharacterDetailView
        character={selectedChar}
        project={selectedProject}
        onBack={goCharList}
      />
    )
  }

  if (view === 'char_list' && selectedProject) {
    return (
      <CharacterListView
        key={charListKey}
        project={selectedProject}
        onBackToProjects={goProjects}
        onSelectChar={(c) => { setSelectedChar(c); setView('char_detail') }}
        onCreateChar={() => setView('char_create')}
      />
    )
  }

  return (
    <ProjectsView
      key={projectsKey}
      onSelect={(p) => { setSelectedProject(p); setView('char_list') }}
      onCreateClick={() => setView('project_create')}
    />
  )
}
