import { useState, useRef, useCallback, useEffect } from 'react'
import { apiPostForm, apiPostJson, request, apiUrl } from '../api/client'
import { EP } from '../api/endpoints'
import { useAsync } from '../api/useAsync'
import { UI } from './sharedStyles'

const DEFAULT_NEGATIVE =
  'low quality, blurry, watermark, text, signature, bad anatomy, extra limbs, deformed, ugly, duplicate, worst quality'

const S = {
  root: { display: 'flex', gap: 24, alignItems: 'flex-start' },
  form: { flex: 1, display: 'flex', flexDirection: 'column', gap: 14 },
  result: { flex: 1, display: 'flex', flexDirection: 'column', gap: 12 },
  label: { fontSize: 12, color: 'var(--muted)', marginBottom: 4, display: 'block' },
  textarea: {
    width: '100%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text)',
    padding: '10px 12px',
    fontSize: 14,
    resize: 'vertical',
    fontFamily: 'inherit',
    outline: 'none',
  },
  row: { display: 'flex', gap: 12 },
  fieldGroup: { flex: 1, display: 'flex', flexDirection: 'column', gap: 4 },
  select: {
    width: '100%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text)',
    padding: '8px 10px',
    fontSize: 14,
    outline: 'none',
  },
  input: {
    width: '100%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text)',
    padding: '8px 10px',
    fontSize: 14,
    outline: 'none',
  },
  sliderRow: { display: 'flex', alignItems: 'center', gap: 10 },
  slider: { flex: 1, accentColor: 'var(--accent)' },
  sliderVal: { width: 32, textAlign: 'right', color: 'var(--muted)', fontSize: 13 },
  btn: UI.btnPrimary,
  btnDisabled: UI.btnDisabled,
  btnSecondary: UI.btnSecondary,
  spinner: UI.spinner,
  loading: UI.loading,
  empty: UI.empty,
  error: { color: 'var(--danger)', fontSize: 13 },
  seedRow: { display: 'flex', gap: 8, alignItems: 'center' },
  refSection: {
    border: '1px solid var(--border)', borderRadius: 10,
    padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10,
    background: 'var(--surface)',
  },
  refHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  refTitle: { fontSize: 13, fontWeight: 600, color: 'var(--text)' },
  toggleBtn: {
    fontSize: 12, padding: '3px 10px', borderRadius: 6,
    border: '1px solid var(--border)', cursor: 'pointer',
    background: 'transparent', color: 'var(--muted)',
  },
  toggleBtnActive: { background: 'var(--accent)', color: 'var(--accent-contrast)', border: 'none' },
  refDropzone: {
    border: '2px dashed var(--border)', borderRadius: 8, minHeight: 100,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer', overflow: 'hidden', background: 'var(--bg)',
    transition: 'border-color .15s',
  },
  refDropzoneActive: { borderColor: 'var(--accent)' },
  refThumb: { width: '100%', maxHeight: 160, objectFit: 'contain', display: 'block' },
  modeBtns: { display: 'flex', gap: 8 },
  modeBtn: {
    flex: 1, padding: '7px 0', borderRadius: 8, border: '1px solid var(--border)',
    background: 'transparent', color: 'var(--muted)', fontSize: 12,
    cursor: 'pointer', textAlign: 'center',
  },
  modeBtnActive: { background: 'var(--accent)', color: 'var(--accent-contrast)', border: 'none', fontWeight: 600 },
  diceBtn: {
    padding: '7px 10px',
    borderRadius: 8,
    border: '1px solid var(--border)',
    background: 'var(--surface)',
    color: 'var(--text)',
    cursor: 'pointer',
    fontSize: 16,
    lineHeight: 1,
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

export default function GenerateTab({ onAddHistory, artStyleId = '', pendingPrompt = '', onPromptConsumed }) {
  const [promptZh, setPromptZh] = useState(() => sessionStorage.getItem('gen_promptZh') ?? '')
  const [promptEn, setPromptEn] = useState(() => sessionStorage.getItem('gen_promptEn') ?? '')
  const [optimizedEn, setOptimizedEn] = useState(() => sessionStorage.getItem('gen_optimizedEn') ?? '')
  const [detectedStyle, setDetectedStyle] = useState(null)
  const [negPrompt, setNegPrompt] = useState(() => sessionStorage.getItem('gen_negPrompt') ?? DEFAULT_NEGATIVE)
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
        setNegPromptP(data.negative || DEFAULT_NEGATIVE)
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

  // B1：訂閱 job 進度 SSE，回傳完成後的圖片 blob
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
        fd.append('negative_prompt', negPrompt.trim() || DEFAULT_NEGATIVE)
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
        fd.append('negative_prompt', negPrompt.trim() || DEFAULT_NEGATIVE)
        fd.append('mode', refMode)
        fd.append('denoise', String(denoise))
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
              negative_prompt: negPrompt.trim() || DEFAULT_NEGATIVE,
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
    <div style={S.root}>
      {/* ── 左：參數 ── */}
      <div style={S.form}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <label style={{ ...S.label, marginBottom: 0 }}>中文描述 (用於翻譯優化)</label>
              {detectedStyle && (
                <span style={{
                  fontSize: 10, padding: '1px 6px', borderRadius: 4,
                  background: 'var(--accent-soft-2)',
                  border: '1px solid var(--accent-border)',
                  color: 'var(--accent)', fontWeight: 600, letterSpacing: '0.05em',
                }}>
                  {detectedStyle.toUpperCase()}
                </span>
              )}
            </div>
            <button
              style={{ ...S.btnSecondary, padding: '2px 8px', fontSize: 11, background: 'var(--tint-blue-bg)', borderColor: 'var(--accent)', color: 'var(--accent)' }}
              onClick={onOptimize}
              disabled={optimizing || !promptZh.trim()}
            >
              {optimizing ? '編譯中...' : '✨ AI 編譯提示詞'}
            </button>
          </div>
          <textarea
            style={{ ...S.textarea, minHeight: 60 }}
            placeholder="例如：一個可愛的少女，穿著黃色連帽衫，室內光線..."
            value={promptZh}
            onChange={(e) => setPromptZhP(e.target.value)}
          />
          {optimizing && (
            <div style={{ marginTop: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: 'var(--accent)' }}>✨ AI 翻譯優化中...</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>{optimizeElapsed}s</span>
              </div>
              <div style={{ width: '100%', background: 'var(--border)', height: 4, borderRadius: 2, overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  background: 'var(--accent)',
                  borderRadius: 2,
                  width: '40%',
                  animation: 'optimizePulse 1.2s ease-in-out infinite',
                }} />
              </div>
            </div>
          )}
        </div>
        <div>
          <label style={S.label}>手動英文標籤 (技術關鍵字/補充)</label>
          <textarea
            style={{ ...S.textarea, minHeight: 60 }}
            placeholder="e.g. masterpiece, 8k, bokeh..."
            value={promptEn}
            onChange={(e) => setPromptEnP(e.target.value)}
          />
          {sourceCharId && (
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
              已連結角色 #{sourceCharId}（生成時依角色年齡套用內容護欄；從其他 Tab 帶入新描述時才會換掉）
            </div>
          )}
          {promptEnHasCjk && (
            <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>
              ⚠ 此欄不會翻譯，中文會原樣送進模型。請改寫在上方「中文描述」再按 AI 編譯，或改用英文 tag（例：一位女孩 → 1girl, solo）。
            </div>
          )}
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <label style={S.label}>最終提示詞預覽 (發送給 AI)</label>
            {finalPrompt && (
              <button 
                style={{ ...S.btnSecondary, padding: '2px 8px', fontSize: 11, background: 'var(--hover)', borderColor: 'var(--border)' }}
                onClick={onCopy}
              >
                {copied ? '✅ 已複製' : '📋 複製'}
              </button>
            )}
          </div>
          <div style={{ 
            ...S.textarea, 
            background: 'var(--code-bg)', 
            fontSize: 12, 
            minHeight: 100, 
            padding: '12px',
            borderStyle: 'dashed',
            whiteSpace: 'pre-wrap',
            color: 'var(--code-fg)',
            lineHeight: 1.6
          }}>
            {promptEn || optimizedEn ? (
              <>
                {promptEn}
                {promptEn && optimizedEn ? '\n\n' : ''}
                {optimizedEn}
              </>
            ) : (
              <span style={{ color: 'var(--muted)', fontStyle: 'italic' }}>等待輸入或優化...</span>
            )}
          </div>
        </div>

        <div>
          <label style={S.label}>負向 Prompt</label>
          <textarea
            style={{ ...S.textarea, minHeight: 50 }}
            value={negPrompt}
            onChange={(e) => setNegPromptP(e.target.value)}
          />
        </div>

        {/* ── 參考圖引導模式 ── */}
        <div style={S.refSection}>
          <div style={S.refHeader}>
            <span style={S.refTitle}>參考圖引導</span>
            <button
              style={{ ...S.toggleBtn, ...(refEnabled ? S.toggleBtnActive : {}) }}
              onClick={() => { setRefEnabled(v => !v); setRefFile(null); setRefPreview(null) }}
            >
              {refEnabled ? '已啟用' : '未啟用'}
            </button>
          </div>
          {refEnabled && (
            <>
              {/* 模式選擇 */}
              <div style={S.modeBtns}>
                {[
                  { key: 'i2i', label: 'Image2Image', desc: '保留原圖結構' },
                  { key: 'controlnet', label: 'ControlNet', desc: '約束構圖/姿勢' },
                  { key: 'ipadapter', label: 'IP-Adapter', desc: '外觀/角色參考' },
                ].map(m => (
                  <button
                    key={m.key}
                    style={{ ...S.modeBtn, ...(refMode === m.key ? S.modeBtnActive : {}) }}
                    onClick={() => setRefMode(m.key)}
                    title={m.desc}
                  >
                    {m.label}
                    <div style={{ fontSize: 10, marginTop: 2, opacity: 0.7 }}>{m.desc}</div>
                  </button>
                ))}
              </div>

              {/* 圖片上傳 */}
              <div
                style={{ ...S.refDropzone, ...(refDragging ? S.refDropzoneActive : {}) }}
                onClick={() => refInputRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setRefDragging(true) }}
                onDragLeave={() => setRefDragging(false)}
                onDrop={e => { e.preventDefault(); setRefDragging(false); handleRefFile(e.dataTransfer.files[0]) }}
              >
                {refPreview
                  ? <img src={refPreview} style={S.refThumb} alt="ref" />
                  : <span style={{ color: 'var(--muted)', fontSize: 13 }}>拖放或點擊上傳參考圖</span>
                }
              </div>
              <input
                ref={refInputRef} type="file" accept="image/*" style={{ display: 'none' }}
                onChange={e => handleRefFile(e.target.files[0])}
              />

              {/* IP-Adapter Weight */}
              {refMode === 'ipadapter' && (
                <div>
                  <label style={S.label}>
                    參考強度：{ipaWeight.toFixed(2)}
                    <span style={{ marginLeft: 6, opacity: 0.6 }}>（0.6 = 平衡，越高越接近參考圖外觀）</span>
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                    <input
                      type="range" min={0.1} max={1.5} step={0.05}
                      value={ipaWeight}
                      style={{ flex: 1, accentColor: 'var(--accent)' }}
                      onChange={e => setIpaWeight(Number(e.target.value))}
                    />
                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
                  </div>
                </div>
              )}

              {/* Denoise（僅 i2i） */}
              {refMode === 'i2i' && (
                <div>
                  <label style={S.label}>
                    保留強度：{Math.round((1 - denoise) * 100)}%
                    <span style={{ marginLeft: 6, opacity: 0.6 }}>（越高越接近原圖）</span>
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>大改</span>
                    <input
                      type="range" min={0.05} max={0.95} step={0.05}
                      value={denoise}
                      style={{ flex: 1, accentColor: 'var(--accent)' }}
                      onChange={e => setDenoise(Number(e.target.value))}
                    />
                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>微調</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

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
          <div style={S.fieldGroup}>
            <label style={S.label}>Steps：{steps}</label>
            <div style={S.sliderRow}>
              <span style={{ fontSize: 12, color: 'var(--muted)' }}>10</span>
              <input
                type="range" min={10} max={50} value={steps}
                style={S.slider}
                onChange={(e) => setSteps(Number(e.target.value))}
              />
              <span style={{ fontSize: 12, color: 'var(--muted)' }}>50</span>
            </div>
          </div>
        </div>

        <div>
          <label style={S.label}>Seed（-1 = 隨機）</label>
          <div style={S.seedRow}>
            <input
              type="number" style={{ ...S.input, flex: 1 }}
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
            />
            <button style={S.diceBtn} title="隨機 Seed" onClick={randomSeed}>🎲</button>
          </div>
        </div>

        <button
          style={{ ...S.btn, ...(canGenerate ? {} : S.btnDisabled) }}
          disabled={!canGenerate}
          onClick={onGenerate}
        >
          {loading ? '生成中...' : '生成圖片'}
        </button>
        {error && <p style={S.error}>{error}</p>}
      </div>

      {/* ── 右：輸出 ── */}
      <div style={S.result}>
        <p style={S.label}>生成結果{lastSeed != null ? `（seed: ${lastSeed}）` : ''}</p>
        {loading && (
          <div style={S.loading}>
            <div style={S.spinner} />
            <div style={{ width: '100%', maxWidth: 300, background: 'var(--border)', height: 6, borderRadius: 3, overflow: 'hidden', position: 'relative', marginTop: 12 }}>
              {genPct == null
                ? <div style={{ position: 'absolute', height: '100%', background: 'var(--accent)', borderRadius: 3, animation: 'indeterminate 1.6s ease-in-out infinite' }} />
                : <div style={{ height: '100%', width: `${genPct}%`, background: 'var(--accent)', borderRadius: 3, transition: 'width .2s' }} />}
            </div>
            <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4 }}>{genPct == null ? 'ComfyUI 正在繪圖中...' : `繪圖中 ${genPct}%`}</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>已耗時：{elapsed}s</div>
          </div>
        )}
        {!loading && result && (
          <>
            <img src={result} style={{ width: '100%', borderRadius: 12 }} alt="generated" />
            <button style={S.btnSecondary} onClick={download}>下載圖片</button>
          </>
        )}
        {!loading && !result && (
          <div style={S.empty}>
            <span>輸入 prompt 並按「生成圖片」</span>
          </div>
        )}
      </div>
    </div>
  )
}
