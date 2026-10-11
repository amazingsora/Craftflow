// CharacterTab 樣式（純靜態）；共用元件樣式來自 sharedStyles.UI

import { UI } from './sharedStyles.js'

export const S = {
  root: { display: 'flex', flexDirection: 'column', gap: 20 },
  toolbar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, minHeight: 34 },
  toolbarTitle: { fontSize: 22, fontWeight: 700, color: 'var(--text)', letterSpacing: '-.02em' },
  breadcrumb: { fontSize: 13, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  breadSep: { color: 'var(--faint)' },
  breadLink: { color: 'var(--muted)', cursor: 'pointer', textDecoration: 'none', padding: '2px 4px', margin: '0 -4px', borderRadius: 'var(--r-sm)' },
  backBar: { position: 'sticky', top: 0, zIndex: 6, display: 'flex', alignItems: 'center', gap: 14, marginBottom: -8, background: 'var(--bg)', borderBottom: '1px solid var(--border)' },
  backBtn: { display: 'inline-flex', alignItems: 'center', gap: 6, height: 34, padding: '0 14px', flexShrink: 0, border: '1px solid var(--accent-border)', borderRadius: 'var(--r)', background: 'var(--accent-soft)', color: 'var(--accent)', fontSize: 13.5, fontWeight: 600, cursor: 'pointer' },
  backCrumb: { display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, fontSize: 13, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },

  addBtn: { ...UI.btnPrimary, padding: '7px 14px', fontSize: 13 },
  backBtn: { ...UI.btnGhost, color: 'var(--muted)' },
  btnRow: { display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' },

  // Project grid
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 },
  card: {
    ...UI.panel,
    padding: 20, cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 10, minHeight: 176,
  },
  cardTitle: { fontSize: 17, fontWeight: 700, color: 'var(--text)', letterSpacing: '-.01em' },
  cardMeta: { fontSize: 13, color: 'var(--text-2)', lineHeight: 1.65 },
  badge: { ...UI.badge, alignSelf: 'flex-start' },
  genreBadge: { ...UI.badge, fontWeight: 500, background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-2)' },
  charCount: { fontSize: 12, color: 'var(--muted)', marginTop: 'auto', paddingTop: 10, borderTop: '1px solid var(--border)' },

  // Character + Faction mixed grid
  charGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(176px, 1fr))', gap: 16 },
  charCard: {
    ...UI.panel,
    padding: 0, overflow: 'hidden', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 0,
  },
  portrait: {
    width: '100%', aspectRatio: '3/4',
    background: 'var(--canvas)', overflow: 'hidden',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'var(--muted)', fontSize: 12,
  },
  charName: { fontSize: 14, fontWeight: 600, color: 'var(--text)' },
  charTraits: { fontSize: 12, color: 'var(--muted)', lineHeight: 1.55, padding: '0 12px', margin: '0 0 12px' },

  // Faction tile (same size as char card, distinct style)
  factionTile: {
    ...UI.panel,
    padding: 0, overflow: 'hidden', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 0,
  },
  factionThumb: {
    width: '100%', aspectRatio: '3/4',
    background: 'var(--surface-2)', overflow: 'hidden',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'var(--faint)',
  },
  factionName: { fontSize: 14, fontWeight: 600, color: 'var(--text)', padding: '10px 12px 0' },
  factionMeta: { fontSize: 12, color: 'var(--muted)' },

  // Color picker
  colorRow: { display: 'flex', alignItems: 'center', gap: 8, height: 36 },
  colorPicker: {
    width: 36, height: 36, padding: 3, borderRadius: 'var(--r)',
    border: '1px solid var(--border-strong)', cursor: 'pointer', background: 'var(--surface)',
  },
  colorCode: { fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--text-2)' },
  colorDot: { width: 10, height: 10, borderRadius: 3, flexShrink: 0, boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.12)' },

  // Faction chips (in char detail)
  factionChip: {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    fontSize: 12.5, fontWeight: 500, borderRadius: 'var(--r)', padding: '3px 6px 3px 10px',
    background: 'var(--accent-soft)', border: '1px solid var(--accent-border)',
    color: 'var(--accent)', cursor: 'default',
  },
  chipX: {
    cursor: 'pointer', color: 'var(--accent)', fontSize: 14, opacity: .7,
    lineHeight: 1, padding: '0 3px',
  },

  // Delete confirm box
  deleteBox: {
    background: 'var(--tint-red-bg)', border: '1px solid var(--tint-red-bg)',
    borderRadius: 'var(--r-lg)', padding: 16, display: 'flex', flexDirection: 'column', gap: 10,
  },
  deletePrompt: { fontSize: 13, color: 'var(--danger)', margin: 0 },

  // Forms
  form: { display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 600 },
  label: UI.label,
  input: UI.input,
  select: UI.select,
  textarea: UI.textarea,
  btn: { ...UI.btnPrimary, padding: '9px 16px' },
  btnSm: UI.btnSm,
  btnDanger: UI.btnDanger,
  error: UI.error,
  muted: { color: 'var(--muted)', fontSize: 13 },

  // Variant tab bar
  varTabBar: { display: 'flex', gap: 0, borderBottom: '1px solid var(--border)' },
  varTab: {
    position: 'relative', padding: '8px 12px 9px', border: 'none', background: 'transparent',
    color: 'var(--muted)', fontSize: 13, fontWeight: 500, cursor: 'pointer',
    borderBottom: '2px solid transparent', marginBottom: -1, borderRadius: 'var(--r) var(--r) 0 0',
    display: 'flex', alignItems: 'center', gap: 6,
  },
  varTabActive: { color: 'var(--text)', borderBottom: '2px solid var(--accent)', fontWeight: 600 },
  tabEditBtn: {
    width: 18, height: 18, border: 'none', background: 'transparent',
    color: 'var(--faint)', cursor: 'pointer', padding: 0, fontSize: 11, lineHeight: 1,
    display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 'var(--r-sm)',
    flexShrink: 0,
  },

  // Detail layout：舞台｜資料｜生成面板（窄螢幕自動換行）
  detail: { display: 'grid', columnGap: 24, rowGap: 20, alignItems: 'start' },   // 欄寬見 index.css .cf-detail
  detailStage: { display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 },
  detailSummary: { minWidth: 0 },   // 寬螢幕時 sticky，見 index.css .cf-detail
  detailRight: { display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 },
  inspector: {
    ...UI.panel,
    padding: 0, overflow: 'hidden',
    display: 'flex', flexDirection: 'column', minWidth: 0,
  },
  inspectorHead: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
    padding: '12px 14px', borderBottom: '1px solid var(--border)',
  },
  inspectorTitle: { fontSize: 13, fontWeight: 600, color: 'var(--text)' },
  inspectorBody: { padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 12 },
  inspectorFoot: { padding: 12, borderTop: '1px solid var(--border)', background: 'var(--surface-2)' },

  summaryCard: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 'var(--r-lg)', padding: '14px 16px',
    fontSize: 13.5, lineHeight: 1.85, whiteSpace: 'pre-wrap',
    color: 'var(--text-2)',
  },
  summaryPlaceholder: {
    background: 'var(--surface-2)', border: '1px dashed var(--border-strong)',
    borderRadius: 'var(--r-lg)', padding: '18px 16px',
    color: 'var(--muted)', fontSize: 13, textAlign: 'center',
  },
  dropzone: {
    border: '1px dashed var(--border-strong)', borderRadius: 'var(--r-lg)',
    minHeight: 180, display: 'flex', alignItems: 'center',
    justifyContent: 'center', cursor: 'pointer', background: 'var(--surface-2)',
    overflow: 'hidden', transition: 'border-color .15s', textAlign: 'center',
  },
  dropzoneActive: { borderColor: 'var(--accent)' },
  portraitImg: { width: '100%', objectFit: 'cover', maxHeight: 220, display: 'block' },
  genImg: { width: '100%', borderRadius: 'var(--r)', display: 'block', marginTop: 8, background: 'var(--canvas)' },
  spinner: {
    display: 'inline-block', width: 14, height: 14,
    border: '2px solid currentColor', borderTopColor: 'transparent', opacity: .8,
    borderRadius: '50%', animation: 'spin 0.8s linear infinite',
    verticalAlign: 'middle', marginRight: 6, flexShrink: 0,
  },
  sectionLabel: { ...UI.sectionLabel, marginBottom: 8 },
  // 「會影響生圖」標記（取代舊的 ✦ 字元）
  genMark: { display: 'inline-block', width: 6, height: 6, borderRadius: 1, background: 'var(--accent)', transform: 'rotate(45deg)', margin: '0 8px 1px 1px', verticalAlign: 'middle' },
  sectionHead: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 10, minHeight: 26 },
  hint: { ...UI.hint, fontSize: 12, marginTop: 6 },
  divider: { borderColor: 'var(--border)', margin: '4px 0' },
  row: { display: 'flex', gap: 12 },
  fieldGroup: { flex: 1, display: 'flex', flexDirection: 'column', gap: 0, minWidth: 0 },
}
