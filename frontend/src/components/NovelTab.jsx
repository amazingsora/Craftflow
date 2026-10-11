import { useState, useEffect, useCallback } from 'react'
import { Empty } from './ui.jsx'

const API = '/api/v1'

// ── Drag handle icon ───────────────────────────────────────────────────────────
const DragHandle = ({ style }) => (
  <span
    style={{ fontSize: 12, color: 'var(--faint)', cursor: 'grab', userSelect: 'none', flexShrink: 0, ...style }}
    title="拖曳排序"
  >⠿</span>
)

// ── Styles ─────────────────────────────────────────────────────────────────────
const S = {
  root: {
    display: 'flex', height: 'calc(100vh - 140px)', minHeight: 560, overflow: 'hidden',
    background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)',
  },

  sideA: {
    width: 208, flexShrink: 0,
    borderRight: '1px solid var(--border)', background: 'var(--surface-2)',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  sideB: {
    width: 272, flexShrink: 0,
    borderRight: '1px solid var(--border)',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  main: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 },

  panelHeader: {
    padding: '0 8px 0 14px', height: 44, flexShrink: 0,
    fontSize: 12, fontWeight: 600, color: 'var(--text-2)', letterSpacing: '.02em',
    borderBottom: '1px solid var(--border)',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  },

  listScroll: { flex: 1, overflowY: 'auto', padding: '6px 0' },

  // Project list
  projItem: {
    margin: '1px 6px', padding: '7px 10px', cursor: 'pointer', borderRadius: 'var(--r)',
    fontSize: 13, color: 'var(--text)', fontWeight: 500,
  },
  projItemActive: { background: 'var(--accent-soft)', color: 'var(--accent)' },
  projSub: { fontSize: 11, color: 'var(--muted)', marginTop: 2, fontWeight: 400 },

  // Volume block
  volBlock: { paddingBottom: 4 },
  volHeader: {
    padding: '8px 8px 4px 10px',
    display: 'flex', alignItems: 'center', gap: 6,
    cursor: 'default', fontSize: 12, color: 'var(--muted)',
  },
  volLabel: { flex: 1, fontWeight: 600, fontSize: 11.5, color: 'var(--text-2)', letterSpacing: '.02em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  volActions: { display: 'flex', gap: 2, alignItems: 'center', flexShrink: 0 },

  // Chapter item (inside volume)
  chapItem: {
    margin: '1px 6px', padding: '6px 8px 6px 20px', borderRadius: 'var(--r)',
    display: 'flex', alignItems: 'center', gap: 6,
    cursor: 'pointer', fontSize: 13, color: 'var(--text-2)',
  },
  chapItemActive: { background: 'var(--accent-soft)', color: 'var(--accent)', fontWeight: 600 },

  // Drag-over highlight
  dragOver: { outline: '1px dashed var(--accent)', outlineOffset: -1 },

  // Inline forms
  inlineForm: {
    padding: '10px', flexShrink: 0,
    borderBottom: '1px solid var(--border)', background: 'var(--surface)',
    display: 'flex', flexDirection: 'column', gap: 6,
  },
  inlineInput: {
    width: '100%', boxSizing: 'border-box',
    background: 'var(--surface)', border: '1px solid var(--border-strong)',
    borderRadius: 'var(--r)', color: 'var(--text)',
    padding: '5px 8px', fontSize: 12.5,
    outline: 'none', fontFamily: 'inherit',
  },
  inlineRow: { display: 'flex', gap: 6 },
  btnSmall: {
    padding: '3px 9px', borderRadius: 'var(--r-sm)',
    border: '1px solid var(--border-strong)', background: 'var(--surface)',
    color: 'var(--text)', fontSize: 11.5, cursor: 'pointer', flexShrink: 0,
  },
  btnPrimary: {
    padding: '3px 10px', borderRadius: 'var(--r-sm)',
    border: '1px solid transparent', background: 'var(--accent)',
    color: 'var(--accent-contrast)', fontSize: 11.5, cursor: 'pointer', fontWeight: 600, flexShrink: 0,
  },
  btnIcon: {
    minWidth: 22, height: 22, padding: '0 5px', borderRadius: 'var(--r-sm)',
    border: '1px solid transparent', background: 'transparent',
    color: 'var(--muted)', fontSize: 12, cursor: 'pointer',
    lineHeight: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  },

  // Editor
  editorHeader: {
    padding: '0 12px 0 20px', height: 52, flexShrink: 0,
    borderBottom: '1px solid var(--border)',
    display: 'flex', alignItems: 'center', gap: 10,
  },
  dirtyDot: { width: 7, height: 7, borderRadius: '50%', background: 'var(--warning)', flexShrink: 0, boxShadow: '0 0 0 3px color-mix(in srgb, var(--warning) 20%, transparent)' },
  titleInput: {
    flex: 1, background: 'transparent', border: 'none',
    color: 'var(--text)', fontSize: 17, fontWeight: 700, letterSpacing: '-.01em',
    outline: 'none', fontFamily: 'inherit', boxShadow: 'none',
  },
  textarea: {
    flex: 1, background: 'transparent', border: 'none',
    color: 'var(--text)', fontSize: 16, lineHeight: 2,
    padding: '24px max(24px, calc((100% - 720px) / 2))', resize: 'none', outline: 'none',
    fontFamily: 'inherit', overflowY: 'auto', boxShadow: 'none',
  },
  editorFooter: {
    padding: '8px 12px 8px 20px', flexShrink: 0,
    borderTop: '1px solid var(--border)', background: 'var(--surface-2)',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
  },
  wordCount: { fontSize: 12, color: 'var(--muted)', fontFamily: 'var(--font-mono)' },

  // Analysis panel
  analysisPanel: {
    borderTop: '1px solid var(--border)',
    maxHeight: 260, overflowY: 'auto',
    padding: '14px 20px', flexShrink: 0, background: 'var(--surface-2)',
  },
  analysisTitle: { fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 8 },
  issue: { padding: '6px 10px', borderRadius: 'var(--r)', marginBottom: 5, fontSize: 12.5, lineHeight: 1.6 },
  issueSevere: { background: 'var(--tint-red-bg)', borderLeft: '3px solid var(--danger)' },
  issueWarn:   { background: 'var(--tint-amber-bg)', borderLeft: '3px solid var(--warning)' },
  rewriteItem: { marginBottom: 12 },
  rewriteMeta: { fontSize: 11, color: 'var(--muted)', marginBottom: 4 },
  rewriteGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12.5, lineHeight: 1.7 },
  rewriteOld:  { padding: '8px 10px', borderRadius: 'var(--r)', background: 'var(--tint-red-bg)',  color: 'var(--text-2)' },
  rewriteNew:  { padding: '8px 10px', borderRadius: 'var(--r)', background: 'var(--tint-green-bg)', color: 'var(--text)' },

  empty: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 13, padding: 16, textAlign: 'center' },

  // Preview mode
  previewWrap: { flex: 1, overflowY: 'auto', padding: '40px 48px' },
  previewTitle: { textAlign: 'center', fontSize: 22, fontWeight: 700, marginBottom: 40, color: 'var(--text)', lineHeight: 1.5, letterSpacing: '.02em' },
  previewContent: { maxWidth: 640, margin: '0 auto', fontSize: 17, lineHeight: 2.2, color: 'var(--text)' },
  previewPara: { textIndent: '2em', margin: '0 0 0.6em 0', padding: 0 },

  // Mode toggle
  modeToggle: { display: 'inline-flex', flexShrink: 0, border: '1px solid var(--border-strong)', borderRadius: 'var(--r)', overflow: 'hidden' },
  modeBtn: {
    padding: '4px 11px', fontSize: 12, cursor: 'pointer',
    border: 'none', background: 'var(--surface)', color: 'var(--text-2)',
  },
  modeBtnActive: { background: 'var(--accent-soft)', color: 'var(--accent)', fontWeight: 600 },

  // Page navigation bar
  pageNavBar: {
    padding: '7px 14px', flexShrink: 0,
    borderTop: '1px solid var(--border)',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
  },
  pageInfo: { flex: 1, textAlign: 'center', fontSize: 12, color: 'var(--muted)', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' },
  pageBtn: {
    padding: '4px 14px', borderRadius: 'var(--r)', fontSize: 12, cursor: 'pointer',
    border: '1px solid var(--border-strong)', background: 'var(--surface)', color: 'var(--text)',
    flexShrink: 0,
  },
  pageBtnDisabled: { opacity: 0.35, cursor: 'not-allowed' },
}

// ── Component ──────────────────────────────────────────────────────────────────

const RHYTHM_LABEL = { TOO_SHORT: '段落過短', TOO_LONG: '段落過長' }

async function _errText(r) {
  if (!r) return '連線失敗：後端沒有回應'
  try { const j = await r.json(); return j.detail || `HTTP ${r.status}` } catch { return `HTTP ${r.status}` }
}

export default function NovelTab() {
  // Projects
  const [projects,       setProjects]       = useState([])
  const [activeProject,  setActiveProject]  = useState(null)
  const [showNewProj,    setShowNewProj]     = useState(false)
  const [newProjTitle,   setNewProjTitle]    = useState('')
  const [newProjAuthor,  setNewProjAuthor]   = useState('')

  // Volumes (each has .chapters array)
  const [volumes,        setVolumes]         = useState([])
  const [showNewVol,     setShowNewVol]      = useState(false)
  const [newVolSubtitle, setNewVolSubtitle]  = useState('')
  // per-volume chapter form: volumeId -> input string
  const [chapForms,      setChapForms]       = useState({}) // { [volId]: string }

  // Editor
  const [activeChapter,  setActiveChapter]  = useState(null)
  const [editTitle,      setEditTitle]      = useState('')
  const [editContent,    setEditContent]    = useState('')
  const [isDirty,        setIsDirty]        = useState(false)
  const [saving,         setSaving]         = useState(false)

  // AI
  const [analysisResult, setAnalysisResult] = useState(null)
  const [rewriteResult,  setRewriteResult]  = useState(null)
  const [aiMode,         setAiMode]         = useState(null)
  const [aiLoading,      setAiLoading]      = useState(false)

  // Drag & drop
  const [dragItem,       setDragItem]       = useState(null)  // { type:'volume'|'chapter', id, volumeId? }
  const [dragOverId,     setDragOverId]     = useState(null)  // id of hovered target

  // View mode
  const [viewMode,       setViewMode]       = useState('edit') // 'edit' | 'preview'

  // Pagination (derived from volumes, recalculated each render)
  const allChapters = volumes.flatMap((v, vi) => v.chapters.map(ch => ({ ...ch, _vol: v, _volIdx: vi })))
  const currentPageIndex = activeChapter ? allChapters.findIndex(c => c.id === activeChapter.id) : -1
  const totalPages = allChapters.length

  // ── Load ────────────────────────────────────────────────────────────────────

  useEffect(() => {
    fetch(`${API}/projects/`)
      .then(r => r.ok ? r.json() : [])
      .then(setProjects)
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!activeProject) { setVolumes([]); return }
    fetch(`${API}/projects/${activeProject.id}/volumes`)
      .then(r => r.ok ? r.json() : [])
      .then(setVolumes)
      .catch(() => {})
  }, [activeProject])

  useEffect(() => {
    if (!activeChapter) { setEditTitle(''); setEditContent(''); setIsDirty(false); return }
    fetch(`${API}/chapters/${activeChapter.id}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return
        setEditTitle(data.title)
        setEditContent(data.content || '')
        setIsDirty(false)
      })
      .catch(() => {})
  }, [activeChapter])

  // Ctrl/Cmd + S
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        if (isDirty) saveChapter()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isDirty, editTitle, editContent, activeChapter])

  // ── Actions ─────────────────────────────────────────────────────────────────

  const selectProject = (proj) => {
    setActiveProject(proj)
    setActiveChapter(null)
    setAnalysisResult(null); setRewriteResult(null)
  }

  const createProject = async () => {
    if (!newProjTitle.trim()) return
    const r = await fetch(`${API}/projects/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newProjTitle.trim(), author: newProjAuthor.trim() || '作者' }),
    }).catch(() => null)
    if (!r?.ok) return
    const proj = await r.json()
    setProjects(prev => [proj, ...prev])
    setNewProjTitle(''); setNewProjAuthor(''); setShowNewProj(false)
    selectProject(proj)
  }

  const createVolume = async () => {
    if (!activeProject) return
    const r = await fetch(`${API}/projects/${activeProject.id}/volumes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subtitle: newVolSubtitle.trim() || null }),
    }).catch(() => null)
    if (!r?.ok) return
    const vol = await r.json()
    setVolumes(prev => [...prev, { ...vol, chapters: [] }])
    setNewVolSubtitle(''); setShowNewVol(false)
  }

  const deleteVolume = async (volId) => {
    if (!window.confirm('刪除此集數及其所有章節？')) return
    await fetch(`${API}/volumes/${volId}`, { method: 'DELETE' }).catch(() => {})
    setVolumes(prev => prev.filter(v => v.id !== volId))
    if (activeChapter && volumes.find(v => v.id === volId)?.chapters.some(c => c.id === activeChapter.id)) {
      setActiveChapter(null)
    }
  }

  const createChapter = async (volId) => {
    const title = (chapForms[volId] || '').trim()
    if (!title) return
    const r = await fetch(`${API}/volumes/${volId}/chapters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }).catch(() => null)
    if (!r?.ok) return
    const ch = await r.json()
    setVolumes(prev => prev.map(v =>
      v.id === volId ? { ...v, chapters: [...v.chapters, ch] } : v
    ))
    setChapForms(prev => ({ ...prev, [volId]: '' }))
    setActiveChapter(ch)
    setAnalysisResult(null); setRewriteResult(null)
  }

  const deleteChapter = async (ch) => {
    if (!window.confirm(`刪除「${ch.title}」？`)) return
    await fetch(`${API}/chapters/${ch.id}`, { method: 'DELETE' }).catch(() => {})
    setVolumes(prev => prev.map(v =>
      v.id === ch.volume_id ? { ...v, chapters: v.chapters.filter(c => c.id !== ch.id) } : v
    ))
    if (activeChapter?.id === ch.id) setActiveChapter(null)
  }

  const saveChapter = useCallback(async () => {
    if (!activeChapter) return
    setSaving(true)
    await fetch(`${API}/chapters/${activeChapter.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: editTitle, content: editContent }),
    }).catch(() => {})
    setIsDirty(false); setSaving(false)
    setVolumes(prev => prev.map(v => ({
      ...v,
      chapters: v.chapters.map(c => c.id === activeChapter.id ? { ...c, title: editTitle } : c),
    })))
  }, [activeChapter, editTitle, editContent])

  const turnPage = async (dir) => {
    if (isDirty) await saveChapter()
    const nextIdx = currentPageIndex + dir
    if (nextIdx < 0 || nextIdx >= allChapters.length) return
    setActiveChapter(allChapters[nextIdx])
    setAnalysisResult(null); setRewriteResult(null)
  }

  const runAnalyze = async () => {
    if (!activeChapter || aiLoading) return
    if (isDirty) await saveChapter()
    setAiLoading(true); setAiMode('analyze')
    setAnalysisResult(null); setRewriteResult(null)
    const r = await fetch(`${API}/chapters/${activeChapter.id}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'gentle' }),
    }).catch(() => null)
    setAiLoading(false)
    if (r?.ok) setAnalysisResult(await r.json())
    else setAnalysisResult({ rhythm: [], consistency: [], warnings: [await _errText(r)] })
  }

  const runRewrite = async () => {
    if (!activeChapter || aiLoading) return
    if (isDirty) await saveChapter()
    setAiLoading(true); setAiMode('rewrite')
    setAnalysisResult(null); setRewriteResult(null)
    const r = await fetch(`${API}/chapters/${activeChapter.id}/rewrite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'gentle' }),
    }).catch(() => null)
    setAiLoading(false)
    if (r?.ok) setRewriteResult(await r.json())
    else setRewriteResult({ suggestions: [], error: await _errText(r) })
  }

  // ── Drag & Drop ─────────────────────────────────────────────────────────────

  const onVolumeDragStart = (e, volId) => {
    e.stopPropagation()
    setDragItem({ type: 'volume', id: volId })
  }

  const onVolumeDrop = (e, targetVolId) => {
    e.preventDefault(); e.stopPropagation()
    setDragOverId(null)
    if (!dragItem || dragItem.type !== 'volume' || dragItem.id === targetVolId) { setDragItem(null); return }
    const from = volumes.findIndex(v => v.id === dragItem.id)
    const to   = volumes.findIndex(v => v.id === targetVolId)
    if (from === -1 || to === -1) { setDragItem(null); return }
    const next = [...volumes]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    setVolumes(next)
    const order = next.map((v, i) => ({ id: v.id, order_index: i }))
    fetch(`${API}/projects/${activeProject.id}/volumes/reorder`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(order),
    }).catch(() => {})
    setDragItem(null)
  }

  const onChapterDragStart = (e, ch) => {
    e.stopPropagation()
    setDragItem({ type: 'chapter', id: ch.id, volumeId: ch.volume_id })
  }

  const onChapterDrop = (e, targetCh) => {
    e.preventDefault(); e.stopPropagation()
    setDragOverId(null)
    if (!dragItem || dragItem.type !== 'chapter') { setDragItem(null); return }
    if (dragItem.volumeId !== targetCh.volume_id || dragItem.id === targetCh.id) { setDragItem(null); return }
    const vol = volumes.find(v => v.id === targetCh.volume_id)
    if (!vol) { setDragItem(null); return }
    const chs = [...vol.chapters]
    const from = chs.findIndex(c => c.id === dragItem.id)
    const to   = chs.findIndex(c => c.id === targetCh.id)
    if (from === -1 || to === -1) { setDragItem(null); return }
    const [moved] = chs.splice(from, 1)
    chs.splice(to, 0, moved)
    setVolumes(prev => prev.map(v => v.id === vol.id ? { ...v, chapters: chs } : v))
    const order = chs.map((c, i) => ({ id: c.id, order_index: i }))
    fetch(`${API}/volumes/${vol.id}/chapters/reorder`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(order),
    }).catch(() => {})
    setDragItem(null)
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  const volNumber = (i) => `第 ${i + 1} 集`
  const wordCount = editContent.replace(/\s/g, '').length
  const hasPanel  = (analysisResult || rewriteResult) && !aiLoading

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div style={S.root}>

      {/* ── Column A: 作品 ── */}
      <div style={S.sideA}>
        <div style={S.panelHeader}>
          <span>作品</span>
          <button style={S.btnSmall} onClick={() => setShowNewProj(v => !v)}>+</button>
        </div>

        {showNewProj && (
          <div style={S.inlineForm}>
            <input
              style={S.inlineInput} placeholder="書名" autoFocus
              value={newProjTitle} onChange={e => setNewProjTitle(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && createProject()}
            />
            <input
              style={S.inlineInput} placeholder="作者（選填）"
              value={newProjAuthor} onChange={e => setNewProjAuthor(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && createProject()}
            />
            <button style={S.btnPrimary} onClick={createProject}>建立</button>
          </div>
        )}

        <div style={S.listScroll}>
          {projects.length === 0 && (
            <div style={{ padding: '16px 12px', fontSize: 12, color: 'var(--muted)' }}>尚無作品</div>
          )}
          {projects.map(p => (
            <div
              key={p.id}
              style={{ ...S.projItem, ...(activeProject?.id === p.id ? S.projItemActive : {}) }}
              onClick={() => selectProject(p)}
            >
              <div>{p.title}</div>
              <div style={S.projSub}>{p.author}{p.genre ? ` · ${p.genre}` : ''}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Column B: 集數 + 章節 ── */}
      <div style={S.sideB}>
        <div style={S.panelHeader}>
          <span>集數 / 章節{activeProject ? ` (${volumes.length})` : ''}</span>
          {activeProject && (
            <button style={S.btnSmall} onClick={() => setShowNewVol(v => !v)}>+ 集</button>
          )}
        </div>

        {showNewVol && (
          <div style={S.inlineForm}>
            <div style={S.inlineRow}>
              <input
                style={{ ...S.inlineInput, flex: 1 }}
                placeholder="副標題（選填）" autoFocus
                value={newVolSubtitle} onChange={e => setNewVolSubtitle(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && createVolume()}
              />
              <button style={S.btnPrimary} onClick={createVolume}>+</button>
            </div>
          </div>
        )}

        <div style={S.listScroll}>
          {!activeProject && (
            <div style={{ padding: '16px 12px', fontSize: 12, color: 'var(--muted)' }}>← 先選作品</div>
          )}
          {activeProject && volumes.length === 0 && (
            <div style={{ padding: '16px 12px', fontSize: 12, color: 'var(--muted)' }}>尚無集數，點「+ 集」新增</div>
          )}

          {volumes.map((vol, vi) => (
            <div
              key={vol.id}
              style={{ ...S.volBlock, ...(dragOverId === vol.id ? S.dragOver : {}) }}
              draggable
              onDragStart={e => onVolumeDragStart(e, vol.id)}
              onDragOver={e => { e.preventDefault(); setDragOverId(vol.id) }}
              onDragLeave={() => setDragOverId(null)}
              onDrop={e => onVolumeDrop(e, vol.id)}
            >
              {/* Volume header */}
              <div style={S.volHeader}>
                <DragHandle />
                <span style={S.volLabel}>
                  {volNumber(vi)}{vol.subtitle ? ` · ${vol.subtitle}` : ''}
                </span>
                <div style={S.volActions}>
                  <button
                    style={S.btnIcon}
                    title="新增章節"
                    onClick={() => setChapForms(prev => ({ ...prev, [vol.id]: prev[vol.id] != null ? undefined : '' }))}
                  >+章</button>
                  <button
                    style={{ ...S.btnIcon, color: 'var(--danger)' }}
                    title="刪除集數"
                    onClick={() => deleteVolume(vol.id)}
                  >✕</button>
                </div>
              </div>

              {/* New chapter form for this volume */}
              {chapForms[vol.id] != null && (
                <div style={{ padding: '5px 10px 5px 28px', display: 'flex', gap: 5 }}>
                  <input
                    style={{ ...S.inlineInput, flex: 1 }}
                    placeholder="章節標題" autoFocus
                    value={chapForms[vol.id]}
                    onChange={e => setChapForms(prev => ({ ...prev, [vol.id]: e.target.value }))}
                    onKeyDown={e => { if (e.key === 'Enter') createChapter(vol.id); if (e.key === 'Escape') setChapForms(prev => ({ ...prev, [vol.id]: undefined })) }}
                  />
                  <button style={S.btnPrimary} onClick={() => createChapter(vol.id)}>+</button>
                </div>
              )}

              {/* Chapters */}
              {vol.chapters.map(ch => (
                <div
                  key={ch.id}
                  style={{
                    ...S.chapItem,
                    ...(activeChapter?.id === ch.id ? S.chapItemActive : {}),
                    ...(dragOverId === ch.id ? S.dragOver : {}),
                  }}
                  onClick={() => { setActiveChapter(ch); setAnalysisResult(null); setRewriteResult(null) }}
                  draggable
                  onDragStart={e => onChapterDragStart(e, ch)}
                  onDrop={e => onChapterDrop(e, ch)}
                  onDragOver={e => { e.preventDefault(); setDragOverId(ch.id) }}
                  onDragLeave={() => setDragOverId(null)}
                >
                  <DragHandle style={{ opacity: 0.4 }} />
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {ch.title}
                  </span>
                  <button
                    style={{ ...S.btnIcon, opacity: 0, pointerEvents: 'none' }}
                    className="chap-del"
                    onClick={e => { e.stopPropagation(); deleteChapter(ch) }}
                    title="刪除"
                  >✕</button>
                </div>
              ))}
              {vol.chapters.length === 0 && (
                <div style={{ padding: '4px 10px 6px 26px', fontSize: 11.5, color: 'var(--faint)' }}>（無章節）</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Column C: Editor ── */}
      <div style={S.main}>
        {!activeChapter ? (
          <div style={S.empty}>
            <Empty icon="book-open-text" title={!activeProject ? '選擇或建立作品' : volumes.length === 0 ? '先新增集數' : '選擇章節開始寫作'} style={{ background: 'transparent', border: 'none' }}>
              {!activeProject ? '從左側清單挑一部作品，或按「+」建立新作品' : volumes.length === 0 ? '在中間欄按「+ 集」建立第一集' : '從中間欄點選章節，內容會在這裡編輯'}
            </Empty>
          </div>
        ) : (
          <>
            <div style={S.editorHeader}>
              {isDirty && <span style={S.dirtyDot} title="有未儲存的變更" />}
              <input
                style={S.titleInput}
                value={editTitle}
                onChange={e => { setEditTitle(e.target.value); setIsDirty(true) }}
                placeholder="章節標題"
                readOnly={viewMode === 'preview'}
              />
              <div style={S.modeToggle}>
                <button
                  style={{ ...S.modeBtn, ...(viewMode === 'edit' ? S.modeBtnActive : {}) }}
                  onClick={() => setViewMode('edit')}
                  title="編輯模式"
                >✎ 編輯</button>
                <button
                  style={{ ...S.modeBtn, ...(viewMode === 'preview' ? S.modeBtnActive : {}) }}
                  onClick={() => setViewMode('preview')}
                  title="閱讀預覽"
                >📖 預覽</button>
              </div>
            </div>

            {viewMode === 'edit' ? (
              <textarea
                style={S.textarea}
                value={editContent}
                onChange={e => { setEditContent(e.target.value); setIsDirty(true) }}
                placeholder="開始寫作…"
              />
            ) : (
              <div style={S.previewWrap}>
                <div style={S.previewContent}>
                  <p style={S.previewTitle}>{editTitle}</p>
                  {editContent.split('\n').map((line, i) =>
                    line.trim()
                      ? <p key={i} style={S.previewPara}>{line}</p>
                      : <div key={i} style={{ height: '0.7em' }} />
                  )}
                  {!editContent && (
                    <div style={{ textAlign: 'center', color: 'var(--muted)', fontSize: 14 }}>（尚無內容）</div>
                  )}
                </div>
              </div>
            )}

            {/* AI results */}
            {hasPanel && (
              <div style={S.analysisPanel}>
                {aiMode === 'analyze' && analysisResult && (
                  <>
                    <div style={S.analysisTitle}>節奏分析 — {analysisResult.rhythm_summary}</div>
                    {(analysisResult.rhythm ?? []).filter(p => p.status !== 'NORMAL').map(p => (
                      <div key={p.index} style={{ ...S.issue, ...S.issueWarn }}>
                        <strong>第 {p.index} 段</strong>（{p.char_count} 字）：{RHYTHM_LABEL[p.status] ?? p.status}
                        <div style={{ marginTop: 2, color: 'var(--muted)' }}>「{p.preview}」</div>
                      </div>
                    ))}
                    {(() => {
                      const issues = (analysisResult.consistency ?? []).flatMap(pc => pc.issues)
                      return issues.length > 0 ? (
                        <div style={{ marginTop: 8 }}>
                          <div style={S.analysisTitle}>角色一致性</div>
                          {issues.map((iss, i) => (
                            <div key={i} style={{ ...S.issue, ...(iss.severity === 'high' ? S.issueSevere : S.issueWarn) }}>
                              <strong>{iss.target}</strong>：{iss.description}
                              {iss.evidence && <div style={{ marginTop: 2, color: 'var(--muted)' }}>「{iss.evidence}」</div>}
                            </div>
                          ))}
                        </div>
                      ) : <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>未偵測到角色一致性問題</div>
                    })()}
                    {(analysisResult.warnings ?? []).map((w, i) => (
                      <div key={i} style={{ ...S.issue, ...S.issueWarn, marginTop: 4 }}>{w}</div>
                    ))}
                  </>
                )}

                {aiMode === 'rewrite' && rewriteResult && (
                  <>
                    <div style={S.analysisTitle}>改寫建議 — {rewriteResult.suggestions?.length ?? 0} 處</div>
                    {rewriteResult.message && <div style={{ fontSize: 12, color: 'var(--muted)' }}>{rewriteResult.message}</div>}
                    {rewriteResult.error && <div style={{ ...S.issue, ...S.issueSevere }}>{rewriteResult.error}</div>}
                    {(rewriteResult.suggestions ?? []).map((s, i) => (
                      <div key={i} style={S.rewriteItem}>
                        <div style={S.rewriteMeta}>第 {s.paragraph_index} 段 · {s.reason}</div>
                        <div style={S.rewriteGrid}>
                          <div style={S.rewriteOld}>{s.original}</div>
                          {s.error
                            ? <div style={{ ...S.rewriteNew, ...S.issueSevere }}>改寫失敗：{s.error}</div>
                            : <div style={S.rewriteNew}>{s.suggestion}</div>}
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}

            {/* Page navigation */}
            <div style={S.pageNavBar}>
              <button
                style={{ ...S.pageBtn, ...(currentPageIndex <= 0 ? S.pageBtnDisabled : {}) }}
                onClick={() => turnPage(-1)}
                disabled={currentPageIndex <= 0}
              >← 上一頁</button>
              <div style={S.pageInfo}>
                {currentPageIndex >= 0 && allChapters[currentPageIndex] ? (() => {
                  const meta = allChapters[currentPageIndex]
                  const volName = meta._vol.subtitle || `第 ${meta._volIdx + 1} 集`
                  return `${volName} · ${editTitle || '未命名'}  (${currentPageIndex + 1} / ${totalPages})`
                })() : '—'}
              </div>
              <button
                style={{ ...S.pageBtn, ...(currentPageIndex >= totalPages - 1 ? S.pageBtnDisabled : {}) }}
                onClick={() => turnPage(1)}
                disabled={currentPageIndex >= totalPages - 1}
              >下一頁 →</button>
            </div>

            <div style={S.editorFooter}>
              <div style={S.wordCount}>{wordCount.toLocaleString()} 字</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  style={{ ...S.btnSmall, opacity: (aiLoading || !editContent) ? 0.45 : 1 }}
                  onClick={runAnalyze} disabled={aiLoading || !editContent}
                  title="節奏 + 角色一致性分析"
                >{aiLoading && aiMode === 'analyze' ? '分析中…' : '分析'}</button>
                <button
                  style={{ ...S.btnSmall, opacity: (aiLoading || !editContent) ? 0.45 : 1 }}
                  onClick={runRewrite} disabled={aiLoading || !editContent}
                >{aiLoading && aiMode === 'rewrite' ? '分析中…' : '改寫建議'}</button>
                <button
                  style={{ ...S.btnPrimary, opacity: (!isDirty || saving) ? 0.45 : 1 }}
                  onClick={saveChapter} disabled={!isDirty || saving}
                  title="Ctrl+S"
                >{saving ? '儲存中…' : '儲存'}</button>
              </div>
            </div>
          </>
        )}
      </div>

      <style>{`
        .chap-del { opacity: 0 !important; pointer-events: none !important; }
        div:hover > .chap-del { opacity: 0.5 !important; pointer-events: auto !important; }
      `}</style>
    </div>
  )
}
