// 生圖類分頁（Process／Generate／Compose）共用的樣式 token。
// 2026-09-24 重複碼整合：三個分頁的 S 物件中下列區塊逐字相同（最長 24 行），抽出後以
// `key: UI.key` 或 `{ ...UI.key, 覆寫 }` 引用；數值與原本完全一致，不改外觀。

export const UI = {
  btnPrimary: {
    padding: '11px 0',
    borderRadius: 8,
    border: 'none',
    background: 'var(--accent)',
    color: 'var(--accent-contrast)',
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
}
