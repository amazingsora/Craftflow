import { useState, useRef } from 'react'

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
  btn: {
    padding: '11px 0',
    borderRadius: 8,
    border: 'none',
    background: 'var(--accent)',
    color: '#fff',
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
  },
  btnDisabled: { opacity: 0.45, cursor: 'not-allowed' },
  btnSecondary: {
    padding: '8px 0',
    borderRadius: 8,
    border: '1px solid var(--border)',
    background: 'transparent',
    color: 'var(--text)',
    fontSize: 14,
    cursor: 'pointer',
  },
  spinner: {
    width: 40, height: 40,
    border: '3px solid var(--border)',
    borderTop: '3px solid var(--accent)',
    borderRadius: '50%',
    animation: 'spin 0.9s linear infinite',
  },
  loading: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: 60, color: 'var(--muted)' },
  empty: {
    minHeight: 280,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '2px dashed var(--border)',
    borderRadius: 12,
    color: 'var(--muted)',
  },
  error: { color: 'var(--danger)', fontSize: 13 },
  seedRow: { display: 'flex', gap: 8, alignItems: 'center' },
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

export default function GenerateTab({ onAddHistory }) {
  const [promptZh, setPromptZh] = useState('')
  const [promptEn, setPromptEn] = useState('')
  const [optimizedEn, setOptimizedEn] = useState('')
  const [detectedStyle, setDetectedStyle] = useState(null) // 後端偵測到的 checkpoint style
  const [negPrompt, setNegPrompt] = useState(DEFAULT_NEGATIVE)
  const [steps, setSteps] = useState(20)
  const [seed, setSeed] = useState(-1)
  const [size, setSize] = useState('1024x1024')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [optimizing, setOptimizing] = useState(false)
  const [optimizeElapsed, setOptimizeElapsed] = useState(0)
  const optimizeTimer = useRef()
  const [copied, setCopied] = useState(false)
  const [progress, setProgress] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState(null)
  const [lastSeed, setLastSeed] = useState(null)
  const progressTimer = useRef()
  const elapsedTimer = useRef()

  // 實際發送給 SDXL 的 Prompt：[英文輸入, AI 優化結果]
  const finalPrompt = [promptEn, optimizedEn].filter(Boolean).join(', ')

  const randomSeed = () => setSeed(Math.floor(Math.random() * 2 ** 31))

  const onCopy = () => {
    if (!finalPrompt.trim()) return
    navigator.clipboard.writeText(finalPrompt.trim())
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const onOptimize = async () => {
    if (!promptZh.trim() || optimizing) return
    setOptimizing(true)
    setOptimizeElapsed(0)
    optimizeTimer.current = setInterval(() => setOptimizeElapsed(s => s + 1), 1000)
    try {
      const resp = await fetch('/api/v1/art/compile-prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: promptZh }),
      })
      const data = await resp.json()
      if (data.positive) {
        setOptimizedEn(data.positive.trim())
        setNegPrompt(data.negative || DEFAULT_NEGATIVE)
        setDetectedStyle(data.style || null)
      }
    } catch (e) {
      console.error('Compile failed:', e)
    } finally {
      clearInterval(optimizeTimer.current)
      setOptimizing(false)
    }
  }

  const startProgress = () => {
    setProgress(0)
    setElapsed(0)
    clearInterval(progressTimer.current)
    clearInterval(elapsedTimer.current)
    progressTimer.current = setInterval(() => {
      setProgress(old => {
        if (old >= 95) return old
        return old + (old < 80 ? 1.5 : 0.5)
      })
    }, 200)
    elapsedTimer.current = setInterval(() => setElapsed(old => old + 1), 1000)
  }

  const stopProgress = () => {
    clearInterval(progressTimer.current)
    clearInterval(elapsedTimer.current)
    setProgress(100)
  }

  const onGenerate = async () => {
    if (!finalPrompt.trim() || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    startProgress()

    const [width, height] = size.split('x').map(Number)
    const actualSeed = seed < 0 ? Math.floor(Math.random() * 2 ** 31) : seed
    setLastSeed(actualSeed)
    try {
      const resp = await fetch('/api/v1/art/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: finalPrompt.trim(),
          negative_prompt: negPrompt.trim() || DEFAULT_NEGATIVE,
          width,
          height,
          steps,
          seed: actualSeed,
        }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }))
        throw new Error(err.detail)
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      setResult(url)
      stopProgress()
      onAddHistory?.({
        type: 'generate',
        url,
        filename: `craftflow_${actualSeed}.png`,
        label: finalPrompt.trim().slice(0, 30),
      })
    } catch (e) {
      setError(e.message)
      clearInterval(progressTimer.current)
      clearInterval(elapsedTimer.current)
    } finally {
      setLoading(false)
    }
  }

  const download = () => {
    const a = document.createElement('a')
    a.href = result
    a.download = `craftflow_${lastSeed ?? Date.now()}.png`
    a.click()
  }

  const canGenerate = finalPrompt.trim().length > 0 && !loading

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
                  background: 'rgba(124, 106, 247, 0.15)',
                  border: '1px solid rgba(124, 106, 247, 0.4)',
                  color: 'var(--accent)', fontWeight: 600, letterSpacing: '0.05em',
                }}>
                  {detectedStyle.toUpperCase()}
                </span>
              )}
            </div>
            <button
              style={{ ...S.btnSecondary, padding: '2px 8px', fontSize: 11, background: 'rgba(126, 184, 247, 0.1)', borderColor: 'var(--accent)', color: 'var(--accent)' }}
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
            onChange={(e) => setPromptZh(e.target.value)}
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
            onChange={(e) => setPromptEn(e.target.value)}
          />
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <label style={S.label}>最終提示詞預覽 (發送給 AI)</label>
            {finalPrompt && (
              <button 
                style={{ ...S.btnSecondary, padding: '2px 8px', fontSize: 11, background: 'rgba(255, 255, 255, 0.05)', borderColor: 'var(--border)' }}
                onClick={onCopy}
              >
                {copied ? '✅ 已複製' : '📋 複製'}
              </button>
            )}
          </div>
          <div style={{ 
            ...S.textarea, 
            background: '#0d0d15', 
            fontSize: 12, 
            minHeight: 100, 
            padding: '12px',
            borderStyle: 'dashed',
            whiteSpace: 'pre-wrap',
            color: '#abb2bf',
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
            onChange={(e) => setNegPrompt(e.target.value)}
          />
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
            <div style={{ width: '100%', maxWidth: 300, background: 'var(--border)', height: 6, borderRadius: 3, overflow: 'hidden', marginTop: 12 }}>
              <div style={{ width: `${progress}%`, background: 'var(--accent)', height: '100%', transition: 'width 0.4s ease-out' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', maxWidth: 300, marginTop: 4 }}>
               <span style={{ fontSize: 12, fontWeight: 600 }}>ComfyUI 正在繪圖中...</span>
               <span style={{ fontSize: 12 }}>{Math.round(progress)}%</span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>
               已耗時: {elapsed}s | 預計總需: 10-20s
            </div>
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
