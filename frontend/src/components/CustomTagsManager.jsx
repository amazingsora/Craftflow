// [CN-131] Tag 管理：客製化標籤清單（作品／繪師）的手動維護、Danbooru 字典搜尋、檔案匯入／匯出
import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPostForm, request } from '../api/client.js'
import { UI } from './sharedStyles'
import { Segmented } from './ui.jsx'

export const CUSTOM_TAGS_CHANGED = 'craftflow:custom-tags-changed'

const KINDS = [
  { key: 'series', label: '作品' },
  { key: 'artists', label: '繪師' },
]
const SEARCH_DEBOUNCE_MS = 250
const _bare = t => (t || '').replace(/^@/, '').replace(/\\/g, '').trim().toLowerCase()

const S = {
  row: { display: 'flex', alignItems: 'center', gap: 8 },
  list: {
    display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 220, overflowY: 'auto',
    padding: 4, borderRadius: 'var(--r)', border: '1px solid var(--border)', background: 'var(--surface-2)',
  },
  item: { display: 'flex', alignItems: 'center', gap: 8, padding: '2px 4px' },
  labelInput: { ...UI.input, fontSize: 12.5, padding: '4px 8px', flex: '0 0 40%' },
  tag: { ...UI.mono, fontSize: 12, color: 'var(--text-2)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  count: { ...UI.mono, fontSize: 11.5, color: 'var(--muted)', minWidth: 64, textAlign: 'right' },
  input: { ...UI.input, fontSize: 12.5, padding: '5px 8px' },
  hint: { ...UI.hint, fontSize: 11.5 },
  subTitle: { fontSize: 12, fontWeight: 500, color: 'var(--text-2)' },
  msg: ok => ({ fontSize: 12, color: ok ? 'var(--success)' : 'var(--danger)' }),
}

const putTags = body => request('/art/custom-tags', {
  method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
}).then(r => r.json())

export function CustomTagsManager() {
  const [tags, setTags] = useState({ series: [], artists: [] })
  const [kind, setKind] = useState('series')
  const [draft, setDraft] = useState({ label: '', tag: '' })
  const [query, setQuery] = useState('')
  const [dict, setDict] = useState({ configured: null, size: 0, results: [] })
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)
  const savedRef = useRef('')

  const applySaved = data => { savedRef.current = JSON.stringify(data); setTags(data) }

  useEffect(() => { apiGet('/art/custom-tags').then(applySaved).catch(e => setMsg({ ok: false, text: e.message })) }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      apiGet(`/art/tag-dictionary/search?kind=${kind}&q=${encodeURIComponent(query.trim())}`)
        .then(setDict).catch(e => setMsg({ ok: false, text: e.message }))
    }, query.trim() ? SEARCH_DEBOUNCE_MS : 0)
    return () => clearTimeout(timer)
  }, [query, kind])

  const commit = async (next, okText) => {
    setBusy(true)
    try {
      applySaved(await putTags(next))
      window.dispatchEvent(new Event(CUSTOM_TAGS_CHANGED))
      if (okText) setMsg({ ok: true, text: okText })
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    } finally {
      setBusy(false)
    }
  }

  const list = tags[kind] || []
  const kindLabel = KINDS.find(k => k.key === kind).label
  const inList = tag => list.some(e => _bare(e.tag) === _bare(tag))

  const addEntry = (label, tag) => {
    if (!tag.trim()) return
    if (inList(tag)) { setMsg({ ok: false, text: `「${tag}」已在${kindLabel}清單` }); return }
    commit({ ...tags, [kind]: [...list, { label: label.trim(), tag: tag.trim() }] }, `已加入${kindLabel}：${label.trim() || tag.trim()}`)
  }
  const removeEntry = idx => commit({ ...tags, [kind]: list.filter((_, i) => i !== idx) })
  const editLabel = (idx, label) => setTags({ ...tags, [kind]: list.map((e, i) => (i === idx ? { ...e, label } : e)) })

  const onImport = async e => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    setBusy(true)
    try {
      const res = await apiPostForm('/art/custom-tags/import', form).then(r => r.json())
      applySaved(res.tags)
      window.dispatchEvent(new Event(CUSTOM_TAGS_CHANGED))
      setMsg({ ok: true, text: `匯入 ${file.name}：新增 ${res.added}、重複略過 ${res.duplicate}、無效 ${res.invalid}` })
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const onExport = () => {
    const blob = new Blob([JSON.stringify(tags, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'custom_tags.json'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <>
      <div style={{ ...S.row, justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <Segmented size="sm" value={kind} onChange={setKind}
          options={KINDS.map(k => ({ key: k.key, label: `${k.label}（${tags[k.key]?.length || 0}）` }))} />
        <div style={S.row}>
          <input ref={fileRef} type="file" accept=".json,.csv" style={{ display: 'none' }} onChange={onImport} />
          <button style={UI.btnSm} disabled={busy} onClick={() => fileRef.current?.click()}
            title="custom_tags 格式 JSON，或 Danbooru 標籤 CSV（只收作品／繪師）；與現有清單合併">匯入檔案</button>
          <button style={UI.btnSm} disabled={busy} onClick={onExport} title="下載目前清單（備份或搬到另一台）">匯出 JSON</button>
        </div>
      </div>

      <div style={S.list}>
        {list.length === 0 && <div style={{ ...S.hint, padding: '6px 4px' }}>尚無{kindLabel}。手動新增、從下方字典搜尋，或匯入檔案。</div>}
        {list.map((e, i) => (
          <div key={e.tag} style={S.item}>
            <input style={S.labelInput} value={e.label} aria-label="顯示名稱"
              onChange={ev => editLabel(i, ev.target.value)}
              onBlur={() => { if (JSON.stringify(tags) !== savedRef.current) commit(tags) }} />
            <span style={S.tag} title={e.tag}>{e.tag}</span>
            <button style={UI.btnGhost} disabled={busy} aria-label={`刪除 ${e.tag}`} onClick={() => removeEntry(i)}>×</button>
          </div>
        ))}
      </div>

      <div>
        <div style={{ ...S.subTitle, marginBottom: 6 }}>手動新增{kindLabel}</div>
        <div style={S.row}>
          <input style={{ ...S.input, flex: '0 0 36%' }} placeholder="顯示名稱（可留空）" value={draft.label}
            onChange={e => setDraft({ ...draft, label: e.target.value })} />
          <input style={{ ...S.input, flex: 1, ...UI.mono }} placeholder="tag，例：artist_name" value={draft.tag}
            onChange={e => setDraft({ ...draft, tag: e.target.value })}
            onKeyDown={e => { if (e.key === 'Enter') { addEntry(draft.label, draft.tag); setDraft({ label: '', tag: '' }) } }} />
          <button style={UI.btnSm} disabled={busy || !draft.tag.trim()}
            onClick={() => { addEntry(draft.label, draft.tag); setDraft({ label: '', tag: '' }) }}>新增</button>
        </div>
      </div>

      <div>
        <div style={{ ...S.subTitle, marginBottom: 6 }}>從 Danbooru 字典搜尋{kindLabel}</div>
        {dict.configured === false ? (
          <div style={S.hint}>未設定字典：在 .env 設 <code>TAG_DICTIONARY_CSV</code> 後重啟後端（範例見 .env.example）。</div>
        ) : (
          <>
            <input style={S.input} placeholder={`英文 tag 或別名，例：${kind === 'series' ? 'fate (series)' : 'artist name'}`}
              value={query} onChange={e => setQuery(e.target.value)} />
            {query.trim() && (
              <div style={{ ...S.list, marginTop: 6 }}>
                {dict.results.length === 0 && <div style={{ ...S.hint, padding: '6px 4px' }}>查無結果</div>}
                {dict.results.map(r => {
                  const added = inList(r.tag)
                  return (
                    <div key={r.name} style={S.item} title={r.aliases.length ? `別名：${r.aliases.join(', ')}` : r.name}>
                      <span style={S.tag}>{r.tag}</span>
                      <span style={S.count}>{r.count.toLocaleString()}</span>
                      <button style={UI.btnSm} disabled={busy || added} onClick={() => addEntry('', r.tag)}>
                        {added ? '已加入' : '加入'}
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
            <div style={{ ...S.hint, marginTop: 4 }}>
              字典 {dict.size.toLocaleString()} 筆；右側數字＝Danbooru 投稿數，太少的繪師模型可能學不起來。
            </div>
          </>
        )}
      </div>

      {msg && <div style={S.msg(msg.ok)}>{msg.text}</div>}
      <div style={S.hint}>清單只存本機 data/custom_tags.json（不進 git）。tag 存檔時自動轉成 prompt 寫法（底線→空白、括號跳脫）；繪師不用加 @，Anima 生圖時自動補。</div>
    </>
  )
}
