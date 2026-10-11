import { useState, useEffect, useRef } from 'react'
import { notifyDone } from '../notify.js'
import { FitImage } from './ImageViewer'
import { UI } from './sharedStyles'
import { Icon } from './Icon.jsx'
import { Empty } from './ui.jsx'

// 與後端 PromptStyle enum 同步（styles.py）
const BASE_STYLES = ['sdxl', 'pony', 'flux', 'noobai', 'illustrious', 'anythingxl', 'anima']

const S = {
  root: { display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 980 },
  toolbar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  title: { fontSize: 22, fontWeight: 700, color: 'var(--text)', letterSpacing: '-.02em' },
  btn: { ...UI.btnPrimary, padding: '8px 14px', fontSize: 13 },
  btnSecondary: UI.btnSecondary,
  btnDanger: { ...UI.btnSecondary, color: 'var(--danger)' },
  btnIcon: { ...UI.btnIcon, color: 'var(--muted)', flexShrink: 0 },
  list: { ...UI.panel, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  card: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16,
    padding: '14px 16px', borderTop: '1px solid var(--border)', background: 'var(--surface)',
    cursor: 'pointer', transition: 'background .12s',
  },
  cardName: { fontSize: 14, fontWeight: 600, color: 'var(--text)' },
  cardMeta: { fontSize: 12.5, color: 'var(--muted)', marginTop: 2 },
  badge: {
    fontFamily: 'var(--font-mono)', fontSize: 11, borderRadius: 3, padding: '1px 6px',
    background: 'var(--surface-2)', color: 'var(--text-2)', border: '1px solid var(--border)',
  },
  empty: { color: 'var(--muted)', fontSize: 13, padding: '20px 0' },
  form: { ...UI.panel, display: 'flex', flexDirection: 'column', gap: 18, padding: 20 },
  row: { display: 'flex', gap: 14 },
  field: { display: 'flex', flexDirection: 'column', gap: 6, flex: 1, minWidth: 0 },
  label: { fontSize: 12, fontWeight: 500, color: 'var(--text-2)' },
  labelHint: { fontSize: 11.5, color: 'var(--faint)', fontWeight: 400, marginLeft: 8 },
  input: UI.input,
  textarea: { ...UI.textarea, fontFamily: 'var(--font-mono)', fontSize: 13, minHeight: 0 },
  select: UI.select,
  sectionTitle: { fontSize: 12, fontWeight: 600, color: 'var(--text-2)' },
  loraList: { display: 'flex', flexDirection: 'column', gap: 8 },
  loraRow: { display: 'flex', gap: 8, alignItems: 'center' },
  loraModel: { ...UI.select, flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12.5 },
  loraWeight: { ...UI.input, width: 76, textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 13 },
  formActions: { display: 'flex', gap: 10, paddingTop: 4 },
  divider: { height: 1, background: 'var(--border)', margin: '0 -20px' },
  spinner: {
    width: 16, height: 16, border: '2px solid currentColor', borderTopColor: 'transparent',
    borderRadius: '50%', animation: 'spin 0.8s linear infinite', display: 'inline-block',
  },
  spinnerLg: UI.spinner,
  testSection: { display: 'flex', flexDirection: 'column', gap: 12 },
  testTitle: { fontSize: 13, fontWeight: 600, color: 'var(--text)' },
  testImg: { width: '100%', borderRadius: 'var(--r)', border: '1px solid var(--border)', display: 'block' },
  testPlaceholder: {
    minHeight: 200, display: 'flex', alignItems: 'center', justifyContent: 'center',
    border: '1px dashed var(--border-strong)', borderRadius: 'var(--r-lg)', color: 'var(--muted)', fontSize: 13,
    background: 'var(--surface-2)',
  },
  testMeta: { fontSize: 11.5, color: 'var(--muted)', wordBreak: 'break-all', fontFamily: 'var(--font-mono)' },
}

const emptyStyle = {
  name: '', description: '', base_style: 'sdxl',
  quality_prefix: '', negative: '', extra_tags: '', loras: [],
}

export default function ArtStyleTab() {
  const [view, setView]       = useState('list')  // 'list' | 'edit'
  const [styles, setStyles]   = useState([])
  const [editing, setEditing] = useState(null)    // null = new, object = existing
  const [form, setForm]       = useState(emptyStyle)
  const [saving, setSaving]   = useState(false)
  const [error, setError]     = useState('')
  const [loraList, setLoraList] = useState([])    // available LoRAs from ComfyUI
  const [testPrompt, setTestPrompt] = useState('')
  const [testGenerating, setTestGenerating] = useState(false)
  const [testResult, setTestResult] = useState(null)  // { image: url, prompt, style, seed }
  const [testError, setTestError] = useState('')
  const testImgRef = useRef(null)

  useEffect(() => { loadStyles(); loadLoras() }, [])

  async function loadLoras() {
    try {
      const res = await fetch('/api/v1/settings/loras')
      if (res.ok) {
        const data = await res.json()
        setLoraList(data.loras ?? [])
      }
    } catch {}
  }

  async function loadStyles() {
    try {
      const res = await fetch('/api/v1/art-styles')
      if (res.ok) setStyles(await res.json())
    } catch {}
  }

  function openNew() {
    setEditing(null)
    setForm(emptyStyle)
    setError('')
    setView('edit')
  }

  function openEdit(s) {
    setEditing(s)
    setForm({
      name: s.name,
      description: s.description ?? '',
      base_style: s.base_style,
      quality_prefix: s.quality_prefix ?? '',
      negative: s.negative ?? '',
      extra_tags: s.extra_tags ?? '',
      loras: (s.loras ?? []).map(l => ({ ...l })),
    })
    setError('')
    setView('edit')
  }

  function setField(k, v) { setForm(f => ({ ...f, [k]: v })) }

  // ── LoRA helpers ──────────────────────────────────────────────────────────

  function addLora() {
    setForm(f => ({ ...f, loras: [...f.loras, { model: '', weight: 0.8 }] }))
  }

  function setLora(idx, key, val) {
    setForm(f => {
      const loras = f.loras.map((l, i) => i === idx ? { ...l, [key]: val } : l)
      return { ...f, loras }
    })
  }

  function removeLora(idx) {
    setForm(f => ({ ...f, loras: f.loras.filter((_, i) => i !== idx) }))
  }

  // ── Test Generation ───────────────────────────────────────────────────────

  async function testGenerate() {
    if (!testPrompt.trim()) { setTestError('請輸入測試描述'); return }
    if (!editing) return
    setTestGenerating(true); setTestError(''); setTestResult(null)
    try {
      const compileRes = await fetch('/api/v1/art/compile-prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: testPrompt, art_style_id: editing.id }),
      })
      if (!compileRes.ok) {
        const d = await compileRes.json().catch(() => ({}))
        throw new Error(d.detail ?? `編譯失敗 (${compileRes.status})`)
      }
      const compiled = await compileRes.json()

      const genRes = await fetch('/api/v1/art/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: compiled.positive,
          negative_prompt: compiled.negative ?? '',
          art_style_id: editing.id,
        }),
      })
      if (!genRes.ok) {
        const d = await genRes.json().catch(() => ({}))
        throw new Error(d.detail ?? `生成失敗 (${genRes.status})`)
      }
      const seed = genRes.headers.get('X-Seed') ?? '?'
      const style = genRes.headers.get('X-Style') ?? compiled.style
      const blob = await genRes.blob()
      const url = URL.createObjectURL(blob)
      setTestResult({ url, prompt: compiled.positive, negative: compiled.negative ?? '', style, seed })
      notifyDone('生成完成', '畫風測試圖')
      setTimeout(() => testImgRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50)
    } catch (e) {
      setTestError(e.message)
    } finally {
      setTestGenerating(false)
    }
  }

  // ── Save / Delete ─────────────────────────────────────────────────────────

  async function save() {
    if (!form.name.trim()) { setError('請輸入畫風名稱'); return }
    setSaving(true); setError('')
    const body = {
      ...form,
      loras: form.loras.filter(l => l.model.trim()),
    }
    try {
      const url    = editing ? `/api/v1/art-styles/${editing.id}` : '/api/v1/art-styles'
      const method = editing ? 'PUT' : 'POST'
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        setError(d.detail ?? `儲存失敗 (${res.status})`)
      } else {
        await loadStyles()
        setView('list')
      }
    } catch (e) {
      setError(`網路錯誤：${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  async function deleteStyle() {
    if (!editing) return
    if (!confirm(`確定刪除「${editing.name}」？`)) return
    try {
      await fetch(`/api/v1/art-styles/${editing.id}`, { method: 'DELETE' })
      await loadStyles()
      setView('list')
    } catch {}
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (view === 'list') {
    return (
      <div style={S.root}>
        <div style={S.toolbar}>
          <div>
            <h1 style={S.title}>畫風管理</h1>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 2 }}>可重用的 prompt 配方：基底 Style、品質前綴、負向與 LoRA</p>
          </div>
          <button style={S.btn} onClick={openNew}><Icon name="plus" size={14} />新增畫風</button>
        </div>
        {styles.length === 0
          ? <Empty icon="palette" title="尚無畫風">點擊「新增畫風」建立第一個。</Empty>
          : (
            <div style={S.list}>
              {styles.map((s, i) => (
                <div key={s.id} className="cf-nav-item" style={{ ...S.card, ...(i === 0 ? { borderTop: 'none' } : {}) }} onClick={() => openEdit(s)}>
                  <div>
                    <div style={S.cardName}>{s.name}</div>
                    <div style={S.cardMeta}>
                      {s.description || <span style={{ opacity: 0.4 }}>無說明</span>}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span style={S.badge}>{s.base_style}</span>
                    {s.loras?.length > 0 && (
                      <span style={S.badge}>LoRA ×{s.loras.length}</span>
                    )}
                    <Icon name="chevron-right" size={15} style={{ color: 'var(--faint)', marginLeft: 4 }} />
                  </div>
                </div>
              ))}
            </div>
          )
        }
      </div>
    )
  }

  // Edit view
  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <div>
          <button className="cf-link" style={{ ...UI.btnGhost, color: 'var(--muted)', padding: '2px 4px', margin: '0 -4px' }} onClick={() => setView('list')}><Icon name="arrow-left" size={13} />畫風管理</button>
          <h1 style={{ ...S.title, marginTop: 4 }}>{editing ? editing.name : '新增畫風'}</h1>
        </div>
        <div />
      </div>

      <div style={S.form}>
        {/* 名稱 + 說明 */}
        <div style={S.row}>
          <div style={{ ...S.field, flex: 1 }}>
            <label style={S.label}>名稱</label>
            <input
              style={S.input}
              value={form.name}
              onChange={e => setField('name', e.target.value)}
              placeholder="例：插畫奇幻風"
            />
          </div>
          <div style={{ ...S.field, flex: 2 }}>
            <label style={S.label}>說明（選填）</label>
            <input
              style={S.input}
              value={form.description}
              onChange={e => setField('description', e.target.value)}
              placeholder="簡短描述這個畫風的用途或特色"
            />
          </div>
        </div>

        {/* 基底 Style */}
        <div style={{ ...S.field, maxWidth: 220 }}>
          <label style={S.label}>
            基底 Style
            <span style={S.labelHint}>決定 LLM 編譯模板</span>
          </label>
          <select
            style={S.select}
            value={form.base_style}
            onChange={e => setField('base_style', e.target.value)}
          >
            {BASE_STYLES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div style={S.divider} />

        {/* Quality Prefix */}
        <div style={S.field}>
          <label style={S.label}>
            Quality Prefix
            <span style={S.labelHint}>空白 = 使用基底 Style 的預設值</span>
          </label>
          <textarea
            style={{ ...S.textarea, minHeight: 52 }}
            value={form.quality_prefix}
            onChange={e => setField('quality_prefix', e.target.value)}
            placeholder={`例：masterpiece, best quality, newest（空白 = 繼承 ${form.base_style} 預設）`}
          />
        </div>

        {/* Negative */}
        <div style={S.field}>
          <label style={S.label}>
            Negative Prompt
            <span style={S.labelHint}>空白 = 使用基底 Style 的預設值</span>
          </label>
          <textarea
            style={{ ...S.textarea, minHeight: 64 }}
            value={form.negative}
            onChange={e => setField('negative', e.target.value)}
            placeholder={`空白 = 繼承 ${form.base_style} 預設 negative`}
          />
        </div>

        {/* Extra Tags */}
        <div style={S.field}>
          <label style={S.label}>
            Extra Tags
            <span style={S.labelHint}>固定附加在每次生成的 positive prompt 尾端</span>
          </label>
          <input
            style={S.input}
            value={form.extra_tags}
            onChange={e => setField('extra_tags', e.target.value)}
            placeholder="例：watercolor style, ink wash, soft lighting"
          />
        </div>

        <div style={S.divider} />

        {/* LoRA */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={S.sectionTitle}>LoRA 模型</span>
            <button style={UI.btnSm} onClick={addLora}><Icon name="plus" size={13} />新增 LoRA</button>
          </div>
          {form.loras.length === 0
            ? <div style={{ ...S.empty, padding: '10px 0' }}>尚無 LoRA，點擊「新增 LoRA」加入。</div>
            : (
              <div style={S.loraList}>
                {form.loras.map((l, idx) => (
                  <div key={idx} style={S.loraRow}>
                    {loraList.length > 0 ? (
                      <select
                        style={S.loraModel}
                        value={l.model}
                        onChange={e => setLora(idx, 'model', e.target.value)}
                      >
                        <option value="">— 選擇 LoRA —</option>
                        {loraList.map(name => (
                          <option key={name} value={name}>{name}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        style={S.loraModel}
                        value={l.model}
                        onChange={e => setLora(idx, 'model', e.target.value)}
                        placeholder="LoRA 檔名（ComfyUI 離線，請手動輸入）"
                      />
                    )}
                    <input
                      style={S.loraWeight}
                      type="number"
                      min={0} max={2} step={0.05}
                      value={l.weight}
                      onChange={e => setLora(idx, 'weight', parseFloat(e.target.value) || 0)}
                      title="Weight (0–2)"
                    />
                    <button style={S.btnIcon} onClick={() => removeLora(idx)} title="移除" aria-label="移除 LoRA"><Icon name="x" size={14} /></button>
                  </div>
                ))}
              </div>
            )
          }
        </div>

        {/* Error */}
        {error && (
          <div style={{ color: 'var(--danger)', fontSize: 13 }}>{error}</div>
        )}

        {/* Actions */}
        <div style={S.formActions}>
          <button
            style={{ ...S.btn, opacity: saving ? 0.5 : 1, flex: 1 }}
            onClick={save}
            disabled={saving}
          >
            {saving ? <span style={S.spinner} /> : '儲存'}
          </button>
          {editing && (
            <button style={S.btnDanger} onClick={deleteStyle}>刪除</button>
          )}
          <button style={S.btnSecondary} onClick={() => setView('list')}>取消</button>
        </div>

        {/* Test Generation — only for saved styles */}
        {editing && (
          <>
            <div style={S.divider} />
            <div style={S.testSection}>
              <span style={S.testTitle}>畫風測試生成</span>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  style={{ ...S.input, flex: 1 }}
                  value={testPrompt}
                  onChange={e => setTestPrompt(e.target.value)}
                  placeholder="輸入測試描述（中文），例：一位紅髮少女站在森林中"
                  onKeyDown={e => e.key === 'Enter' && !testGenerating && testGenerate()}
                />
                <button
                  style={{ ...S.btn, padding: '8px 18px', opacity: testGenerating ? 0.5 : 1, whiteSpace: 'nowrap' }}
                  onClick={testGenerate}
                  disabled={testGenerating}
                >
                  {testGenerating ? <span style={S.spinner} /> : '測試生成'}
                </button>
              </div>
              {testError && <div style={{ color: 'var(--danger)', fontSize: 12 }}>{testError}</div>}
              {testGenerating && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
                  <span style={S.spinnerLg} />
                  生成中，請稍候...
                </div>
              )}
              {testResult ? (
                <div ref={testImgRef} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <FitImage src={testResult.url} alt="test result" maxHeight="min(60vh, 520px)" style={{ border: '1px solid var(--border)', borderRadius: 10 }} />
                  <div style={S.testMeta}>
                    style: {testResult.style} · seed: {testResult.seed} · 點圖看原尺寸
                  </div>
                  <div style={{ ...S.testMeta, opacity: 0.7 }}><strong>正向：</strong>{testResult.prompt}</div>
                  <div style={{ ...S.testMeta, opacity: 0.7 }}><strong>負向（實際送出）：</strong>{testResult.negative || '（空）'}</div>
                </div>
              ) : !testGenerating && (
                <div style={S.testPlaceholder}>輸入描述後點擊「測試生成」</div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
