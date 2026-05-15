import { useState, useRef } from 'react'

const S = {
  root: { display: 'flex', gap: 24, alignItems: 'flex-start' },
  left: { flex: '0 0 340px', display: 'flex', flexDirection: 'column', gap: 12 },
  right: { flex: 1, display: 'flex', flexDirection: 'column', gap: 16 },
  dropzone: {
    border: '2px dashed var(--border)',
    borderRadius: 12,
    minHeight: 220,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    overflow: 'hidden',
    background: 'var(--surface)',
    transition: 'border-color .2s',
  },
  dropzoneActive: { borderColor: 'var(--accent)' },
  previewImg: { width: '100%', objectFit: 'contain', maxHeight: 260 },
  hint: { color: 'var(--muted)', textAlign: 'center', padding: 20, lineHeight: 2, fontSize: 13 },
  label: { fontSize: 12, color: 'var(--muted)', marginBottom: 3, display: 'block' },
  textarea: {
    width: '100%',
    background: '#12121e',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text)',
    padding: '10px 12px',
    fontSize: 14,
    resize: 'vertical',
    fontFamily: 'inherit',
    outline: 'none',
    minHeight: 90,
  },
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
    padding: '7px 12px',
    borderRadius: 8,
    border: '1px solid var(--border)',
    background: 'transparent',
    color: 'var(--text)',
    fontSize: 13,
    cursor: 'pointer',
    alignSelf: 'flex-start',
  },
  error: { color: 'var(--danger)', fontSize: 13 },
  // Result panels
  resultImg: { width: '100%', borderRadius: 12, display: 'block' },
  resultImgPlaceholder: {
    minHeight: 200,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '2px dashed var(--border)',
    borderRadius: 12,
    color: 'var(--muted)',
    fontSize: 13,
  },
  adviceCard: {
    background: '#12121e',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: '16px 20px',
    lineHeight: 1.9,
    fontSize: 14,
    color: 'var(--text)',
    whiteSpace: 'pre-wrap',
  },
  advicePlaceholder: {
    minHeight: 120,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '2px dashed var(--border)',
    borderRadius: 12,
    color: 'var(--muted)',
    fontSize: 13,
  },
  promptPill: {
    background: '#1e1a3a',
    border: '1px solid #3a2d6a',
    borderRadius: 8,
    padding: '8px 14px',
    fontSize: 12,
    color: '#b09ef0',
    wordBreak: 'break-all',
    lineHeight: 1.6,
  },
  sectionLabel: { fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 6 },
  loading: {
    display: 'flex', flexDirection: 'column',
    alignItems: 'center', gap: 12,
    padding: 48, color: 'var(--muted)', fontSize: 13,
  },
  spinner: {
    width: 40, height: 40,
    border: '3px solid var(--border)',
    borderTop: '3px solid var(--accent)',
    borderRadius: '50%',
    animation: 'spin 0.9s linear infinite',
  },
  imgRow: { display: 'flex', gap: 12 },
  imgHalf: { flex: 1 },
}

const PLACEHOLDER_QUESTIONS = [
  '如果把視角改成俯視，構圖會如何變化？',
  '這個場景改成夜晚光源，氣氛會怎麼不同？',
  '主角位置太居中，怎麼調整讓畫面更有張力？',
]

export default function ComposeTab({ onAddHistory }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [question, setQuestion] = useState(() => sessionStorage.getItem('compose_question') ?? '')
  const [result, setResult] = useState(null)   // { advice, suggested_prompt, image (b64), seed }
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef()
  const progressTimer = useRef()
  const elapsedTimer = useRef()

  const handleFile = (f) => {
    if (!f || !f.type.startsWith('image/')) return
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setResult(null)
    setError(null)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  const startProgress = () => {
    setProgress(0)
    setElapsed(0)
    clearInterval(progressTimer.current)
    clearInterval(elapsedTimer.current)
    
    // 進度條計時器
    progressTimer.current = setInterval(() => {
      setProgress(old => {
        if (old >= 95) return old
        // 7b 模型通常在 10-15 秒內完成分析，ComfyUI 4 秒
        // 我們讓進度在前 15 秒走到 80% (Ollama)，之後 5 秒走到 95% (ComfyUI)
        const step = old < 80 ? 1 : 0.5
        return old + step
      })
    }, 200)

    // 總時間計時器
    elapsedTimer.current = setInterval(() => {
      setElapsed(old => old + 1)
    }, 1000)
  }

  const stopProgress = () => {
    clearInterval(progressTimer.current)
    clearInterval(elapsedTimer.current)
    setProgress(100)
  }

  const onSubmit = async () => {
    if (!file || !question.trim() || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    startProgress()

    try {
      const body = new FormData()
      body.append('file', file)
      body.append('question', question.trim())

      const resp = await fetch('/api/v1/art/compose', { method: 'POST', body })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }))
        throw new Error(err.detail)
      }
      const data = await resp.json()
      setResult(data)
      stopProgress()

      // Add to history (b64 → blob URL)
      const blob = await fetch(`data:image/png;base64,${data.image}`).then(r => r.blob())
      const url = URL.createObjectURL(blob)
      onAddHistory?.({
        type: 'compose',
        url,
        filename: `compose_${data.seed}.png`,
        label: question.trim().slice(0, 30),
      })
    } catch (e) {
      setError(e.message)
      clearInterval(progressTimer.current)
      clearInterval(elapsedTimer.current)
    } finally {
      setLoading(false)
    }
  }

  const downloadResult = () => {
    if (!result) return
    const a = document.createElement('a')
    a.href = `data:image/png;base64,${result.image}`
    a.download = `compose_${result.seed}.png`
    a.click()
  }

  const canSubmit = file && question.trim().length > 0 && !loading
  const dzStyle = { ...S.dropzone, ...(dragging ? S.dropzoneActive : {}) }

  return (
    <div style={S.root}>
      {/* ── 左：輸入 ── */}
      <div style={S.left}>
        <label style={S.label}>上傳草圖</label>
        <div
          style={dzStyle}
          onDrop={onDrop}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onClick={() => inputRef.current.click()}
        >
          {preview
            ? <img src={preview} style={S.previewImg} alt="preview" />
            : (
              <div style={S.hint}>
                拖曳草圖到此處<br />
                或點擊選擇檔案
              </div>
            )
          }
        </div>
        <input
          ref={inputRef} type="file" accept="image/*"
          style={{ display: 'none' }}
          onChange={(e) => handleFile(e.target.files[0])}
        />

        <div>
          <label style={S.label}>你的問題</label>
          <textarea
            style={S.textarea}
            placeholder={PLACEHOLDER_QUESTIONS[Math.floor(Math.random() * PLACEHOLDER_QUESTIONS.length)]}
            value={question}
            onChange={(e) => { setQuestion(e.target.value); sessionStorage.setItem('compose_question', e.target.value) }}
          />
        </div>

        <button
          style={{ ...S.btn, ...(canSubmit ? {} : S.btnDisabled) }}
          disabled={!canSubmit}
          onClick={onSubmit}
        >
          {loading ? '分析中...' : '生成意見 + 參考圖'}
        </button>
        {error && <p style={S.error}>{error}</p>}
      </div>

      {/* ── 右：輸出 ── */}
      <div style={S.right}>
        {loading && (
          <div style={S.loading}>
            <div style={S.spinner} />
            <div style={{ width: '100%', maxWidth: 300, background: 'var(--border)', height: 6, borderRadius: 3, overflow: 'hidden', marginTop: 12 }}>
              <div style={{ width: `${progress}%`, background: 'var(--accent)', height: '100%', transition: 'width 0.4s ease-out' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', maxWidth: 300, marginTop: 4 }}>
               <span style={{ fontWeight: 600 }}>
                 {progress < 80 ? 'Step 1: AI 正在讀取並分析草圖內容...' : 
                  progress < 95 ? 'Step 2: AI 正在畫出參考圖 (ComfyUI)...' : 
                  'Step 3: 正在整理最後建議...'}
               </span>
               <span>{Math.round(progress)}%</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 8, display: 'flex', gap: 12 }}>
               <span>已耗時: {elapsed}s</span>
               <span>預計總需: 15-25s (7b 模型)</span>
            </div>
          </div>
        )}

        {!loading && result && (
          <>
            {/* 草稿 vs 生成參考圖 */}
            <div>
              <p style={S.sectionLabel}>草稿 → AI 參考圖</p>
              <div style={S.imgRow}>
                <div style={S.imgHalf}>
                  <img src={preview} style={{ ...S.resultImg }} alt="original" />
                </div>
                <div style={S.imgHalf}>
                  <img
                    src={`data:image/png;base64,${result.image}`}
                    style={S.resultImg}
                    alt="generated reference"
                  />
                </div>
              </div>
              <button style={{ ...S.btnSecondary, marginTop: 8 }} onClick={downloadResult}>
                下載參考圖
              </button>
            </div>

            {/* SDXL prompt */}
            <div>
              <p style={S.sectionLabel}>Ollama 生成的 SDXL Prompt</p>
              <div style={S.promptPill}>{result.suggested_prompt}</div>
            </div>

            {/* Advice */}
            <div>
              <p style={S.sectionLabel}>構圖意見</p>
              <div style={S.adviceCard}>{result.advice}</div>
            </div>
          </>
        )}

        {!loading && !result && (
          <>
            <div style={S.resultImgPlaceholder}>參考圖將顯示於此</div>
            <div style={S.advicePlaceholder}>構圖意見將顯示於此</div>
          </>
        )}
      </div>
    </div>
  )
}
