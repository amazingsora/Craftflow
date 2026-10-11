// 設計系統共用元件樣式（Console）；以 `UI.key` 或 `{ ...UI.key, 覆寫 }` 引用。token 定義見 index.css

const field = {
  width: '100%',
  background: 'var(--surface)',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--r)',
  color: 'var(--text)',
  padding: '7px 10px',
  fontSize: 14,
  lineHeight: 1.55,
  outline: 'none',
  boxSizing: 'border-box',
  transition: 'border-color .12s, box-shadow .12s',
}

const btnBase = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 6,
  borderRadius: 'var(--r)',
  fontSize: 13,
  fontWeight: 500,
  lineHeight: 1.2,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  textDecoration: 'none',
}

export const UI = {
  // ── 文字 ──
  label: { fontSize: 12, fontWeight: 500, color: 'var(--text-2)', marginBottom: 6, display: 'block' },
  sectionLabel: { fontSize: 12, fontWeight: 600, color: 'var(--text-2)', letterSpacing: '.01em' },
  hint: { fontSize: 12, color: 'var(--muted)', lineHeight: 1.55 },
  mono: { fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' },
  error: { color: 'var(--danger)', fontSize: 13 },

  // ── 表單 ──
  input: field,
  select: { ...field, padding: '7px 30px 7px 10px' },
  textarea: { ...field, padding: '8px 10px', resize: 'vertical', fontFamily: 'inherit', minHeight: 72 },

  // ── 按鈕 ──
  btnPrimary: {
    ...btnBase,
    padding: '10px 16px',
    border: '1px solid transparent',
    background: 'var(--accent)',
    color: 'var(--accent-contrast)',
    fontSize: 14,
    fontWeight: 600,
  },
  btnSecondary: {
    ...btnBase,
    padding: '8px 14px',
    border: '1px solid var(--border-strong)',
    background: 'var(--surface)',
    color: 'var(--text)',
  },
  btnSm: {
    ...btnBase,
    padding: '5px 10px',
    border: '1px solid var(--border-strong)',
    background: 'var(--surface)',
    color: 'var(--text)',
    fontSize: 12.5,
  },
  btnGhost: {
    ...btnBase,
    padding: '5px 8px',
    border: '1px solid transparent',
    background: 'transparent',
    color: 'var(--text-2)',
    fontSize: 12.5,
  },
  btnDanger: {
    ...btnBase,
    padding: '5px 10px',
    border: '1px solid var(--border-strong)',
    background: 'var(--surface)',
    color: 'var(--danger)',
    fontSize: 12.5,
  },
  btnIcon: {
    ...btnBase,
    width: 30, height: 30, padding: 0,
    border: '1px solid var(--border-strong)',
    background: 'var(--surface)',
    color: 'var(--text-2)',
  },
  btnDisabled: { opacity: 0.45, cursor: 'not-allowed' },

  // ── 選取類 ──
  chip: {
    ...btnBase,
    padding: '4px 11px',
    border: '1px solid var(--border-strong)',
    background: 'var(--surface)',
    color: 'var(--text-2)',
    fontSize: 12.5,
    fontWeight: 500,
  },
  chipActive: {
    background: 'var(--accent-soft)',
    color: 'var(--accent)',
    border: '1px solid var(--accent-border)',
    fontWeight: 600,
  },

  // ── 容器 ──
  panel: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--r-lg)',
  },
  inset: {
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--r)',
  },
  badge: {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    fontSize: 11, fontWeight: 600, lineHeight: 1.4,
    borderRadius: 'var(--r-sm)', padding: '1px 6px',
  },

  // ── 狀態 ──
  spinner: {
    width: 28, height: 28,
    border: '2px solid var(--border-strong)',
    borderTop: '2px solid var(--accent)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  loading: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: 60, color: 'var(--muted)', fontSize: 13 },
  empty: {
    minHeight: 320,
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    alignItems: 'center',
    justifyContent: 'center',
    border: '1px dashed var(--border-strong)',
    borderRadius: 'var(--r-lg)',
    color: 'var(--muted)',
    fontSize: 13,
    background: 'var(--surface-2)',
  },
  dropzone: {
    border: '1px dashed var(--border-strong)',
    borderRadius: 'var(--r-lg)',
    minHeight: 280,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    overflow: 'hidden',
    background: 'var(--surface-2)',
    color: 'var(--muted)',
    transition: 'border-color .15s, background .15s',
  },
  dropzoneActive: { borderColor: 'var(--accent)', background: 'var(--accent-soft)' },
}
