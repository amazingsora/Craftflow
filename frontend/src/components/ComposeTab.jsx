import { useState, useRef, useEffect } from 'react'
import CapabilityNotice from './CapabilityNotice'
import { FitImage, renderInlineMd } from './ImageViewer'
import { UI } from './sharedStyles'
import { Icon } from './Icon.jsx'
import { Panel, FieldHead, Switch, Slider, Empty, Progress } from './ui.jsx'

const S = {
  root: { display: 'grid', gap: 24, alignItems: 'start', '--split-left': 'minmax(320px, 400px)' },   // 欄寬見 index.css .cf-split
  left: { display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 },
  right: { display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 },
  dropzone: { ...UI.dropzone, minHeight: 240 },
  dropzoneActive: UI.dropzoneActive,
  previewImg: { width: '100%', objectFit: 'contain', maxHeight: 300, display: 'block' },
  hint: { color: 'var(--muted)', textAlign: 'center', padding: 20, lineHeight: 1.8, fontSize: 13, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 },
  label: UI.label,
  textarea: { ...UI.textarea, minHeight: 96 },
  btn: UI.btnPrimary,
  btnDisabled: UI.btnDisabled,
  btnSecondary: UI.btnSm,
  error: { ...UI.error, padding: '8px 10px', borderRadius: 'var(--r)', background: 'var(--tint-red-bg)' },
  sub: { fontSize: 12, color: 'var(--muted)', lineHeight: 1.6 },
  adviceCard: { fontSize: 14, lineHeight: 1.9, color: 'var(--text)', whiteSpace: 'pre-wrap' },
  promptPill: {
    fontFamily: 'var(--font-mono)', background: 'var(--code-bg)', border: '1px solid var(--border)',
    borderRadius: 'var(--r)', padding: '10px 12px', fontSize: 12, color: 'var(--code-fg)',
    wordBreak: 'break-word', lineHeight: 1.7,
  },
  sectionLabel: UI.sectionLabel,
  modelBadge: {
    fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-2)',
    background: 'var(--surface-2)', border: '1px solid var(--border)',
    borderRadius: 'var(--r-sm)', padding: '1px 6px', display: 'inline-block',
  },
  loading: { ...UI.loading, padding: 0, width: '100%', maxWidth: 340 },
  spinner: UI.spinner,
  imgRow: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: 'var(--border)' },
  imgHalf: { minWidth: 0, background: 'var(--canvas)', padding: 16, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' },
  imgCap: { alignSelf: 'flex-start', fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '.06em', color: 'var(--muted)', textTransform: 'uppercase' },
}

const PLACEHOLDER_QUESTIONS = [
  '如果把視角改成俯視，構圖會如何變化？',
  '這個場景改成夜晚光源，氣氛會怎麼不同？',
  '主角位置太居中，怎麼調整讓畫面更有張力？',
]

export default function ComposeTab({ onAddHistory, activeVisionModel, capability = { ipa_supported: true, cn_supported: true }, onSendToGenerate }) {
  const ipaSupported = capability.ipa_supported
  const cnSupported  = capability.cn_supported
  // cnFallback 有值時控制項仍可用，後端改走替代路徑
  const cnFallback = capability.cn_fallback || null
  const cnUsable   = cnSupported || !!cnFallback

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

  // ControlNet
  const [cnEnabled, setCnEnabled] = useState(false)
  const [cnWeight, setCnWeight] = useState(0.85)

  // IP-Adapter 角色外觀參考
  const [ipaEnabled, setIpaEnabled] = useState(false)
  useEffect(() => {
    if (!ipaSupported) setIpaEnabled(false)
  }, [ipaSupported])
  const [ipaWeight, setIpaWeight] = useState(0.6)

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
    if (!file || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    startProgress()

    try {
      const body = new FormData()
      body.append('file', file)
      if (question.trim()) body.append('question', question.trim())
      if (ipaSupported && ipaEnabled) {
        body.append('use_sketch_as_ref', 'true')
        body.append('ipa_weight', String(ipaWeight))
      }
      if (cnUsable && cnEnabled) {
        body.append('use_cn', 'true')
        body.append('cn_weight', String(cnWeight))
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

  const canSubmit = file && !loading
  const dzStyle = { ...S.dropzone, ...(dragging ? S.dropzoneActive : {}) }

  return (
    <div style={S.root} className="cf-split">
      {/* ── 左：輸入 ── */}
      <div style={S.left}>
        <Panel index="01" title="上傳草圖" icon="upload">
          <div
            className="cf-drop"
            style={dzStyle}
            onDrop={onDrop}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onClick={() => inputRef.current.click()}
          >
            {preview
              ? <img src={preview} style={S.previewImg} alt="草圖預覽" />
              : (
                <div style={S.hint}>
                  <Icon name="image-plus" size={22} />
                  <span>拖曳草圖到此處<br />或點擊選擇檔案</span>
                </div>
              )
            }
          </div>
          <input
            ref={inputRef} type="file" accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => handleFile(e.target.files[0])}
          />
        </Panel>

        <Panel index="02" title="引導" icon="sliders-horizontal">
          {/* IP-Adapter 角色外觀參考；不支援時顯示原因＋替代方案 */}
          {!ipaSupported && (
            <CapabilityNotice title="角色外觀參考" kind="ipa" family={capability.family} />
          )}
          {ipaSupported && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <Switch label="角色外觀參考" sub="IP-Adapter" checked={ipaEnabled} onChange={() => setIpaEnabled(v => !v)} />
              {ipaEnabled && (
                <>
                  <div style={S.sub}>以草圖本身作為外觀參考，生成有色彩的構圖版本。</div>
                  <Slider label="參考強度" hint="0.6 建議起點" value={ipaWeight} min={0.1} max={1.5} step={0.05}
                    minLabel="0.1" maxLabel="1.5" format={v => v.toFixed(2)} onChange={setIpaWeight} />
                </>
              )}
            </div>
          )}

          <div style={{ height: 1, background: 'var(--border)', margin: '0 -14px' }} />

          {/* 草圖引導。cnUsable 涵蓋「原生 CN」與「img2img 替代」；兩者皆無才顯示不支援卡片 */}
          {!cnUsable && (
            <CapabilityNotice title="草圖線稿引導" kind="cn" family={capability.family} fallback={cnFallback} />
          )}
          {cnUsable && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <Switch label={cnSupported ? '草圖線稿引導' : '構圖引導'} sub={cnSupported ? 'ControlNet' : 'img2img'} checked={cnEnabled} onChange={() => setCnEnabled(v => !v)} />
              {cnEnabled && (
                <>
                  <div style={S.sub}>以草圖線稿引導生圖構圖，強度越高越貼近草圖姿勢。</div>
                  <Slider label="引導強度" hint="0.85 建議起點" value={cnWeight} min={0.1} max={1.5} step={0.05}
                    minLabel="0.1" maxLabel="1.5" format={v => v.toFixed(2)} onChange={setCnWeight} />
                </>
              )}
            </div>
          )}
        </Panel>

        <Panel index="03" title="提問" icon="messages-square">
          <div>
            <FieldHead label="你的問題" hint="選填，空白則 AI 自動分析" />
            <textarea
              style={S.textarea}
              placeholder={PLACEHOLDER_QUESTIONS[Math.floor(Math.random() * PLACEHOLDER_QUESTIONS.length)]}
              value={question}
              onChange={(e) => { setQuestion(e.target.value); sessionStorage.setItem('compose_question', e.target.value) }}
            />
          </div>
          {activeVisionModel && (
            <div style={S.sub}>
              視覺模型 <span style={S.modelBadge}>{activeVisionModel}</span>
              <span style={{ marginLeft: 6, color: 'var(--faint)' }}>於「設定」切換</span>
            </div>
          )}
        </Panel>

        {error && <p style={S.error}>{error}</p>}
        <button
          style={{ ...S.btn, height: 42, ...(canSubmit ? {} : S.btnDisabled) }}
          disabled={!canSubmit}
          onClick={onSubmit}
        >
          {loading
            ? <><span style={{ width: 14, height: 14, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin .8s linear infinite' }} />分析中 {elapsed}s</>
            : <><Icon name="sparkles" size={15} />生成意見 + 參考圖</>}
        </button>
      </div>

      {/* ── 右：輸出 ── */}
      <div style={S.right}>
        <Panel
          title="草稿 → AI 參考圖" icon="image" flush
          actions={!loading && result ? <button style={S.btnSecondary} onClick={downloadResult}><Icon name="download" size={13} />下載參考圖</button> : null}
        >
          {loading && (
            <div className="cf-dotgrid" style={{ minHeight: 420, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--canvas)' }}>
              <div style={S.loading}>
                <div style={S.spinner} />
                <div style={{ width: '100%', marginTop: 8 }}><Progress /></div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>AI 分析草圖 + ComfyUI 生成參考圖…</div>
                <div style={{ fontSize: 11.5, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>已耗時 {elapsed}s（通常 15–25s）</div>
              </div>
            </div>
          )}
          {!loading && result && (
            <div style={S.imgRow}>
              <div style={S.imgHalf}>
                <span style={S.imgCap}>Sketch</span>
                <FitImage src={preview} alt="原始草圖" maxHeight="min(60vh, 560px)" />
              </div>
              <div style={S.imgHalf}>
                <span style={S.imgCap}>AI Reference</span>
                <FitImage src={`data:image/png;base64,${result.image}`} alt="AI 參考圖" maxHeight="min(60vh, 560px)" />
              </div>
            </div>
          )}
          {!loading && !result && (
            <div className="cf-dotgrid" style={{ backgroundColor: 'var(--canvas)', padding: 24 }}>
              <Empty icon="image" title="參考圖將顯示於此" style={{ background: 'transparent', border: 'none', minHeight: 300 }}>
                上傳草圖後按「生成意見 + 參考圖」
              </Empty>
            </div>
          )}
        </Panel>

        {!loading && result && (
          <Panel
            title={<>Ollama 生成的 Prompt{result.style ? <span style={{ ...S.modelBadge, marginLeft: 8 }}>{String(result.style).toUpperCase()}</span> : null}{result.mechanism ? <span style={{ ...S.modelBadge, marginLeft: 6 }}>引導 {result.mechanism}</span> : null}</>}
            icon="pen-line"
            actions={onSendToGenerate ? (
              <button
                style={{ ...UI.btnSm, color: 'var(--accent)', borderColor: 'var(--accent-border)', background: 'var(--accent-soft)' }}
                onClick={() => onSendToGenerate(question.trim())}
                title="將此次問題描述帶入文字→生圖 Tab"
              ><Icon name="arrow-right" size={13} />送到生圖</button>
            ) : null}
          >
            <div style={S.promptPill}>{result.suggested_prompt}</div>
          </Panel>
        )}

        <Panel title="構圖意見" icon="messages-square">
          {!loading && result
            ? <div style={S.adviceCard}>{renderInlineMd(result.advice)}</div>
            : <div style={{ ...S.sub, padding: '14px 0', textAlign: 'center' }}>構圖意見將顯示於此</div>}
        </Panel>
      </div>
    </div>
  )
}
