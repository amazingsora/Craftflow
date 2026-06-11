import { useState, useRef } from 'react'

const S = {
  root: { display: 'flex', gap: 24, alignItems: 'flex-start' },
  panel: { flex: 1, display: 'flex', flexDirection: 'column', gap: 12 },
  dropzone: {
    border: '2px dashed var(--border)',
    borderRadius: 12,
    minHeight: 280,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    overflow: 'hidden',
    background: 'var(--surface)',
    transition: 'border-color .2s',
  },
  dropzoneActive: { borderColor: 'var(--accent)' },
  previewImg: { width: '100%', height: '100%', objectFit: 'contain', maxHeight: 400 },
  hint: { color: 'var(--muted)', textAlign: 'center', padding: 24, lineHeight: 2 },
  btn: {
    padding: '10px 0',
    borderRadius: 8,
    border: 'none',
    background: 'var(--accent)',
    color: 'var(--accent-contrast)',
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background .2s',
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
  error: { color: 'var(--danger)', fontSize: 13, marginTop: 4 },
  label: { fontSize: 12, color: 'var(--muted)', marginBottom: 2 },
}

export default function ProcessTab({ onAddHistory }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef()

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

  const onProcess = async () => {
    if (!file || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const body = new FormData()
      body.append('file', file)
      const resp = await fetch('/api/v1/art/lineart', { method: 'POST', body })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }))
        throw new Error(err.detail)
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      setResult(url)
      onAddHistory?.({
        type: 'process',
        url,
        filename: `lineart_${Date.now()}.png`,
        label: file.name,
      })
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const download = () => {
    const a = document.createElement('a')
    a.href = result
    a.download = `lineart_${Date.now()}.png`
    a.click()
  }

  const dzStyle = { ...S.dropzone, ...(dragging ? S.dropzoneActive : {}) }

  return (
    <div style={S.root}>
      {/* ── 左：輸入 ── */}
      <div style={S.panel}>
        <p style={S.label}>上傳草稿圖</p>
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
                拖曳草稿到此處<br />
                或點擊選擇檔案<br />
                <span style={{ fontSize: 12 }}>支援 JPG / PNG / WebP</span>
              </div>
            )
          }
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(e) => handleFile(e.target.files[0])}
        />
        <button
          style={{ ...S.btn, ...(!file || loading ? S.btnDisabled : {}) }}
          disabled={!file || loading}
          onClick={onProcess}
        >
          {loading ? '處理中...' : '生成線稿'}
        </button>
        {error && <p style={S.error}>{error}</p>}
      </div>

      {/* ── 右：輸出 ── */}
      <div style={S.panel}>
        <p style={S.label}>生成結果</p>
        {loading && (
          <div style={S.loading}>
            <div style={S.spinner} />
            <span>ComfyUI 處理中，通常需要 30–90 秒...</span>
          </div>
        )}
        {!loading && result && (
          <>
            <img src={result} style={{ width: '100%', borderRadius: 12 }} alt="lineart result" />
            <button style={S.btnSecondary} onClick={download}>下載圖片</button>
          </>
        )}
        {!loading && !result && (
          <div style={S.empty}>
            <span>生成結果將顯示於此</span>
          </div>
        )}
      </div>
    </div>
  )
}
