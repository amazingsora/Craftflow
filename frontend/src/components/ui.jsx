// 設計系統共用元件（Console）：Panel／SectionHead／Switch／Slider／Segmented／Empty
import { UI } from './sharedStyles.js'
import { Icon } from './Icon.jsx'

// 區塊面板；index＝左上角編號（01、02…），actions＝標題列右側
export function Panel({ index, title, icon, actions, children, style, bodyStyle, flush = false }) {
  return (
    <section style={{ ...UI.panel, ...style }}>
      {title && (
        <header style={{
          display: 'flex', alignItems: 'center', gap: 8, minHeight: 44,
          padding: '8px 12px 8px 14px', borderBottom: '1px solid var(--border)',
        }}>
          {index && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)', fontWeight: 500 }}>{index}</span>}
          {icon && <Icon name={icon} size={15} style={{ color: 'var(--muted)' }} />}
          <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', flex: 1, minWidth: 0 }}>{title}</h3>
          {actions}
        </header>
      )}
      <div style={flush ? bodyStyle : { padding: 14, display: 'flex', flexDirection: 'column', gap: 14, ...bodyStyle }}>
        {children}
      </div>
    </section>
  )
}

// 欄位標題列：左 label（可帶 tag），右 actions
export function FieldHead({ label, tag, hint, children, style }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6, minHeight: 22, ...style }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
        <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{label}</span>
        {tag && <code style={{ fontSize: 10.5, color: 'var(--accent)', background: 'var(--accent-soft)', padding: '1px 5px', borderRadius: 3 }}>{tag}</code>}
        {hint && <span style={{ fontSize: 11.5, color: 'var(--faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{hint}</span>}
      </span>
      {children && <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>{children}</span>}
    </div>
  )
}

// 開關（語意為 checkbox，鍵盤可操作）
export function Switch({ checked, onChange, label, sub, disabled = false, title, style }) {
  return (
    <label title={title} className="cf-switch" style={{
      position: 'relative', display: 'flex', alignItems: 'center', gap: 10, cursor: disabled ? 'not-allowed' : 'pointer',
      userSelect: 'none', opacity: disabled ? 0.5 : 1, minWidth: 0, ...style,
    }}>
      {(label || sub) && (
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, flex: 1, minWidth: 0, flexWrap: 'wrap' }}>
          {label && <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{label}</span>}
          {sub && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--muted)' }}>{sub}</span>}
        </span>
      )}
      <input
        type="checkbox" checked={!!checked} disabled={disabled}
        onChange={e => onChange?.(e.target.checked)}
        style={{ position: 'absolute', opacity: 0, width: 1, height: 1, pointerEvents: 'none' }}
      />
      <span aria-hidden="true" style={{
        position: 'relative', width: 30, height: 18, borderRadius: 999, flexShrink: 0,
        background: checked ? 'var(--accent)' : 'var(--border-strong)',
        transition: 'background .16s var(--ease)',
      }}>
        <span style={{
          position: 'absolute', top: 2, left: 2, width: 14, height: 14, borderRadius: '50%',
          background: '#fff', boxShadow: '0 1px 2px rgba(0,0,0,.3)',
          transform: checked ? 'translateX(12px)' : 'none', transition: 'transform .18s var(--ease)',
        }} />
      </span>
    </label>
  )
}

// 滑桿：標題＋數值框＋細軌；format 決定數值顯示
export function Slider({ label, value, min, max, step = 1, onChange, format = v => v, minLabel, maxLabel, hint, disabled = false, title }) {
  return (
    <div title={title} style={{ display: 'grid', gridTemplateColumns: '1fr auto', columnGap: 12, alignItems: 'center', opacity: disabled ? 0.5 : 1 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
        <span style={{ fontSize: 12, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{label}</span>
        {hint && <span style={{ fontSize: 11, color: 'var(--faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{hint}</span>}
      </span>
      <span style={{
        gridRow: '1 / span 2', gridColumn: 2, alignSelf: 'end', minWidth: 52, textAlign: 'right',
        fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500, color: 'var(--text)',
        padding: '4px 7px', borderRadius: 'var(--r-sm)', background: 'var(--surface-2)', border: '1px solid var(--border)',
      }}>{format(value)}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
        {minLabel != null && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--faint)' }}>{minLabel}</span>}
        <input
          type="range" min={min} max={max} step={step} value={value} disabled={disabled}
          aria-label={label}
          style={{ flex: 1, minWidth: 0 }}
          onChange={e => onChange(Number(e.target.value))}
        />
        {maxLabel != null && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--faint)' }}>{maxLabel}</span>}
      </span>
    </div>
  )
}

// 分段選擇；options: [{ key, label, sub?, disabled?, title? }]
export function Segmented({ options, value, onChange, block = false, size = 'md' }) {
  const pad = size === 'sm' ? '4px 10px' : '6px 12px'
  return (
    <div role="radiogroup" style={{
      display: block ? 'flex' : 'inline-flex', border: '1px solid var(--border-strong)',
      borderRadius: 'var(--r)', overflow: 'hidden', background: 'var(--surface)',
    }}>
      {options.map((o, i) => {
        const on = o.key === value
        return (
          <button
            key={o.key} role="radio" aria-checked={on} disabled={o.disabled} title={o.title}
            onClick={() => !o.disabled && onChange(o.key)}
            style={{
              flex: block ? 1 : 'none', padding: pad, border: 'none',
              borderLeft: i === 0 ? 'none' : '1px solid var(--border-strong)',
              background: on ? 'var(--accent-soft)' : 'transparent',
              color: on ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 12.5, fontWeight: on ? 600 : 500, cursor: o.disabled ? 'not-allowed' : 'pointer',
              opacity: o.disabled ? 0.45 : 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
              lineHeight: 1.3,
            }}
          >
            <span>{o.label}</span>
            {o.sub && <span style={{ fontSize: 10.5, fontWeight: 400, color: on ? 'var(--accent)' : 'var(--muted)', opacity: .85 }}>{o.sub}</span>}
          </button>
        )
      })}
    </div>
  )
}

// 空狀態
export function Empty({ icon = 'image', title, children, style }) {
  return (
    <div style={{ ...UI.empty, ...style }}>
      <span style={{ width: 40, height: 40, borderRadius: 10, display: 'grid', placeItems: 'center', background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--faint)' }}>
        <Icon name={icon} size={20} />
      </span>
      {title && <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text-2)' }}>{title}</span>}
      {children && <span style={{ fontSize: 12.5, color: 'var(--muted)', textAlign: 'center', maxWidth: 320, lineHeight: 1.6 }}>{children}</span>}
    </div>
  )
}

// 進度條；pct=null 時為不定進度
export function Progress({ pct = null, height = 4 }) {
  return (
    <div style={{ width: '100%', background: 'var(--border)', height, borderRadius: height, overflow: 'hidden', position: 'relative' }}>
      {pct == null
        ? <div style={{ position: 'absolute', height: '100%', background: 'var(--accent)', borderRadius: height, animation: 'indeterminate 1.6s ease-in-out infinite' }} />
        : <div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent)', borderRadius: height, transition: 'width .2s' }} />}
    </div>
  )
}

export function Kbd({ children }) {
  return (
    <kbd style={{
      fontFamily: 'var(--font-mono)', fontSize: 10, lineHeight: 1, padding: '3px 4px', borderRadius: 3,
      background: 'rgba(255,255,255,.2)', color: 'inherit', opacity: .9,
    }}>{children}</kbd>
  )
}
