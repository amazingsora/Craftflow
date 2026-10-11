// 客製化標籤（作品／繪師）：清單來自本機 data/custom_tags.json（GET /art/custom-tags）；已選標籤以卡片顯示，× 移除
import { useState } from 'react'
import { S } from './characterTabStyles.js'

const _GROUPS = [
  { key: 'series', placeholder: '＋ 作品', kindLabel: '作品' },
  { key: 'artists', placeholder: '＋ 繪師', kindLabel: '繪師' },
]

const _bare = t => t.replace(/^@/, '').trim().toLowerCase()
const _split = text => (text || '').split(',').map(t => t.trim()).filter(Boolean)

const chipStyle = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 4px 3px 10px',
  borderRadius: 14, fontSize: 12, background: 'var(--tint-blue-bg)', color: 'var(--tint-blue-fg)',
  border: '1px solid var(--tint-blue-border)', whiteSpace: 'nowrap',
}
const chipXStyle = {
  border: 'none', background: 'transparent', color: 'inherit', cursor: 'pointer',
  fontSize: 14, lineHeight: 1, padding: '0 4px', borderRadius: 10,
}

export function CustomTagsField({ value, onChange, options }) {
  const [draft, setDraft] = useState('')
  const tags = _split(value)
  const lookup = {}
  _GROUPS.forEach(g => (options?.[g.key] || []).forEach(o => { lookup[_bare(o.tag)] = { ...o, kind: g.kindLabel } }))

  const add = tag => {
    const t = (tag || '').trim()
    if (!t || tags.some(x => _bare(x) === _bare(t))) return
    onChange([...tags, t].join(', '))
  }
  const remove = idx => onChange(tags.filter((_, i) => i !== idx).join(', '))
  const commitDraft = () => { _split(draft).forEach(add); setDraft('') }
  const empty = !(options?.series?.length || options?.artists?.length)

  return (
    <div>
      <label style={S.label}><span title="會影響生圖" style={S.genMark} />客製化標籤</label>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        {_GROUPS.map(g => (
          <select key={g.key} style={{ ...S.select, flex: 1 }} value="" disabled={!options?.[g.key]?.length}
            onChange={e => add(e.target.value)}>
            <option value="">{g.placeholder}</option>
            {(options?.[g.key] || []).map(o => (
              <option key={o.tag} value={o.tag} disabled={tags.some(x => _bare(x) === _bare(o.tag))}>
                {o.label === o.tag ? o.tag : `${o.label}（${o.tag}）`}
              </option>
            ))}
          </select>
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
        {tags.map((t, i) => {
          const hit = lookup[_bare(t)]
          return (
            <span key={`${t}-${i}`} style={chipStyle} title={hit ? `${hit.kind}：${hit.tag}` : t}>
              {hit ? `${hit.kind}・${hit.label}` : t}
              <button type="button" style={chipXStyle} aria-label={`移除 ${t}`} onClick={() => remove(i)}>×</button>
            </span>
          )
        })}
        <input
          style={{ ...S.input, flex: 1, minWidth: 160, fontSize: 12, padding: '4px 8px' }}
          value={draft}
          placeholder={tags.length ? '輸入其他 tag，Enter 加入' : '未選擇；可從上方選單加入，或輸入 tag 後按 Enter'}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); commitDraft() } }}
          onBlur={commitDraft}
        />
      </div>
      <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>
        {empty
          ? '清單為空：到「設定 → 客製化標籤」新增、搜尋字典或匯入檔案'
          : '接在畫風段後送入 prompt；Anima 家族的繪師自動補 @。清單只存本機 JSON，選擇存在瀏覽器'}
      </p>
    </div>
  )
}
