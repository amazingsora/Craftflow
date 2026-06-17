// Craftflow CharacterTab 樣式（2026-06-13 A2 增量1：自 CharacterTab.jsx 抽出，純靜態）

export const S = {
  root: { display: 'flex', flexDirection: 'column', gap: 16 },
  toolbar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 },
  toolbarTitle: { fontSize: 16, fontWeight: 700, color: 'var(--text)' },
  breadcrumb: { fontSize: 13, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6 },
  breadSep: { color: 'var(--border)' },
  breadLink: { color: 'var(--accent)', cursor: 'pointer', textDecoration: 'none' },

  addBtn: {
    padding: '8px 18px', borderRadius: 8, border: 'none',
    background: 'var(--accent)', color: 'var(--accent-contrast)', fontSize: 14,
    fontWeight: 600, cursor: 'pointer',
  },
  backBtn: {
    padding: '6px 14px', borderRadius: 8,
    border: '1px solid var(--border)', background: 'transparent',
    color: 'var(--muted)', fontSize: 13, cursor: 'pointer',
  },
  btnRow: { display: 'flex', gap: 8, flexWrap: 'wrap' },

  // Project grid
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 14 },
  card: {
    background: 'var(--surface-2)', border: '1px solid var(--border)',
    borderRadius: 12, padding: 18, cursor: 'pointer',
    transition: 'border-color .15s', display: 'flex', flexDirection: 'column', gap: 8,
  },
  cardTitle: { fontSize: 15, fontWeight: 700, color: 'var(--text)' },
  cardMeta: { fontSize: 12, color: 'var(--muted)', lineHeight: 1.6 },
  badge: {
    display: 'inline-block', fontSize: 11, borderRadius: 4,
    padding: '2px 7px', fontWeight: 600, alignSelf: 'flex-start',
  },
  genreBadge: {
    display: 'inline-block', fontSize: 11, borderRadius: 4,
    padding: '2px 7px', background: 'var(--surface)',
    border: '1px solid var(--border)', color: 'var(--muted)',
  },
  charCount: { fontSize: 12, color: 'var(--muted)', marginTop: 'auto' },

  // Character + Faction mixed grid
  charGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12 },
  charCard: {
    background: 'var(--surface-2)', border: '1px solid var(--border)',
    borderRadius: 10, padding: 14, cursor: 'pointer',
    transition: 'border-color .15s', display: 'flex', flexDirection: 'column', gap: 8,
  },
  portrait: {
    width: '100%', aspectRatio: '1/1', borderRadius: 8,
    background: 'var(--border)', overflow: 'hidden',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'var(--muted)', fontSize: 12,
  },
  charName: { fontSize: 14, fontWeight: 700, color: 'var(--text)' },
  charTraits: { fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 },

  // Faction tile (same size as char card, distinct style)
  factionTile: {
    background: 'var(--surface-2)', border: '2px dashed var(--border)',
    borderRadius: 10, padding: 14, cursor: 'pointer',
    transition: 'border-color .15s', display: 'flex', flexDirection: 'column', gap: 8,
  },
  factionThumb: {
    width: '100%', aspectRatio: '1/1', borderRadius: 8,
    background: 'var(--surface)', overflow: 'hidden',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 30, color: 'var(--muted)',
  },
  factionName: { fontSize: 14, fontWeight: 700, color: 'var(--accent)' },
  factionMeta: { fontSize: 11, color: 'var(--muted)' },

  // Color picker
  colorRow: { display: 'flex', alignItems: 'center', gap: 10 },
  colorPicker: {
    width: 38, height: 34, padding: 2, borderRadius: 6,
    border: '1px solid var(--border)', cursor: 'pointer', background: 'none',
  },
  colorCode: { fontFamily: 'monospace', fontSize: 13, color: 'var(--muted)' },
  colorDot: { width: 10, height: 10, borderRadius: '50%', flexShrink: 0 },

  // Faction chips (in char detail)
  factionChip: {
    display: 'inline-flex', alignItems: 'center', gap: 5,
    fontSize: 12, borderRadius: 20, padding: '3px 10px',
    background: 'var(--surface)', border: '1px solid var(--accent)',
    color: 'var(--accent)', cursor: 'default',
  },
  chipX: {
    cursor: 'pointer', color: 'var(--muted)', fontSize: 13,
    lineHeight: 1, padding: '0 2px',
  },

  // Delete confirm box
  deleteBox: {
    background: 'var(--tint-red-bg)', border: '1px solid var(--tint-red-bg)',
    borderRadius: 10, padding: 16, display: 'flex', flexDirection: 'column', gap: 10,
  },
  deletePrompt: { fontSize: 13, color: 'var(--danger)', margin: 0 },

  // Forms
  form: { display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 560 },
  label: { fontSize: 12, color: 'var(--muted)', marginBottom: 3, display: 'block' },
  input: {
    width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)',
    borderRadius: 8, color: 'var(--text)', padding: '9px 12px',
    fontSize: 14, outline: 'none', boxSizing: 'border-box',
  },
  select: {
    width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)',
    borderRadius: 8, color: 'var(--text)', padding: '9px 12px',
    fontSize: 14, outline: 'none', boxSizing: 'border-box',
  },
  textarea: {
    width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)',
    borderRadius: 8, color: 'var(--text)', padding: '9px 12px',
    fontSize: 14, resize: 'vertical', fontFamily: 'inherit',
    outline: 'none', minHeight: 80, boxSizing: 'border-box',
  },
  btn: {
    padding: '10px 0', borderRadius: 8, border: 'none',
    background: 'var(--accent)', color: 'var(--accent-contrast)',
    fontSize: 15, fontWeight: 600, cursor: 'pointer',
  },
  btnSm: {
    padding: '6px 14px', borderRadius: 8,
    border: '1px solid var(--border)', background: 'transparent',
    color: 'var(--text)', fontSize: 13, cursor: 'pointer',
  },
  btnDanger: {
    padding: '6px 14px', borderRadius: 8,
    border: '1px solid var(--tint-red-bg)', background: 'transparent',
    color: 'var(--danger)', fontSize: 13, cursor: 'pointer',
  },
  error: { color: 'var(--danger)', fontSize: 13 },
  muted: { color: 'var(--muted)', fontSize: 13 },

  // Variant tab bar
  varTabBar: { display: 'flex', gap: 4, margin: '4px 0 0', borderBottom: '1px solid var(--border)', paddingBottom: 0 },
  varTab: {
    padding: '7px 16px', border: 'none', background: 'transparent',
    color: 'var(--muted)', fontSize: 13, cursor: 'pointer',
    borderBottom: '2px solid transparent', marginBottom: -1, borderRadius: '6px 6px 0 0',
    display: 'flex', alignItems: 'center', gap: 5, transition: 'color .12s',
  },
  varTabActive: { color: 'var(--text)', borderBottom: '2px solid var(--accent)', fontWeight: 600, background: 'var(--accent-soft)' },
  tabEditBtn: {
    width: 16, height: 16, border: 'none', background: 'transparent',
    color: 'var(--muted)', cursor: 'pointer', padding: 0, fontSize: 12, lineHeight: 1,
    display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 3,
    flexShrink: 0,
  },

  // Detail layout
  detail: { display: 'flex', gap: 20, alignItems: 'flex-start' },
  detailLeft: { flex: '0 0 290px', display: 'flex', flexDirection: 'column', gap: 14 },
  detailRight: { flex: 1, display: 'flex', flexDirection: 'column', gap: 14 },
  summaryCard: {
    background: 'var(--surface-2)', border: '1px solid var(--border)',
    borderRadius: 10, padding: '14px 16px',
    fontSize: 13, lineHeight: 1.9, whiteSpace: 'pre-wrap',
    color: 'var(--text)', minHeight: 120,
  },
  summaryPlaceholder: {
    background: 'var(--surface-2)', border: '2px dashed var(--border)',
    borderRadius: 10, padding: '20px 16px',
    color: 'var(--muted)', fontSize: 13, textAlign: 'center',
  },
  dropzone: {
    border: '2px dashed var(--border)', borderRadius: 10,
    minHeight: 180, display: 'flex', alignItems: 'center',
    justifyContent: 'center', cursor: 'pointer',
    overflow: 'hidden', transition: 'border-color .2s', textAlign: 'center',
  },
  dropzoneActive: { borderColor: 'var(--accent)' },
  portraitImg: { width: '100%', objectFit: 'cover', maxHeight: 220, display: 'block' },
  genImg: { width: '100%', borderRadius: 10, display: 'block', marginTop: 8 },
  spinner: {
    display: 'inline-block', width: 16, height: 16,
    border: '2px solid var(--border)', borderTop: '2px solid var(--accent)',
    borderRadius: '50%', animation: 'spin 0.9s linear infinite',
    verticalAlign: 'middle', marginRight: 5,
  },
  sectionLabel: { fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 6 },
  divider: { borderColor: 'var(--border)', margin: '4px 0' },
  row: { display: 'flex', gap: 12 },
  fieldGroup: { flex: 1, display: 'flex', flexDirection: 'column', gap: 4 },
}
