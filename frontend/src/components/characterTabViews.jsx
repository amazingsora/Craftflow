// Craftflow CharacterTab 導覽 View（2026-06-13 A2 增量3a：自 CharacterTab.jsx 抽出，零行為變更）
// 含 ProjectsView / ProjectCreateView / CharacterListView / FactionView / CharacterCreateView

import { useState, useEffect, useRef } from 'react'
import { request, apiDelete, apiUrl } from '../api/client'
import { S } from './characterTabStyles.js'
import { Spinner, StatusBadge, GenderPicker, DeleteConfirm } from './characterTabParts.jsx'
import { GENRES, STATUSES, apiFetch } from './characterTabShared.js'


export function ProjectsView({ onSelect, onCreateClick, onEdit }) {
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


export function ProjectCreateView({ onBack, onCreate }) {
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


export function CharacterListView({ project: initProject, onSelectChar, onCreateChar, onBackToProjects, autoEdit = false, onSelectFaction }) {
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
        <div style={{ ...S.form, maxWidth: 480, background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, padding: 16 }}>
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


export function FactionView({ faction: initFaction, project, allChars, onBack, onSelectChar }) {
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
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, padding: 14 }}>
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


export function CharacterCreateView({ project, onBack, onCreate }) {
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
