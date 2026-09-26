import { useState, useEffect } from 'react'

// 縮圖：整張塞進 box（等比例、不裁切），點擊開原尺寸檢視
export function FitImage({ src, alt = '', maxHeight = '60vh', style = {} }) {
  const [open, setOpen] = useState(false)
  if (!src) return null
  return (
    <>
      <img
        src={src}
        alt={alt}
        title="點擊檢視原圖"
        onClick={() => setOpen(true)}
        style={{
          width: '100%', height: maxHeight, objectFit: 'contain', display: 'block',
          borderRadius: 12, background: 'var(--surface-2)', cursor: 'zoom-in', ...style,
        }}
      />
      {open && <ImageLightbox src={src} alt={alt} onClose={() => setOpen(false)} />}
    </>
  )
}

// 原尺寸檢視：超過視窗可捲動；點背景或按 Esc 關閉
export function ImageLightbox({ src, alt = '', onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.85)',
        overflow: 'auto', display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        padding: 24, cursor: 'zoom-out',
      }}
    >
      <img src={src} alt={alt} style={{ maxWidth: 'none', display: 'block', margin: 'auto' }} />
    </div>
  )
}

// 極簡 inline markdown：**粗體** 與行首 # 標題轉粗體，其餘原樣（避免引入 markdown 套件）
export function renderInlineMd(text) {
  return String(text || '').split('\n').map((line, li, arr) => {
    const heading = /^#{1,6}\s+/.test(line)
    const body = line.replace(/^#{1,6}\s+/, '')
    const parts = body.split(/(\*\*[^*]+\*\*)/g).map((seg, i) =>
      /^\*\*[^*]+\*\*$/.test(seg) ? <strong key={i}>{seg.slice(2, -2)}</strong> : seg
    )
    return (
      <span key={li}>
        {heading ? <strong>{parts}</strong> : parts}
        {li < arr.length - 1 ? '\n' : ''}
      </span>
    )
  })
}
