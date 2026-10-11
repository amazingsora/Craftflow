// 角色詳情頁的純呈現元件：生成面板（主版本／變體共用）、耗時表、圖片磚
import { S } from './characterTabStyles.js'
import { UI } from './sharedStyles.js'
import { Icon } from './Icon.jsx'
import { Switch, Slider, Kbd } from './ui.jsx'
import { Spinner } from './characterTabParts.jsx'
import { GenerationInfo } from './GenerationInfo.jsx'

const TIMING_COLORS = ['var(--faint)', 'var(--tint-purple-fg)', 'var(--tint-blue-fg)', 'var(--tint-amber-fg)', 'var(--tint-green-fg)', 'var(--muted)', 'var(--accent)']
// 「其他」＝總計扣掉這些已列項目（與原本兩處計算一致）
const OTHER_BASE_KEYS = ['vision_extract', 'body_coverage', 'compile_prompt', 'compile_ai_prompt', 'canvas_expand', 'upload', 'comfyui']

export function TimingTable({ timings }) {
  if (!timings) return null
  const m = timings.models || {}
  const rows = [
    timings.vision_extract    != null && ['視覺分析', m.vision, timings.vision_extract],
    timings.body_coverage     != null && ['姿態偵測', m.vision, timings.body_coverage],
    timings.compile_prompt    != null && ['提示詞編譯', m.text, timings.compile_prompt],
    timings.compile_ai_prompt != null && ['AI提示詞', m.text, timings.compile_ai_prompt],
    timings.canvas_expand     != null && ['Canvas Expand', m.canvas_expand || m.workflow, timings.canvas_expand],
    timings.pass1             != null && ['Pass 1 粗稿', m.workflow, timings.pass1],
    timings.upload            != null && ['圖片上傳', null, timings.upload],
    timings.comfyui           != null && ['ComfyUI 生成', m.workflow, timings.comfyui],
  ].filter(Boolean)
  const sum = OTHER_BASE_KEYS.reduce((a, k) => a + (timings[k] ?? 0), 0)
  const other = Math.round((timings.total - sum) * 10) / 10
  if (other > 0.5) rows.push(['其他', null, other])
  const total = Number(timings.total) || rows.reduce((a, r) => a + Number(r[2]), 0) || 1

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>
          <Icon name="timer" size={13} style={{ color: 'var(--accent)' }} />上次耗時
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>{timings.total}s</span>
      </div>
      <div style={{ display: 'flex', height: 6, gap: 1, borderRadius: 2, overflow: 'hidden', marginBottom: 8, background: 'var(--border)' }}>
        {rows.map(([label, , sec], i) => (
          <span key={label} title={`${label} ${sec}s`} style={{ width: `${(Number(sec) / total) * 100}%`, background: TIMING_COLORS[i % TIMING_COLORS.length] }} />
        ))}
      </div>
      <div>
        {rows.map(([label, model, sec], i) => (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12, padding: '3px 0', borderTop: '1px dashed var(--border)' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 7, color: 'var(--text-2)', minWidth: 0 }}>
              <i style={{ width: 7, height: 7, borderRadius: 1, flexShrink: 0, background: TIMING_COLORS[i % TIMING_COLORS.length] }} />
              <span style={{ whiteSpace: 'nowrap' }}>{label}</span>
              {model && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{model}</span>}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{sec}s</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// 生成人設圖面板；各旋鈕以 {enabled, onEnabled, value, onValue} 傳入，主版本與變體共用
export function GenInspector({
  count, max = 8, family, caps, ipa, cn, fd,
  seed, onSeed, lastSeed, onUseLastSeed, reusePrompt, onReusePrompt,
  generating, onGenerate, timings,
}) {
  const { ipaSupported, ipaHint, cnUsable, cnLabel, cnHint, faceDetailerSupported } = caps
  const sec = { display: 'flex', flexDirection: 'column', gap: 10, padding: '12px 14px', borderBottom: '1px solid var(--border)' }
  return (
    <aside style={S.inspector} aria-label="生成人設圖">
      <div style={S.inspectorHead}>
        <span style={S.inspectorTitle}>生成人設圖</span>
        <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {family && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, padding: '2px 6px', borderRadius: 3, border: '1px solid var(--border-strong)', color: 'var(--text-2)' }}>{family}</span>}
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--muted)' }}>{count}/{max}</span>
        </span>
      </div>

      <div style={sec}>
        {ipaSupported
          ? <Switch label="概念圖參考" sub="IP-Adapter" checked={ipa.enabled} onChange={ipa.onEnabled} />
          : <Switch label="概念圖參考" sub="不支援" checked={false} disabled title={ipaHint} />}
        {ipaSupported && ipa.enabled && (
          <Slider label="強度" value={ipa.value} min={0.1} max={1.5} step={0.05} minLabel="0.1" maxLabel="1.5" format={v => v.toFixed(2)} onChange={ipa.onValue} />
        )}
      </div>

      {cnUsable && (
        <div style={sec} title={cnHint}>
          <Switch label="結構控制" sub={cnLabel} checked={cn.enabled} onChange={cn.onEnabled} />
          {cn.enabled && (
            <Slider label="強度" value={cn.value} min={0.1} max={1.5} step={0.05} minLabel="0.1" maxLabel="1.5" format={v => v.toFixed(2)} onChange={cn.onValue} />
          )}
        </div>
      )}

      {faceDetailerSupported && (
        <div style={sec} title="生成後以 FaceDetailer 重繪臉部">
          <Switch label="增強臉部輪廓" sub="FaceDetailer" checked={fd.enabled} onChange={fd.onEnabled} />
          {fd.enabled && (
            <Slider label="重繪幅度" value={fd.value} min={0.2} max={0.7} step={0.05} minLabel="0.2" maxLabel="0.7" format={v => v.toFixed(2)} onChange={fd.onValue}
              title="修臉重繪幅度（denoise）：低＝保留原臉只補細節；高＝重畫臉型五官，過高會與身體畫風脫節" />
          )}
        </div>
      )}

      {/* seed：-1＝隨機；固定 seed＋「沿用 prompt」可重現同一張圖 */}
      <div style={sec}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontSize: 12, color: 'var(--text-2)' }}>Seed</span>
          <span style={{ fontSize: 11, color: 'var(--faint)' }}>-1 = 隨機</span>
        </div>
        <input
          type="number" value={seed}
          title="-1 = 每次隨機（預設）；填入非負整數則固定 seed，供比較調整效果"
          style={{ ...UI.input, fontFamily: 'var(--font-mono)', fontSize: 13 }}
          onChange={e => onSeed(e.target.value === '' ? -1 : Number(e.target.value))}
        />
        {lastSeed != null && (
          <button style={{ ...UI.btnSm, justifyContent: 'flex-start' }}
            title="把上次實際使用的 seed 填入輸入框，供下次生成沿用"
            onClick={onUseLastSeed}>
            <Icon name="history" size={13} />沿用上次 seed <span className="cf-num" style={{ color: 'var(--muted)' }}>{lastSeed}</span>
          </button>
        )}
        <label title="連同 seed 一起沿用上次生成的 prompt，不重新編譯（只固定 seed 不夠，LLM 每次翻譯結果仍可能不同）"
          style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--text-2)', cursor: 'pointer', userSelect: 'none' }}>
          <input type="checkbox" checked={!!reusePrompt} onChange={e => onReusePrompt(e.target.checked)} />
          沿用上次 prompt
        </label>
      </div>

      {timings && <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)' }}><TimingTable timings={timings} /></div>}

      <div style={{ ...S.inspectorFoot, borderTop: 'none' }}>
        <button
          style={{ ...UI.btnPrimary, width: '100%', height: 40, ...(generating ? { opacity: .75, cursor: 'wait' } : {}) }}
          disabled={generating}
          onClick={onGenerate}
        >
          {generating
            ? <><span style={S.spinner} />生成中…</>
            : <><Icon name="sparkles" size={15} />生成人設圖</>}
        </button>
      </div>
    </aside>
  )
}

// 待確認的生成結果（一次一張）
export function PendingCard({ item, total, onZoom, saveLabel, saveDisabled, saving, onSave, onDiscard, onDiscardAll, discardDisabled }) {
  return (
    <div style={{ ...UI.panel, overflow: 'hidden', borderColor: 'var(--accent-border)', boxShadow: '0 0 0 3px var(--accent-soft)', animation: 'cf-pop .3s var(--ease) both' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: '1px solid var(--border)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--accent)', fontWeight: 600, minWidth: 0 }}>
          <Icon name="sparkles" size={13} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.label}</span>
        </span>
        <span style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>待確認 <span className="cf-num">{total}</span> 張</span>
      </div>
      <div style={{ background: 'var(--canvas)', display: 'flex', justifyContent: 'center' }}>
        <img src={item.url} alt={item.label} title="點擊放大" onClick={onZoom}
          style={{ display: 'block', width: '100%', aspectRatio: '2 / 3', objectFit: 'contain', cursor: 'zoom-in' }} />
      </div>
      <div style={{ display: 'flex', gap: 6, padding: 10 }}>
        <button style={{ ...UI.btnPrimary, flex: 1, padding: '8px 0', fontSize: 13 }} disabled={saveDisabled} onClick={onSave}>
          {saving ? <><span style={S.spinner} />儲存中…</> : <><Icon name="check" size={14} />{saveLabel}</>}
        </button>
        <button style={UI.btnSecondary} disabled={discardDisabled} onClick={onDiscard}>捨棄</button>
        {onDiscardAll && total > 1 && (
          <button style={{ ...UI.btnSecondary, color: 'var(--danger)' }} onClick={onDiscardAll}>全捨棄</button>
        )}
      </div>
    </div>
  )
}

// 已儲存圖片磚：2:3 不裁切，hover 顯示操作
export function ImageTile({ src, alt, index, downloadHref, downloadName, onZoom, confirming, onAskDelete, onConfirmDelete, onCancelDelete, infoPath, selected }) {
  const overlayBtn = {
    width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: 'var(--r-sm)',
    background: 'rgba(13,17,23,.66)', color: '#fff', border: 'none', cursor: 'pointer', backdropFilter: 'blur(6px)', textDecoration: 'none',
  }
  return (
    <div style={{ minWidth: 0 }}>
      <div className="cf-hover-parent" style={{
        position: 'relative', borderRadius: 'var(--r)', overflow: 'hidden', background: 'var(--canvas)',
        boxShadow: selected ? '0 0 0 2px var(--accent)' : '0 0 0 1px var(--border)',
      }}>
        <img src={src} alt={alt} title="點擊放大" onClick={onZoom} className="cf-card-img"
          style={{ display: 'block', width: '100%', aspectRatio: '2 / 3', objectFit: 'cover', objectPosition: 'center top', cursor: 'zoom-in' }} />
        {index != null && (
          <span style={{ position: 'absolute', left: 6, top: 6, fontFamily: 'var(--font-mono)', fontSize: 10, padding: '1px 5px', borderRadius: 3, background: 'rgba(13,17,23,.6)', color: '#fff' }}>
            {String(index + 1).padStart(2, '0')}
          </span>
        )}
        {confirming
          ? <div style={{ position: 'absolute', inset: 0, background: 'rgba(13,17,23,.78)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: '#fff' }}>確認移除？</span>
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={onConfirmDelete} style={{ ...UI.btnSm, background: 'var(--danger)', borderColor: 'transparent', color: '#fff' }}>移除</button>
                <button onClick={onCancelDelete} style={UI.btnSm}>取消</button>
              </div>
            </div>
          : <div className="cf-reveal" style={{ position: 'absolute', right: 6, top: 6, display: 'flex', gap: 4 }}>
              {downloadHref && (
                <a href={downloadHref} download={downloadName} style={overlayBtn} title="下載" aria-label="下載"><Icon name="download" size={14} /></a>
              )}
              <button onClick={onAskDelete} style={overlayBtn} title="移除" aria-label="移除"><Icon name="trash-2" size={14} /></button>
            </div>
        }
      </div>
      {infoPath && <GenerationInfo fetchPath={infoPath} />}
    </div>
  )
}

// 概念圖方磚（上傳入口與已上傳圖共用樣式）
export function ConceptSlot({ children, onClick, htmlFor, as = 'div', add = false }) {
  const Tag = as
  return (
    <Tag
      htmlFor={htmlFor}
      onClick={onClick}
      className={add ? 'cf-drop' : 'cf-hover-parent'}
      style={{
        position: 'relative', aspectRatio: '1 / 1', borderRadius: 'var(--r)', overflow: 'hidden',
        background: add ? 'var(--surface-2)' : 'var(--canvas)',
        border: add ? '1px dashed var(--border-strong)' : 'none',
        boxShadow: add ? 'none' : '0 0 0 1px var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: add ? 'pointer' : 'default', color: 'var(--muted)',
        transition: 'border-color .15s, color .15s',
      }}
    >
      {children}
    </Tag>
  )
}

// 已上傳概念圖磚：main 標記／參與生成切換／刪除（主版本與變體共用） [CN-132]
export function ConceptTile({ src, idx, isMain, enabled, confirming, onZoom, onAskDelete, onConfirmDelete, onCancelDelete, onSetMain, onToggle }) {
  const chip = {
    position: 'absolute', height: 22, display: 'flex', alignItems: 'center', gap: 3, padding: '0 6px',
    borderRadius: 'var(--r-sm)', border: 'none', background: 'rgba(13,17,23,.66)', color: '#fff',
    fontSize: 10.5, lineHeight: 1, cursor: 'pointer', whiteSpace: 'nowrap',
  }
  return (
    <ConceptSlot>
      <img src={src} alt={`概念圖${idx + 1}`} title="點擊放大" onClick={onZoom}
        style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center top', cursor: 'zoom-in', opacity: enabled ? 1 : 0.35, transition: 'opacity .15s' }} />
      {isMain
        ? <span title="IPA／CN／外擴用這張" style={{ ...chip, left: 4, top: 4, cursor: 'default', fontWeight: 600, background: 'var(--accent)', color: 'var(--accent-contrast)' }}>MAIN</span>
        : <>
            <button className="cf-reveal" onClick={onSetMain} title="設為 main（IPA／CN／外擴用這張）" style={{ ...chip, left: 4, top: 4 }}>
              <Icon name="flag" size={11} />設為 main
            </button>
            <button onClick={onToggle} aria-pressed={enabled} title={enabled ? '參與生成（點擊排除）' : '不參與生成（點擊加入）'} style={{ ...chip, left: 4, bottom: 4 }}>
              <Icon name={enabled ? 'eye' : 'eye-off'} size={11} />{enabled ? '參與' : '不參與'}
            </button>
          </>
      }
      {confirming
        ? <div style={{ position: 'absolute', inset: 0, background: 'rgba(13,17,23,.78)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            <span style={{ fontSize: 11.5, color: '#fff' }}>確認刪除？</span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button onClick={onConfirmDelete} style={{ ...UI.btnSm, padding: '3px 8px', background: 'var(--danger)', borderColor: 'transparent', color: '#fff' }}>刪除</button>
              <button onClick={onCancelDelete} style={{ ...UI.btnSm, padding: '3px 8px' }}>取消</button>
            </div>
          </div>
        : <button
            className="cf-reveal"
            onClick={onAskDelete}
            title="刪除" aria-label="刪除概念圖"
            style={{ position: 'absolute', top: 4, right: 4, width: 22, height: 22, borderRadius: 'var(--r-sm)', border: 'none', background: 'rgba(13,17,23,.66)', color: '#fff', cursor: 'pointer', display: 'grid', placeItems: 'center', padding: 0 }}
          ><Icon name="x" size={13} /></button>
      }
    </ConceptSlot>
  )
}

// ── AI 整理資訊 ──────────────────────────────────────────────────────────────
// AI 摘要的極簡 markdown：## 標題、- 清單、**粗體**；其餘原樣（不引入 markdown 套件）
function inlineBold(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((seg, i) =>
    /^\*\*[^*]+\*\*$/.test(seg) ? <strong key={i} style={{ color: 'var(--text)', fontWeight: 600 }}>{seg.slice(2, -2)}</strong> : seg)
}

function renderSummary(text) {
  const out = []
  let list = []
  const flush = () => {
    if (!list.length) return
    out.push(<ul key={`ul${out.length}`} style={{ margin: '2px 0 4px', paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 3 }}>{list}</ul>)
    list = []
  }
  String(text).split('\n').forEach((raw, i) => {
    const line = raw.trim()
    if (/^#{1,6}\s+/.test(line)) {
      flush()
      out.push(<h4 key={i} style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', letterSpacing: '.02em', margin: out.length ? '14px 0 6px' : '0 0 6px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 3, height: 12, borderRadius: 2, background: 'var(--accent)', flexShrink: 0 }} />{line.replace(/^#{1,6}\s+/, '')}
      </h4>)
    } else if (/^[-*・]\s+/.test(line)) {
      list.push(<li key={i} style={{ lineHeight: 1.7 }}>{inlineBold(line.replace(/^[-*・]\s+/, ''))}</li>)
    } else if (line) {
      flush()
      out.push(<p key={i} style={{ lineHeight: 1.75, margin: '0 0 4px' }}>{inlineBold(line)}</p>)
    }
  })
  flush()
  return out
}

// AI 整理資訊卡；onHide＝整欄隱藏（顯示鈕在「角色資料」標題列）
export function SummaryCard({ text, busy, onRefresh, onHide, placeholder }) {
  return (
    <section style={{ ...UI.panel, overflow: 'hidden' }} aria-label="AI 整理資訊">
      <header style={{ display: 'flex', alignItems: 'center', gap: 4, minHeight: 44, padding: '6px 8px 6px 14px', borderBottom: '1px solid var(--border)', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
        <Icon name="sparkles" size={14} style={{ color: 'var(--accent)', marginRight: 4 }} />
        <h3 style={{ fontSize: 13, fontWeight: 600, flex: 1 }}>AI 整理資訊</h3>
        <button style={UI.btnGhost} onClick={onRefresh} disabled={busy}>
          {busy ? <><Spinner />整理中…</> : <><Icon name="refresh-cw" size={13} />重新整理</>}
        </button>
        {onHide && (
          <button style={UI.btnGhost} onClick={onHide} title="隱藏 AI 整理資訊" aria-label="隱藏 AI 整理資訊">
            <Icon name="eye-off" size={13} />隱藏
          </button>
        )}
      </header>
      {text
        ? <div style={{ padding: '14px 16px 16px', fontSize: 13.5, color: 'var(--text-2)' }}>{renderSummary(text)}</div>
        : <div style={{ ...S.summaryPlaceholder, border: 'none', borderRadius: 0 }}>{placeholder}</div>}
    </section>
  )
}

export { Kbd }
