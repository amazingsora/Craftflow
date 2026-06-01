import { useState, useRef, useEffect } from 'react'

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
  modelBadge: {
    fontSize: 11, color: 'var(--muted)',
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    padding: '4px 8px',
    display: 'inline-block',
  },
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

export default function ComposeTab({ onAddHistory, activeVisionModel, ipaSupported = true, onSendToGenerate }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [question, setQuestion] = useState(() => sessionStorage.getItem('compose_question') ?? '')
  const [result, setResult] = useState(null)   // { advice, suggested_prompt, image (b64), seed }
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef()
  const elapsedTimer = useRef()

  // IP-Adapter 角色外觀參考
  const [ipaEnabled, setIpaEnabled] = useState(false)
  useEffect(() => {
    if (!ipaSupported) setIpaEnabled(false)
  }, [ipaSupported])
  const [ipaFile, setIpaFile] = useState(null)
  const [ipaPreview, setIpaPreview] = useState(null)
  const [ipaWeight, setIpaWeight] = useState(0.6)
  const [ipaDragging, setIpaDragging] = useState(false)
  const ipaInputRef = useRef()

  const handleIpaFile = (f) => {
    if (!f || !f.type.startsWith('image/')) return
    setIpaFile(f)
    setIpaPreview(URL.createObjectURL(f))
  }

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
    setElapsed(0)
    clearInterval(elapsedTimer.current)
    elapsedTimer.current = setInterval(() => setElapsed(old => old + 1), 1000)
  }

  const stopProgress = () => {
    clearInterval(elapsedTimer.current)
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
      if (ipaEnabled) {
        body.append('use_sketch_as_ref', 'true')
        body.append('ipa_weight', String(ipaWeight))
        // 備用：若未來恢復外部角色參考圖，取消下方注釋
        // if (ipaFile) body.append('character_ref', ipaFile)
      }

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

        {/* IP-Adapter 角色外觀參考 */}
        <div style={{
          border: '1px solid var(--border)', borderRadius: 10,
          padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
              角色外觀參考
              {!ipaSupported && (
                <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 400, marginLeft: 6 }}>
                  （目前 workflow 不支援 IP-Adapter）
                </span>
              )}
            </span>
            <button
              disabled={!ipaSupported}
              style={{
                fontSize: 12, padding: '3px 10px', borderRadius: 6,
                border: ipaEnabled ? 'none' : '1px solid var(--border)',
                cursor: ipaSupported ? 'pointer' : 'not-allowed',
                opacity: ipaSupported ? 1 : 0.4,
                background: ipaEnabled ? 'var(--accent)' : 'transparent',
                color: ipaEnabled ? '#fff' : 'var(--muted)',
              }}
              onClick={() => { if (ipaSupported) { setIpaEnabled(v => !v); setIpaFile(null); setIpaPreview(null) } }}
            >
              {ipaEnabled ? '已啟用' : '未啟用'}
            </button>
          </div>
          {ipaEnabled && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8 }}>
                以草圖本身作為外觀參考，生成有色彩的構圖版本。
              </div>
              <label style={{ ...S.label, marginBottom: 4 }}>
                參考強度：{ipaWeight.toFixed(2)}
                <span style={{ marginLeft: 6, opacity: 0.6 }}>（0.6 建議起點）</span>
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                <input type="range" min={0.1} max={1.5} step={0.05}
                  value={ipaWeight} style={{ flex: 1, accentColor: 'var(--accent)' }}
                  onChange={e => setIpaWeight(Number(e.target.value))} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
              </div>
            </div>
          )}
        </div>

        <div>
          <label style={S.label}>你的問題</label>
          <textarea
            style={S.textarea}
            placeholder={PLACEHOLDER_QUESTIONS[Math.floor(Math.random() * PLACEHOLDER_QUESTIONS.length)]}
            value={question}
            onChange={(e) => { setQuestion(e.target.value); sessionStorage.setItem('compose_question', e.target.value) }}
          />
        </div>

        {activeVisionModel && (
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>
            視覺模型：<span style={S.modelBadge}>{activeVisionModel}</span>
            <span style={{ marginLeft: 6, opacity: 0.6 }}>（於 ⚙ 設定切換）</span>
          </div>
        )}

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
            <div style={{ width: '100%', maxWidth: 300, background: 'var(--border)', height: 6, borderRadius: 3, overflow: 'hidden', position: 'relative', marginTop: 12 }}>
              <div style={{ position: 'absolute', height: '100%', background: 'var(--accent)', borderRadius: 3, animation: 'indeterminate 1.6s ease-in-out infinite' }} />
            </div>
            <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4 }}>AI 分析草圖 + ComfyUI 生成參考圖...</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>已耗時：{elapsed}s（通常 15-25s）</div>
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <p style={{ ...S.sectionLabel, marginBottom: 0 }}>Ollama 生成的 SDXL Prompt</p>
                {onSendToGenerate && (
                  <button
                    style={{ fontSize: 12, padding: '4px 12px', borderRadius: 6, border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontWeight: 600 }}
                    onClick={() => onSendToGenerate(question.trim())}
                    title="將此次問題描述帶入文字→生圖 Tab"
                  >→ 送到生圖</button>
                )}
              </div>
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
