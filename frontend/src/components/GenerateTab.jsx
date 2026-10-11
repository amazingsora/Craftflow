import { useState, useRef, useCallback, useEffect } from 'react'
import { apiPostForm, apiPostJson, request, apiUrl } from '../api/client'
import { EP } from '../api/endpoints'
import { useAsync } from '../api/useAsync'
import { UI } from './sharedStyles'
import { Icon } from './Icon.jsx'
import { Panel, FieldHead, Switch, Slider, Segmented, Empty, Progress, Kbd } from './ui.jsx'

const S = {
  root: { display: 'grid', gap: 24, alignItems: 'start' },   // 欄寬見 index.css .cf-split
  form: { display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 },
  result: { position: 'sticky', top: 0, display: 'flex', flexDirection: 'column', minWidth: 0 },
  label: UI.label,
  textarea: UI.textarea,
  row: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  fieldGroup: { display: 'flex', flexDirection: 'column', minWidth: 0 },
  select: UI.select,
  input: UI.input,
  btn: UI.btnPrimary,
  btnDisabled: UI.btnDisabled,
  btnSecondary: UI.btnSecondary,
  spinner: UI.spinner,
  loading: UI.loading,
  empty: UI.empty,
  error: { ...UI.error, padding: '8px 10px', borderRadius: 'var(--r)', background: 'var(--tint-red-bg)' },
  seedRow: { display: 'flex', gap: 8, alignItems: 'center' },
  hint: { fontSize: 12, color: 'var(--muted)', marginTop: 6, lineHeight: 1.55 },
  warn: { fontSize: 12, color: 'var(--danger)', marginTop: 6, lineHeight: 1.55 },
  preview: {
    fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.7, minHeight: 88,
    padding: '10px 12px', borderRadius: 'var(--r)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
    background: 'var(--code-bg)', color: 'var(--code-fg)', border: '1px dashed var(--border-strong)',
  },
  styleTag: {
    fontFamily: 'var(--font-mono)', fontSize: 10, padding: '1px 6px', borderRadius: 3,
    background: 'var(--accent-soft)', color: 'var(--accent)', fontWeight: 600, letterSpacing: '.04em',
  },
  refDropzone: {
    border: '1px dashed var(--border-strong)', borderRadius: 'var(--r)', minHeight: 112,
    display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 6,
    cursor: 'pointer', overflow: 'hidden', background: 'var(--surface-2)', color: 'var(--muted)', fontSize: 12.5,
    transition: 'border-color .15s, background .15s',
  },
  refDropzoneActive: { borderColor: 'var(--accent)', background: 'var(--accent-soft)' },
  refThumb: { width: '100%', maxHeight: 180, objectFit: 'contain', display: 'block' },
  actionBar: {
    position: 'sticky', bottom: 0, zIndex: 2, display: 'flex', gap: 8,
    padding: '12px 0 4px', background: 'linear-gradient(transparent, var(--bg) 30%)',
  },
  canvasHead: {
    display: 'flex', alignItems: 'center', gap: 10, minHeight: 44,
    padding: '8px 10px 8px 14px', borderBottom: '1px solid var(--border)',
  },
  canvas: {
    position: 'relative', minHeight: 'min(72vh, 760px)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 24, backgroundColor: 'var(--canvas)',
  },
  resultImg: {
    display: 'block', maxWidth: '100%', maxHeight: 'min(68vh, 720px)', objectFit: 'contain',
    borderRadius: 'var(--r-sm)', boxShadow: '0 0 0 1px rgba(0,0,0,.06), 0 16px 40px -16px rgba(13,17,23,.45)',
    animation: 'cf-pop .35s var(--ease) both',
  },
  seedChip: {
    fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-2)', padding: '2px 7px',
    borderRadius: 'var(--r-sm)', background: 'var(--surface-2)', border: '1px solid var(--border)',
  },
}

function dedupeTags(s) {
  const seen = new Set()
  return s.split(',').map(t => t.trim()).filter(t => {
    if (!t) return false
    const k = t.toLowerCase().replace(/^\(+|\)+$/g, '').replace(/:[\d.]+$/, '').trim()
    if (seen.has(k)) return false
    seen.add(k)
    return true
  }).join(', ')
}

export default function GenerateTab({ onAddHistory, artStyleId = '', pendingPrompt = '', onPromptConsumed, capability = { ipa_supported: true, cn_supported: true } }) {
  const ipaSupported = capability.ipa_supported !== false
  const cnNative = capability.cn_supported !== false
  const [promptZh, setPromptZh] = useState(() => sessionStorage.getItem('gen_promptZh') ?? '')
  const [promptEn, setPromptEn] = useState(() => sessionStorage.getItem('gen_promptEn') ?? '')
  const [optimizedEn, setOptimizedEn] = useState(() => sessionStorage.getItem('gen_optimizedEn') ?? '')
  const [detectedStyle, setDetectedStyle] = useState(null)
  const [negPrompt, setNegPrompt] = useState(() => sessionStorage.getItem('gen_negPrompt') ?? '')
  // 「以此角色生圖」帶入的角色 id：送出時一併帶給後端，未成年護欄依角色年齡判定
  const [sourceCharId, setSourceCharId] = useState(() => Number(sessionStorage.getItem('gen_charId')) || null)
  const [steps, setSteps] = useState(20)
  const [seed, setSeed] = useState(-1)
  const [size, setSize] = useState('1024x1024')
  const [result, setResult] = useState(null)
  const [genPct, setGenPct] = useState(null)
  const generateTask = useAsync()
  const optimizeTask = useAsync()
  const loading = generateTask.loading
  const optimizing = optimizeTask.loading
  const [optimizeElapsed, setOptimizeElapsed] = useState(0)
  const optimizeTimer = useRef()
  const [copied, setCopied] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const error = generateTask.error || optimizeTask.error
  const setError = (message) => {
    generateTask.setError(message)
    optimizeTask.setError(null)
  }
  const [lastSeed, setLastSeed] = useState(null)
  const elapsedTimer = useRef()

  useEffect(() => {
    if (!pendingPrompt) return
    if (typeof pendingPrompt === 'string') {
      // 其他 Tab（ComposeTab 等）仍傳中文字串
      setPromptZhP(pendingPrompt)
      setSourceCharP(null)
    } else {
      // 角色管理「以此角色生圖」：英文識別段放手動英文欄（AI 編譯不會覆蓋），中文欄留給場景描述
      setPromptEnP(pendingPrompt.en || '')
      setPromptZhP(pendingPrompt.zh || '')
      if (pendingPrompt.negative) setNegPromptP(pendingPrompt.negative)
      setSourceCharP(pendingPrompt.characterId ?? null)
    }
    setOptimizedEnP('')
    onPromptConsumed?.()
  }, [pendingPrompt])

  // Reference image guide mode
  const [refEnabled, setRefEnabled] = useState(false)
  const [refFile, setRefFile] = useState(null)
  const [refPreview, setRefPreview] = useState(null)
  const [refMode, setRefMode] = useState('i2i')  // 'i2i' | 'controlnet' | 'ipadapter'
  const [denoise, setDenoise] = useState(0.35)
  const [ipaWeight, setIpaWeight] = useState(0.6)
  const [cnWeight, setCnWeight] = useState(0.85)
  const [refDragging, setRefDragging] = useState(false)
  const refInputRef = useRef()

  // 實際發送給 SDXL 的 Prompt：[英文輸入, AI 優化結果]
  // 去重：角色識別段已含 quality/主體，場景再按 AI 編譯時會再出一份；保留首次出現＝識別段的順序
  const finalPrompt = dedupeTags([promptEn, optimizedEn].filter(Boolean).join(', '))
  // 手動英文欄不經翻譯、原樣送出；含中日文字元時提示改寫到上方中文描述
  const promptEnHasCjk = /[\u3040-\u30ff\u3400-\u9fff]/.test(promptEn)

  const setPromptZhP = (v) => { setPromptZh(v); sessionStorage.setItem('gen_promptZh', v) }
  const setPromptEnP = (v) => { setPromptEn(v); sessionStorage.setItem('gen_promptEn', v) }
  const setSourceCharP = (v) => { setSourceCharId(v); if (v) sessionStorage.setItem('gen_charId', String(v)); else sessionStorage.removeItem('gen_charId') }
  const setOptimizedEnP = (v) => { setOptimizedEn(v); sessionStorage.setItem('gen_optimizedEn', v) }
  const setNegPromptP = (v) => { setNegPrompt(v); sessionStorage.setItem('gen_negPrompt', v) }

  const randomSeed = () => setSeed(Math.floor(Math.random() * 2 ** 31))

  // R-04：全部清空（中文描述、手動 tag、預覽、負向、參考圖、連結角色）
  const onReset = () => {
    if (loading || optimizing) return
    setPromptZhP(''); setPromptEnP(''); setOptimizedEnP(''); setNegPromptP('')
    setSourceCharP(null); setDetectedStyle(null)
    setRefEnabled(false); setRefFile(null); setRefPreview(null)
    setError(null)
  }

  useEffect(() => {
    if (!ipaSupported && refMode === 'ipadapter') setRefMode('i2i')
  }, [ipaSupported, refMode])

  const handleRefFile = useCallback((f) => {
    if (!f || !f.type.startsWith('image/')) return
    setRefFile(f)
    setRefPreview(URL.createObjectURL(f))
  }, [])

  const onCopy = () => {
    if (!finalPrompt.trim()) return
    navigator.clipboard.writeText(finalPrompt.trim())
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const onOptimize = async () => {
    if (!promptZh.trim() || optimizing) return
    setError(null)
    setOptimizeElapsed(0)
    optimizeTimer.current = setInterval(() => setOptimizeElapsed(s => s + 1), 1000)
    try {
      const data = await optimizeTask.run(() => apiPostJson(EP.compilePrompt, {
        prompt: promptZh,
        art_style_id: artStyleId ? Number(artStyleId) : null,
      }))
      if (data.positive) {
        setOptimizedEnP(data.positive.trim())
        setNegPromptP(data.negative || '')
        setDetectedStyle(data.style || null)
      }
    } finally {
      clearInterval(optimizeTimer.current)
    }
  }

  const startProgress = () => {
    setElapsed(0)
    clearInterval(elapsedTimer.current)
    elapsedTimer.current = setInterval(() => setElapsed(old => old + 1), 1000)
  }

  const stopProgress = () => {
    clearInterval(elapsedTimer.current)
  }

  // 訂閱 job 進度 SSE，回傳完成後的圖片 blob
  const streamJobProgress = (jobId, onPct) => new Promise((resolve, reject) => {
    const es = new EventSource(apiUrl(`/art/jobs/${jobId}/progress`))
    es.onmessage = async (e) => {
      let d
      try { d = JSON.parse(e.data) } catch { return }
      if (d.heartbeat) return
      if (d.event === 'done') {
        es.close()
        try {
          const r = await fetch(apiUrl(`/art/jobs/${jobId}/result?index=0`))
          if (!r.ok) throw new Error('取圖失敗')
          resolve(await r.blob())
        } catch (err) { reject(err) }
      } else if (d.event === 'error') {
        es.close()
        try {
          const j = await fetch(apiUrl(`/art/jobs/${jobId}`)).then(r => r.json())
          reject(new Error(j.error || '生成失敗'))
        } catch { reject(new Error('生成失敗')) }
      } else if (typeof d.pct === 'number') {
        onPct(d.pct)
      }
    }
    es.onerror = () => { es.close(); reject(new Error('進度連線中斷，請重試')) }
  })

  const onGenerate = async () => {
    if (!finalPrompt.trim() || loading) return
    if (refEnabled && !refFile) { setError('請上傳參考圖片'); return }
    setError(null)
    setResult(null)
    startProgress()

    const [width, height] = size.split('x').map(Number)
    const actualSeed = seed < 0 ? Math.floor(Math.random() * 2 ** 31) : seed
    setLastSeed(actualSeed)
    try {
      let blob
      if (refEnabled && refFile && refMode === 'ipadapter') {
        const fd = new FormData()
        fd.append('file', refFile)
        fd.append('prompt', finalPrompt.trim())
        fd.append('negative_prompt', negPrompt.trim())
        fd.append('weight', String(ipaWeight))
        fd.append('width', String(size.split('x')[0]))
        fd.append('height', String(size.split('x')[1]))
        fd.append('steps', String(steps))
        fd.append('seed', String(actualSeed))
        if (artStyleId) fd.append('art_style_id', artStyleId)
        blob = await (await generateTask.run(() => apiPostForm(EP.ipadapter, fd))).blob()
      } else if (refEnabled && refFile) {
        const fd = new FormData()
        fd.append('file', refFile)
        fd.append('prompt', finalPrompt.trim())
        fd.append('negative_prompt', negPrompt.trim())
        fd.append('mode', refMode)
        fd.append('denoise', String(denoise))
        fd.append('cn_weight', String(cnWeight))
        fd.append('width', String(width))
        fd.append('height', String(height))
        fd.append('steps', String(steps))
        fd.append('seed', String(actualSeed))
        if (artStyleId) fd.append('art_style_id', artStyleId)
        blob = await (await generateTask.run(() => apiPostForm(EP.imgGuide, fd))).blob()
      } else {
        // txt2img：async job + SSE 即時進度（同步 /art/generate 仍保留為後端 fallback）
        blob = await generateTask.run(async () => {
          const startResp = await request('/art/generate-async', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              prompt: finalPrompt.trim(),
              negative_prompt: negPrompt.trim(),
              width,
              height,
              steps,
              seed: actualSeed,
              art_style_id: artStyleId ? Number(artStyleId) : null,
              character_id: sourceCharId,
              batch_size: 1,
            }),
          })
          const { job_id } = await startResp.json()
          return await streamJobProgress(job_id, setGenPct)
        })
      }
      const url = URL.createObjectURL(blob)
      setResult(url)
      stopProgress()
      onAddHistory?.({
        type: refEnabled ? refMode : 'generate',
        url,
        filename: `craftflow_${actualSeed}.png`,
        label: finalPrompt.trim().slice(0, 30),
      })
    } catch (e) {
      clearInterval(elapsedTimer.current)
    } finally {
      setGenPct(null)
    }
  }

  const download = () => {
    const a = document.createElement('a')
    a.href = result
    a.download = `craftflow_${lastSeed ?? Date.now()}.png`
    a.click()
  }

  const canGenerate = finalPrompt.trim().length > 0 && !loading && (!refEnabled || !!refFile)

  return (
    <div
      style={S.root}
      className="cf-split"
      onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && canGenerate) { e.preventDefault(); onGenerate() } }}
    >
      {/* ── 左：參數 ── */}
      <div style={S.form}>
        <Panel index="01" title="提示詞" icon="pen-line">
          <div>
            <FieldHead
              label="中文描述"
              hint="用於翻譯優化"
              tag={detectedStyle ? detectedStyle.toUpperCase() : null}
            >
              <button
                style={{ ...UI.btnSm, color: 'var(--accent)', borderColor: 'var(--accent-border)', background: 'var(--accent-soft)' }}
                onClick={onOptimize}
                disabled={optimizing || !promptZh.trim()}
              >
                <Icon name="sparkles" size={13} />
                {optimizing ? `編譯中 ${optimizeElapsed}s` : 'AI 編譯提示詞'}
              </button>
            </FieldHead>
            <textarea
              style={{ ...S.textarea, minHeight: 84 }}
              placeholder="例如：一個可愛的少女，穿著黃色連帽衫，室內光線..."
              value={promptZh}
              onChange={(e) => setPromptZhP(e.target.value)}
            />
            {optimizing && (
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ flex: 1, background: 'var(--border)', height: 3, borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', background: 'var(--accent)', borderRadius: 2, width: '40%', animation: 'optimizePulse 1.2s ease-in-out infinite' }} />
                </div>
                <span style={{ fontSize: 11.5, color: 'var(--accent)' }}>AI 翻譯優化中</span>
              </div>
            )}
          </div>
          <div>
            <FieldHead label="手動英文標籤" hint="技術關鍵字／補充" />
            <textarea
              style={{ ...S.textarea, minHeight: 60, fontFamily: 'var(--font-mono)', fontSize: 13 }}
              placeholder="e.g. masterpiece, 8k, bokeh..."
              value={promptEn}
              onChange={(e) => setPromptEnP(e.target.value)}
            />
            {sourceCharId && (
              <div style={S.hint}>
                已連結角色 <span className="cf-num">#{sourceCharId}</span>（生成時依角色年齡套用內容護欄；從其他 Tab 帶入新描述時才會換掉）
              </div>
            )}
            {promptEnHasCjk && (
              <div style={S.warn}>
                此欄不會翻譯，中文會原樣送進模型。請改寫在上方「中文描述」再按 AI 編譯，或改用英文 tag（例：一位女孩 → 1girl, solo）。
              </div>
            )}
          </div>

          <div>
            <FieldHead label="最終提示詞預覽" hint="發送給 AI">
              {finalPrompt && (
                <button style={UI.btnGhost} onClick={onCopy}>
                  <Icon name={copied ? 'check' : 'copy'} size={13} />
                  {copied ? '已複製' : '複製'}
                </button>
              )}
            </FieldHead>
            <div style={S.preview}>
              {finalPrompt ? finalPrompt : (
                <span style={{ color: 'var(--faint)', fontFamily: 'var(--font-sans)' }}>等待輸入或優化…</span>
              )}
            </div>
          </div>

          <div>
            <FieldHead label="負向 Prompt" />
            <textarea
              style={{ ...S.textarea, minHeight: 52, fontFamily: 'var(--font-mono)', fontSize: 13 }}
              placeholder="留空＝依底模家族／畫風的預設負向"
              value={negPrompt}
              onChange={(e) => setNegPromptP(e.target.value)}
            />
          </div>
        </Panel>

        {/* ── 參考圖引導模式 ── */}
        <Panel
          index="02" title="參考圖引導" icon="image"
          actions={<Switch checked={refEnabled} onChange={() => { setRefEnabled(v => !v); setRefFile(null); setRefPreview(null) }} sub={refEnabled ? 'ON' : 'OFF'} />}
          flush={!refEnabled}
        >
          {refEnabled && (
            <>
              {/* 模式選擇 */}
              <Segmented
                block
                value={refMode}
                onChange={setRefMode}
                options={[
                  { key: 'i2i', label: 'Image2Image', sub: '保留原圖結構' },
                  { key: 'controlnet', label: cnNative ? 'ControlNet' : '結構引導', sub: cnNative ? '約束構圖/姿勢' : `改走 ${capability.cn_fallback || 'img2img'}`, title: cnNative ? '約束構圖/姿勢' : `此模型無 CN，改走 ${capability.cn_fallback || 'img2img'}` },
                  { key: 'ipadapter', label: 'IP-Adapter', sub: ipaSupported ? '外觀/角色參考' : '此模型不支援', disabled: !ipaSupported },
                ]}
              />

              {/* 圖片上傳 */}
              <div
                className="cf-drop"
                style={{ ...S.refDropzone, ...(refDragging ? S.refDropzoneActive : {}) }}
                onClick={() => refInputRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setRefDragging(true) }}
                onDragLeave={() => setRefDragging(false)}
                onDrop={e => { e.preventDefault(); setRefDragging(false); handleRefFile(e.dataTransfer.files[0]) }}
              >
                {refPreview
                  ? <img src={refPreview} style={S.refThumb} alt="參考圖" />
                  : <><Icon name="upload" size={18} /><span>拖放或點擊上傳參考圖</span></>
                }
              </div>
              <input
                ref={refInputRef} type="file" accept="image/*" style={{ display: 'none' }}
                onChange={e => handleRefFile(e.target.files[0])}
              />

              {/* IP-Adapter Weight */}
              {refMode === 'ipadapter' && (
                <Slider label="參考強度" hint="0.6 = 平衡，越高越接近參考圖外觀"
                  value={ipaWeight} min={0.1} max={1.5} step={0.05} minLabel="0.1" maxLabel="1.5"
                  format={v => v.toFixed(2)} onChange={setIpaWeight} />
              )}

              {/* 結構引導強度（controlnet 模式；無原生 CN 時映射到 LLLite 強度或 img2img denoise） */}
              {refMode === 'controlnet' && (
                <Slider label="引導強度" hint="越高越貼近參考圖構圖"
                  value={cnWeight} min={0.1} max={1.5} step={0.05} minLabel="0.1" maxLabel="1.5"
                  format={v => v.toFixed(2)} onChange={setCnWeight} />
              )}

              {/* Denoise（僅 i2i） */}
              {refMode === 'i2i' && (
                <Slider label="保留強度" hint="越高越接近原圖"
                  value={denoise} min={0.05} max={0.95} step={0.05} minLabel="大改" maxLabel="微調"
                  format={v => `${Math.round((1 - v) * 100)}%`} onChange={setDenoise} />
              )}
            </>
          )}
        </Panel>

        <Panel index="03" title="參數" icon="sliders-horizontal">
          <div style={S.row}>
            <div style={S.fieldGroup}>
              <label style={S.label}>尺寸</label>
              <select style={S.select} value={size} onChange={(e) => setSize(e.target.value)}>
                <option value="512x512">512 × 512</option>
                <option value="768x768">768 × 768</option>
                <option value="1024x1024">1024 × 1024</option>
                <option value="768x1024">768 × 1024 (直向)</option>
                <option value="1024x768">1024 × 768 (橫向)</option>
              </select>
            </div>
            <div style={{ ...S.fieldGroup, justifyContent: 'flex-end' }}>
              <Slider label="Steps" value={steps} min={10} max={50} minLabel="10" maxLabel="50" onChange={setSteps} />
            </div>
          </div>

          <div>
            <FieldHead label="Seed" hint="-1 = 隨機" />
            <div style={S.seedRow}>
              <input
                type="number" style={{ ...S.input, flex: 1, fontFamily: 'var(--font-mono)' }}
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
              />
              <button style={{ ...UI.btnIcon, width: 36, height: 36 }} title="隨機 Seed" aria-label="隨機 Seed" onClick={randomSeed}>
                <Icon name="dice-5" size={16} />
              </button>
            </div>
          </div>
        </Panel>

        {error && <p style={S.error}>{error}</p>}

        <div style={S.actionBar}>
          <button
            style={{ ...S.btn, flex: 1, height: 42, ...(canGenerate ? {} : S.btnDisabled) }}
            disabled={!canGenerate}
            onClick={onGenerate}
            title="Ctrl + Enter"
          >
            {loading
              ? <><span style={{ width: 14, height: 14, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin .8s linear infinite' }} />生成中 {elapsed}s</>
              : <><Icon name="sparkles" size={15} />生成圖片<Kbd>Ctrl ↵</Kbd></>}
          </button>
          <button
            style={{ ...S.btnSecondary, height: 42 }}
            disabled={loading || optimizing}
            onClick={onReset}
            title="清空中文描述、手動標籤、預覽、負向與參考圖"
          ><Icon name="refresh-cw" size={14} />全部清空</button>
        </div>
      </div>

      {/* ── 右：輸出 ── */}
      <div style={S.result}>
        <div style={{ ...UI.panel, overflow: 'hidden' }}>
          <div style={S.canvasHead}>
            <Icon name="image" size={15} style={{ color: 'var(--muted)' }} />
            <span style={{ fontSize: 13, fontWeight: 600, flex: 1 }}>生成結果</span>
            {lastSeed != null && <span style={S.seedChip}>seed {lastSeed}</span>}
            <span style={{ ...S.seedChip, background: 'transparent' }}>{size.replace('x', ' × ')}</span>
            {!loading && result && (
              <button style={UI.btnSm} onClick={download}><Icon name="download" size={13} />下載</button>
            )}
          </div>
          <div style={S.canvas} className="cf-dotgrid">
            {loading && (
              <div style={{ ...S.loading, padding: 0, width: '100%', maxWidth: 320 }}>
                <div style={S.spinner} />
                <div style={{ width: '100%', marginTop: 8 }}><Progress pct={genPct} /></div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{genPct == null ? 'ComfyUI 正在繪圖中…' : `繪圖中 ${genPct}%`}</div>
                <div style={{ fontSize: 11.5, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>已耗時 {elapsed}s</div>
              </div>
            )}
            {!loading && result && (
              <img src={result} style={S.resultImg} alt="生成結果" />
            )}
            {!loading && !result && (
              <Empty icon="image" title="尚未生成" style={{ background: 'transparent', border: 'none', minHeight: 0 }}>
                輸入提示詞並按「生成圖片」，或在任一欄位按 <span className="cf-num" style={{ whiteSpace: 'nowrap' }}>Ctrl + Enter</span>
              </Empty>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
