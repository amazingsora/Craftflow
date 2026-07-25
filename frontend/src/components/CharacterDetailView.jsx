// Craftflow 角色詳情 View（2026-06-13 A2 增量3b：自 CharacterTab.jsx 抽出，零行為變更）
// 含 DEFAULT_TAB_NAMES + gen-prefs helper + _initVariant + CharacterDetailView

import { useState, useEffect, useRef } from 'react'
import { request, apiDelete, apiUrl } from '../api/client'
import { S } from './characterTabStyles.js'
import { Spinner, ImageLightbox, GenderPicker, DeleteConfirm } from './characterTabParts.jsx'
import { apiFetch } from './characterTabShared.js'


const DEFAULT_TAB_NAMES = ['主版本', 'Tab 2', 'Tab 3']

// Persist generate-checkbox prefs in localStorage so they survive page reload.
// Key: "craftflow_genprefs_<charId>" for main char, "craftflow_genprefs_<charId>_v<slot>" for variants.
const _genPrefsKey = (charId, slot) =>
  slot != null ? `craftflow_genprefs_${charId}_v${slot}` : `craftflow_genprefs_${charId}`

const _loadGenPrefs = (charId, slot, defaults) => {
  try {
    const raw = localStorage.getItem(_genPrefsKey(charId, slot))
    if (raw) return { ...defaults, ...JSON.parse(raw) }
  } catch {}
  return defaults
}

const _saveGenPref = (charId, slot, key, value) => {
  try {
    const k = _genPrefsKey(charId, slot)
    const prev = JSON.parse(localStorage.getItem(k) || '{}')
    localStorage.setItem(k, JSON.stringify({ ...prev, [key]: value }))
  } catch {}
}

function _initVariant(v = {}, charId = null, slot = null) {
  const prefs = _loadGenPrefs(charId, slot, {
    aiPromptEnabled: !!(v.ai_prompt),
    outfitEnabled: !!(v.outfit),
    ipaEnabled: true,
    ipaWeight: 0.6,
    cnEnabled: true,
    cnWeight: 0.85,
    visionEnabled: true,
  })
  return {
    color: v.color ?? '', traits: v.core_traits ?? '',
    behavior: v.behavior_rules ?? '', voice: v.voice_style ?? '',
    notes: v.notes ?? '', aiPrompt: v.ai_prompt ?? '',
    aiPromptEnabled: prefs.aiPromptEnabled,
    outfit: v.outfit ?? '', outfitEnabled: prefs.outfitEnabled,
    ipaEnabled: prefs.ipaEnabled,
    ipaWeight: prefs.ipaWeight,
    cnEnabled: prefs.cnEnabled,
    cnWeight: prefs.cnWeight,
    visionEnabled: prefs.visionEnabled,
    age: v.age != null ? String(v.age) : '', height: v.height != null ? String(v.height) : '', birthday: v.birthday ?? '',
    gender: v.gender ?? null, aiSummary: v.ai_summary ?? null,
    conceptImages: v.concept_images ?? [], aiImages: v.ai_generated_images ?? [],
    pendingQueue: [], generating: false, savingGen: false, savingFields: false,
    summarizing: false, uploadingConcept: false,
    deletingConceptIdx: null, deletingAiIdx: null,
    lastDebugPrompt: null, lastRawDesc: null, lastFlatDraft: null, lastTimings: null, lastAiPromptCompiled: null, lastIpaUsed: null, showDebugPrompt: false,
  }
}

export function CharacterDetailView({ character: initChar, project, allFactions, onBack, onDeleted, onAddHistory, onSendToGenerate, capability = { ipa_supported: true, cn_supported: true } }) {
  const ipaSupported = capability.ipa_supported
  const cnSupported  = capability.cn_supported

  const [char, setChar] = useState(initChar)
  const [charName, setCharName] = useState(initChar.name)
  const [color, setColor] = useState(initChar.color ?? '')
  const [notes, setNotes] = useState(initChar.notes ?? '')
  const [traits, setTraits] = useState(initChar.core_traits ?? '')
  const [behavior, setBehavior] = useState(initChar.behavior_rules ?? '')
  const [voice, setVoice] = useState(initChar.voice_style ?? '')
  const [age, setAge] = useState(initChar.age ?? '')
  const [height, setHeight] = useState(initChar.height ?? '')
  const [birthday, setBirthday] = useState(initChar.birthday ?? '')
  const [gender, setGender] = useState(initChar.gender ?? null)
  const [aiPrompt, setAiPrompt] = useState(initChar.ai_prompt ?? '')
  const [savingFields, setSavingFields] = useState(false)
  const [summarizing, setSummarizing] = useState(false)
  const [uploadingConcept, setUploadingConcept] = useState(false)
  const [conceptImages, setConceptImages] = useState(initChar.concept_images || [])
  const [generating, setGenerating] = useState(false)
  const [pendingQueue, setPendingQueue] = useState([])
  const [savingGen, setSavingGen] = useState(false)
  const [aiImages, setAiImages] = useState(initChar.ai_generated_images || [])
  const [error, setError] = useState(null)
  const [showDelete, setShowDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [charFactionIds, setCharFactionIds] = useState(initChar.faction_ids ?? [])
  const [addingFaction, setAddingFaction] = useState(false)
  const conceptRef = useRef()
  const [deletingConceptIdx, setDeletingConceptIdx] = useState(null)
  const [deletingAiIdx, setDeletingAiIdx] = useState(null)
  const [artStyleId, setArtStyleId] = useState(initChar.art_style_id ?? null)
  const [artStyles, setArtStyles] = useState([])
  // 角色專屬 LoRA（直通欄位）
  const [loraName, setLoraName] = useState(initChar.lora_name ?? '')
  const [loraWeight, setLoraWeight] = useState(initChar.lora_weight ?? 0.8)
  const [loraList, setLoraList] = useState([])
  const [aiPromptEnabled, setAiPromptEnabled] = useState(
    () => _loadGenPrefs(initChar.id, null, { aiPromptEnabled: !!initChar.ai_prompt }).aiPromptEnabled
  )
  const [outfit, setOutfit] = useState(initChar.outfit ?? '')
  const [outfitEnabled, setOutfitEnabled] = useState(
    () => _loadGenPrefs(initChar.id, null, { outfitEnabled: !!initChar.outfit }).outfitEnabled
  )
  const [ipaEnabled, setIpaEnabled] = useState(
    () => _loadGenPrefs(initChar.id, null, { ipaEnabled: true }).ipaEnabled
  )
  const [ipaWeight, setIpaWeight] = useState(
    () => _loadGenPrefs(initChar.id, null, { ipaWeight: 0.6 }).ipaWeight
  )
  // ControlNet 與 IPA 為兩個獨立後端參數，UI 拆開避免「一個開關控制兩者」的誤解
  const [cnEnabled, setCnEnabled] = useState(
    () => _loadGenPrefs(initChar.id, null, { cnEnabled: true }).cnEnabled
  )
  const [cnWeight, setCnWeight] = useState(
    () => _loadGenPrefs(initChar.id, null, { cnWeight: 0.85 }).cnWeight
  )
  // 草圖視覺特徵：是否用視覺模型從概念圖抽特徵進 prompt（CN coverage 偵測不受影響）
  const [visionEnabled, setVisionEnabled] = useState(
    () => _loadGenPrefs(initChar.id, null, { visionEnabled: true }).visionEnabled
  )
  const [showDebugPrompt, setShowDebugPrompt] = useState(false)
  const [lastDebugPrompt, setLastDebugPrompt] = useState(null)
  const [lastRawDesc, setLastRawDesc] = useState(null)
  const [lastFlatDraft, setLastFlatDraft] = useState(null)
  const [lastAiPromptCompiled, setLastAiPromptCompiled] = useState(null)
  const [lastIpaUsed, setLastIpaUsed] = useState(null)
  const [lastPromptProfile, setLastPromptProfile] = useState(null)
  const [lastCoverage, setLastCoverage] = useState(null)
  const [lightboxSrc, setLightboxSrc] = useState(null)
  const [lastTimings, setLastTimings] = useState(null)

  // ── Tab state ──────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState(0)
  const [tabNames, setTabNames] = useState(() => {
    const n = initChar.tab_names || []
    return DEFAULT_TAB_NAMES.map((d, i) => n[i] || d)
  })
  const [editingTabIdx, setEditingTabIdx] = useState(null)
  const [editingTabNameVal, setEditingTabNameVal] = useState('')
  const [savingTabName, setSavingTabName] = useState(false)

  // Variant state: 2 slots (Tab 2 = index 0, Tab 3 = index 1)
  const [vs, setVs] = useState(() => {
    const vars = initChar.variants || []
    return [_initVariant(vars[0] || {}, initChar.id, 1), _initVariant(vars[1] || {}, initChar.id, 2)]
  })
  const setV = (slot, upd) =>
    setVs(prev => prev.map((v, i) => i === slot - 1 ? { ...v, ...upd } : v))
  // Current variant state (null when on Tab 1)
  const vState = activeTab > 0 ? vs[activeTab - 1] : null

  const charFactions = allFactions.filter(f => charFactionIds.includes(f.id))
  const availableFactions = allFactions.filter(f => !charFactionIds.includes(f.id))

  useEffect(() => {
    apiFetch('/art-styles').then(setArtStyles).catch(() => {})
    // ComfyUI 離線時 /settings/loras 會 503，靜默忽略即可
    apiFetch('/settings/loras').then(d => setLoraList(d.loras || [])).catch(() => {})
  }, [])

  const saveFields = async () => {
    if (!charName.trim()) { setError('角色名稱不能為空'); return }
    setSavingFields(true)
    try {
      const updated = await apiFetch(`/characters/${char.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: charName.trim(),
          color: color || null,
          core_traits: traits || null,
          behavior_rules: behavior || null,
          voice_style: voice || null,
          notes: notes || null,
          age: age !== '' ? parseInt(age) : null,
          height: height !== '' ? parseInt(height) : null,
          birthday: birthday.trim() || null,
          gender: gender || null,
          ai_prompt: aiPrompt.trim() || null,
          outfit: outfit.trim() || null,
          art_style_id: artStyleId || null,
          lora_name: loraName.trim() || null,
          lora_weight: loraName.trim() ? parseFloat(loraWeight) : null,
        }),
      })
      setChar(updated)
    } catch (e) { setError(e.message) }
    finally { setSavingFields(false) }
  }

  const runSummarize = async () => {
    setSummarizing(true); setError(null)
    try {
      const updated = await apiFetch(`/characters/${char.id}/summarize`, { method: 'POST' })
      setChar(updated)
    } catch (e) { setError(e.message) }
    finally { setSummarizing(false) }
  }

  const uploadConceptImage = async (file) => {
    if (!file || !file.type.startsWith('image/')) return
    setUploadingConcept(true); setError(null)
    const body = new FormData()
    body.append('file', file)
    try {
      const updated = await apiFetch(`/characters/${char.id}/concept-images`, { method: 'POST', body })
      setChar(updated)
      setConceptImages(updated.concept_images || [])
    } catch (e) { setError(e.message) }
    finally { setUploadingConcept(false) }
  }

  const deleteConceptImage = async (idx) => {
    try {
      const updated = await apiFetch(`/characters/${char.id}/concept-images/${idx}`, { method: 'DELETE' })
      setChar(updated)
      setConceptImages(updated.concept_images || [])
      setDeletingConceptIdx(null)
    } catch (e) { setError(e.message) }
  }

  const generateDesignImage = async () => {
    setGenerating(true); setError(null); setPendingQueue([])
    try {
      const params = new URLSearchParams({
        use_ai_prompt: aiPromptEnabled ? '1' : '0',
        use_outfit: outfitEnabled ? '1' : '0',
        use_vision: visionEnabled ? '1' : '0',
        use_ipa: (ipaSupported && ipaEnabled) ? '1' : '0',
        ipa_weight: String(ipaWeight),
        use_controlnet: (cnSupported && cnEnabled) ? '1' : '0',
        cn_weight: String(cnWeight),
      })
      const resp = await request(`/characters/${char.id}/generate-design?${params}`, { method: 'POST' })
      
      // Retrieve debug prompt from header
      let debugPrompt = null
      const b64Prompt = resp.headers.get('X-Prompt')
      if (b64Prompt) {
        try {
          debugPrompt = atob(b64Prompt)
          // Decode UTF-8 if needed (atob handles latin1)
          debugPrompt = decodeURIComponent(escape(debugPrompt))
        } catch (e) { console.warn('Failed to decode debug prompt', e) }
      }

      const b64RawDesc = resp.headers.get('X-Raw-Desc')
      if (b64RawDesc) {
        try { setLastRawDesc(decodeURIComponent(escape(atob(b64RawDesc)))) }
        catch (e) { /* silent */ }
      }
      setLastFlatDraft(resp.headers.get('X-Flat-Draft') === '1')

      if (debugPrompt) setLastDebugPrompt(debugPrompt)

      const b64Profile = resp.headers.get('X-Prompt-Profile')
      if (b64Profile) {
        try { setLastPromptProfile(decodeURIComponent(escape(atob(b64Profile)))) }
        catch (e) { /* silent */ }
      }

      const b64Coverage = resp.headers.get('X-Coverage')
      if (b64Coverage) {
        try { setLastCoverage(decodeURIComponent(escape(atob(b64Coverage)))) }
        catch (e) { /* silent */ }
      }

      const b64Timings = resp.headers.get('X-Timings')
      if (b64Timings) {
        try { setLastTimings(JSON.parse(decodeURIComponent(escape(atob(b64Timings))))) }
        catch (e) { /* silent */ }
      }

      const b64AiCompiled = resp.headers.get('X-AI-Prompt-Compiled')
      if (b64AiCompiled) {
        try { setLastAiPromptCompiled(decodeURIComponent(escape(atob(b64AiCompiled)))) }
        catch (e) { /* silent */ }
      }
      setLastIpaUsed(resp.headers.get('X-IPA-Used') === '1')

      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      setPendingQueue([{ blob, url, label: '全身人設圖' }])
      onAddHistory?.({
        type: 'character', url, filename: `${char.name}_design_${Date.now()}.png`, label: `${char.name} 人設圖`,
        model: resp.headers.get('X-Style') || null,
        params: {
          ipa: ipaEnabled ? Number(ipaWeight) : null,
          cn: cnEnabled ? Number(cnWeight) : null,
          cnMode: resp.headers.get('X-CN-Mode') || null,
        },
      })
    } catch (e) { setError(e.message) }
    finally { setGenerating(false) }
  }

  const savePendingFirst = async () => {
    if (pendingQueue.length === 0) return
    setSavingGen(true)
    const item = pendingQueue[0]
    const fd = new FormData()
    fd.append('file', item.blob, `${char.name}_${item.expression ?? 'design'}.png`)
    try {
      const updated = await apiFetch(`/characters/${char.id}/ai-images`, { method: 'POST', body: fd })
      setChar(updated)
      setAiImages(updated.ai_generated_images || [])
      URL.revokeObjectURL(item.url)
      setPendingQueue(prev => prev.slice(1))
    } catch (e) { setError(e.message) }
    finally { setSavingGen(false) }
  }

  const discardPendingFirst = () => {
    if (pendingQueue.length === 0) return
    URL.revokeObjectURL(pendingQueue[0].url)
    setPendingQueue(prev => prev.slice(1))
  }

  const discardAllPending = () => {
    pendingQueue.forEach(item => URL.revokeObjectURL(item.url))
    setPendingQueue([])
  }

  const deleteAiImage = async (idx) => {
    try {
      const updated = await apiFetch(`/characters/${char.id}/ai-images/${idx}`, { method: 'DELETE' })
      setChar(updated)
      setAiImages(updated.ai_generated_images || [])
      setDeletingAiIdx(null)
    } catch (e) { setError(e.message) }
  }

  const joinFaction = async (factionId) => {
    try {
      await request(`/factions/${factionId}/members/${char.id}`, { method: 'POST' })
      setCharFactionIds(prev => [...prev, factionId])
      setAddingFaction(false)
    } catch (e) { setError(e.message) }
  }

  const leaveFaction = async (factionId) => {
    try {
      await apiDelete(`/factions/${factionId}/members/${char.id}`)
      setCharFactionIds(prev => prev.filter(id => id !== factionId))
    } catch (e) { setError(e.message) }
  }

  const deleteChar = async () => {
    setDeleting(true)
    try {
      await apiDelete(`/characters/${char.id}`)
      onDeleted()
    } catch (e) { setError(e.message); setDeleting(false) }
  }

  // ── Tab name handlers ──────────────────────────────────────────────────
  const startEditTabName = (idx) => {
    setEditingTabIdx(idx)
    setEditingTabNameVal(tabNames[idx])
  }
  const confirmTabName = async () => {
    const name = editingTabNameVal.trim() || DEFAULT_TAB_NAMES[editingTabIdx]
    const newNames = tabNames.map((n, i) => i === editingTabIdx ? name : n)
    setSavingTabName(true)
    try {
      await apiFetch(`/characters/${char.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tab_names: newNames }),
      })
      setTabNames(newNames)
    } catch (e) { setError(e.message) }
    finally { setSavingTabName(false); setEditingTabIdx(null) }
  }

  // ── Variant field handlers ─────────────────────────────────────────────
  const saveVariantFields = async () => {
    const slot = activeTab
    setV(slot, { savingFields: true })
    try {
      const v = vs[slot - 1]
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          color: v.color || null,
          core_traits: v.traits || null,
          behavior_rules: v.behavior || null,
          voice_style: v.voice || null,
          notes: v.notes || null,
          age: v.age !== '' ? parseInt(v.age) : null,
          height: v.height !== '' ? parseInt(v.height) : null,
          birthday: v.birthday.trim() || null,
          gender: v.gender || null,
          ai_prompt: v.aiPrompt.trim() || null,
          outfit: v.outfit.trim() || null,
        }),
      })
      // Sync variant data back from server response
      const serverVar = (updated.variants || [])[slot - 1] || {}
      setV(slot, { savingFields: false, conceptImages: serverVar.concept_images ?? v.conceptImages, aiImages: serverVar.ai_generated_images ?? v.aiImages })
    } catch (e) { setError(e.message); setV(slot, { savingFields: false }) }
  }

  const runVariantSummarize = async () => {
    const slot = activeTab
    setV(slot, { summarizing: true })
    try {
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/summarize`, { method: 'POST' })
      const serverVar = (updated.variants || [])[slot - 1] || {}
      setV(slot, { summarizing: false, aiSummary: serverVar.ai_summary ?? null })
    } catch (e) { setError(e.message); setV(slot, { summarizing: false }) }
  }

  const uploadVariantConceptImage = async (slot, file) => {
    console.log('[vConc] uploadVariantConceptImage called', { slot, fileName: file?.name, fileType: file?.type, activeTab })
    if (!file || !file.type.startsWith('image/')) {
      console.warn('[vConc] rejected: not an image or no file', file)
      return
    }
    setV(slot, { uploadingConcept: true })
    const body = new FormData()
    body.append('file', file)
    try {
      console.log('[vConc] POST', `/characters/${char.id}/variants/${slot}/concept-images`)
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/concept-images`, { method: 'POST', body })
      console.log('[vConc] success, variants:', updated?.variants)
      const serverVar = (updated.variants || [])[slot - 1] || {}
      console.log('[vConc] serverVar.concept_images:', serverVar.concept_images, '→ setV slot', slot)
      setV(slot, { uploadingConcept: false, conceptImages: serverVar.concept_images ?? [] })
      console.log('[vConc] setV called, current activeTab:', activeTab)
    } catch (e) {
      console.error('[vConc] error:', e.message)
      setError(e.message)
      setV(slot, { uploadingConcept: false })
    }
  }

  const deleteVariantConceptImage = async (slot, idx) => {
    try {
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/concept-images/${idx}`, { method: 'DELETE' })
      const serverVar = (updated.variants || [])[slot - 1] || {}
      setV(slot, { deletingConceptIdx: null, conceptImages: serverVar.concept_images ?? [] })
    } catch (e) { setError(e.message) }
  }

  const generateVariantDesignImage = async () => {
    const slot = activeTab
    setV(slot, { generating: true, pendingQueue: [] })
    try {
      const vParams = new URLSearchParams({
        use_ai_prompt: vState.aiPromptEnabled ? '1' : '0',
        use_outfit: vState.outfitEnabled ? '1' : '0',
        use_vision: (vState.visionEnabled ?? true) ? '1' : '0',
        use_ipa: (ipaSupported && vState.ipaEnabled) ? '1' : '0',
        ipa_weight: String(vState.ipaWeight ?? 0.6),
        use_controlnet: (cnSupported && (vState.cnEnabled ?? true)) ? '1' : '0',
        cn_weight: String(vState.cnWeight ?? 0.85),
      })
      const resp = await request(`/characters/${char.id}/variants/${slot}/generate-design?${vParams}`, { method: 'POST' })
      let debugPrompt = null
      const b64Prompt = resp.headers.get('X-Prompt')
      if (b64Prompt) { try { debugPrompt = decodeURIComponent(escape(atob(b64Prompt))) } catch (e) { /* silent */ } }
      let rawDesc = null
      const b64RawDesc = resp.headers.get('X-Raw-Desc')
      if (b64RawDesc) { try { rawDesc = decodeURIComponent(escape(atob(b64RawDesc))) } catch (e) { /* silent */ } }
      const flatDraft = resp.headers.get('X-Flat-Draft') === '1'
      let timings = null
      const b64Timings = resp.headers.get('X-Timings')
      if (b64Timings) { try { timings = JSON.parse(decodeURIComponent(escape(atob(b64Timings)))) } catch (e) { /* silent */ } }
      let aiPromptCompiled = null
      const b64AiCompiled = resp.headers.get('X-AI-Prompt-Compiled')
      if (b64AiCompiled) { try { aiPromptCompiled = decodeURIComponent(escape(atob(b64AiCompiled))) } catch (e) { /* silent */ } }
      const ipaUsed = resp.headers.get('X-IPA-Used') === '1'
      let promptProfile = null
      const b64Profile = resp.headers.get('X-Prompt-Profile')
      if (b64Profile) { try { promptProfile = decodeURIComponent(escape(atob(b64Profile))) } catch (e) { /* silent */ } }
      let coverage = null
      const b64Coverage = resp.headers.get('X-Coverage')
      if (b64Coverage) { try { coverage = decodeURIComponent(escape(atob(b64Coverage))) } catch (e) { /* silent */ } }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      setV(slot, {
        generating: false,
        lastDebugPrompt: debugPrompt,
        lastRawDesc: rawDesc,
        lastFlatDraft: flatDraft,
        lastTimings: timings,
        lastAiPromptCompiled: aiPromptCompiled,
        lastIpaUsed: ipaUsed,
        lastPromptProfile: promptProfile,
        lastCoverage: coverage,
        pendingQueue: [{ blob, url, label: '全身人設圖' }],
      })
      onAddHistory?.({
        type: 'character', url, filename: `${char.name}_v${slot}_design_${Date.now()}.png`, label: `${char.name} 人設圖（Tab ${slot}）`,
        model: resp.headers.get('X-Style') || null,
        params: {
          ipa: vState.ipaEnabled ? Number(vState.ipaWeight ?? 0.6) : null,
          cn: (vState.cnEnabled ?? true) ? Number(vState.cnWeight ?? 0.85) : null,
          cnMode: resp.headers.get('X-CN-Mode') || null,
        },
      })
    } catch (e) { setError(e.message); setV(slot, { generating: false }) }
  }

  const saveVariantPendingFirst = async () => {
    const slot = activeTab
    const v = vs[slot - 1]
    if (!v.pendingQueue.length) return
    const item = v.pendingQueue[0]
    setV(slot, { savingGen: true })
    const fd = new FormData()
    fd.append('file', item.blob, `${char.name}_v${slot}_design.png`)
    try {
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/ai-images`, { method: 'POST', body: fd })
      const serverVar = (updated.variants || [])[slot - 1] || {}
      URL.revokeObjectURL(item.url)
      setVs(prev => prev.map((vs, i) => i === slot - 1 ? {
        ...vs,
        savingGen: false,
        aiImages: serverVar.ai_generated_images ?? [],
        pendingQueue: vs.pendingQueue.slice(1),
      } : vs))
    } catch (e) { setError(e.message); setV(slot, { savingGen: false }) }
  }

  const deleteVariantAiImage = async (slot, idx) => {
    try {
      const updated = await apiFetch(`/characters/${char.id}/variants/${slot}/ai-images/${idx}`, { method: 'DELETE' })
      const serverVar = (updated.variants || [])[slot - 1] || {}
      setV(slot, { deletingAiIdx: null, aiImages: serverVar.ai_generated_images ?? [] })
    } catch (e) { setError(e.message) }
  }

  return (
    <div style={S.root}>
      <div style={S.toolbar}>
        <div style={S.breadcrumb}>
          <span style={S.breadLink} onClick={onBack}>← {project.title}</span>
          <span style={S.breadSep}>›</span>
          {char.color && <span style={{ ...S.colorDot, background: char.color }} />}
          <span style={{ color: 'var(--text)', fontWeight: 600 }}>{char.name}</span>
        </div>
        {onSendToGenerate && (
          <button
            style={{ fontSize: 12, padding: '6px 14px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'var(--accent-contrast)', cursor: 'pointer', fontWeight: 600 }}
            onClick={() => {
              const parts = [char.name]
              if (char.core_traits) parts.push(char.core_traits)
              if (char.outfit) parts.push(`服裝：${char.outfit}`)
              onSendToGenerate(parts.join('，'))
            }}
            title="將角色特徵帶入文字→生圖 Tab"
          >→ 以此角色生圖</button>
        )}
      </div>

      {/* ── Tab bar ── */}
      {editingTabIdx !== null ? (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', maxWidth: 260 }}>
          <input
            style={{ ...S.input, flex: 1, padding: '5px 10px', fontSize: 13 }}
            value={editingTabNameVal} autoFocus
            onChange={e => setEditingTabNameVal(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') confirmTabName(); if (e.key === 'Escape') setEditingTabIdx(null) }}
          />
          <button style={{ ...S.btnSm, fontSize: 12, padding: '4px 10px' }} disabled={savingTabName} onClick={confirmTabName}>
            {savingTabName ? <Spinner /> : '確認'}
          </button>
          <button style={{ ...S.btnSm, fontSize: 12, padding: '4px 10px' }} onClick={() => setEditingTabIdx(null)}>取消</button>
        </div>
      ) : (
        <div style={S.varTabBar}>
          {tabNames.map((name, idx) => (
            <button
              key={idx}
              style={{ ...S.varTab, ...(activeTab === idx ? S.varTabActive : {}) }}
              onClick={() => setActiveTab(idx)}
            >
              {name}
              <span
                style={S.tabEditBtn}
                title="重新命名"
                onClick={e => { e.stopPropagation(); startEditTabName(idx) }}
              >✎</span>
            </button>
          ))}
        </div>
      )}

      {error && <p style={S.error}>{error}</p>}

      {activeTab === 0 ? (
      <div style={S.detail}>
        {/* ── 左欄 ── */}
        <div style={S.detailLeft}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={S.sectionLabel}>AI 整理資訊</span>
              <button style={S.btnSm} onClick={runSummarize} disabled={summarizing}>
                {summarizing ? <><Spinner />整理中...</> : 'AI 重新整理'}
              </button>
            </div>
            {char.ai_summary
              ? <div style={S.summaryCard}>{char.ai_summary}</div>
              : <div style={S.summaryPlaceholder}>點擊「AI 重新整理」讓 AI 根據角色資料生成設定檔</div>
            }
          </div>

          {/* 概念圖（最多3張） */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={S.sectionLabel}>概念圖（{conceptImages.length}/3）</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
              {conceptImages.map((img, idx) => (
                <div key={idx} style={{ position: 'relative', aspectRatio: '1/1', borderRadius: 8, overflow: 'hidden', background: 'var(--border)' }}>
                  <img
                    src={apiUrl(`/characters/${char.id}/concept-images/${idx}?t=${img}`)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover', cursor: 'zoom-in' }}
                    alt={`概念圖${idx + 1}`}
                    title="點擊放大"
                    onClick={() => setLightboxSrc(apiUrl(`/characters/${char.id}/concept-images/${idx}?t=${img}`))}
                  />
                  {deletingConceptIdx === idx
                    ? <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.75)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                        <span style={{ fontSize: 11, color: 'var(--danger)' }}>確認刪除？</span>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button onClick={() => deleteConceptImage(idx)} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: 'none', background: 'var(--tint-red-bg)', color: 'var(--danger)', cursor: 'pointer' }}>刪除</button>
                          <button onClick={() => setDeletingConceptIdx(null)} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'transparent', color: 'var(--muted)', cursor: 'pointer' }}>取消</button>
                        </div>
                      </div>
                    : <button
                        onClick={() => setDeletingConceptIdx(idx)}
                        style={{ position: 'absolute', top: 3, right: 3, width: 20, height: 20, borderRadius: '50%', border: 'none', background: 'rgba(0,0,0,0.72)', color: 'var(--accent-contrast)', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}
                      >×</button>
                  }
                </div>
              ))}
              {conceptImages.length < 3 && (
                <div
                  style={{ aspectRatio: '1/1', borderRadius: 8, border: '2px dashed var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--muted)', fontSize: 24, transition: 'border-color .2s' }}
                  onClick={() => conceptRef.current.click()}
                  onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                >
                  {uploadingConcept ? <Spinner /> : '+'}
                </div>
              )}
            </div>
            <input ref={conceptRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={e => { if (e.target.files[0]) uploadConceptImage(e.target.files[0]); e.target.value = '' }} />
          </div>

          {/* AI 人設圖 */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: (ipaSupported && ipaEnabled) || (cnSupported && cnEnabled) ? 8 : 6 }}>
              <span style={S.sectionLabel}>AI 人設圖（{aiImages.length}/8）</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {ipaSupported && (
                  <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: ipaEnabled ? 'var(--tint-blue-fg)' : 'var(--muted)', cursor: 'pointer', userSelect: 'none' }}>
                    <input type="checkbox" checked={ipaEnabled} onChange={e => { setIpaEnabled(e.target.checked); _saveGenPref(initChar.id, null, 'ipaEnabled', e.target.checked) }}
                      style={{ cursor: 'pointer', accentColor: 'var(--tint-blue-fg)' }} />
                    概念圖參考
                  </label>
                )}
                {cnSupported && (
                  <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: cnEnabled ? 'var(--tint-blue-fg)' : 'var(--muted)', cursor: 'pointer', userSelect: 'none' }}>
                    <input type="checkbox" checked={cnEnabled} onChange={e => { setCnEnabled(e.target.checked); _saveGenPref(initChar.id, null, 'cnEnabled', e.target.checked) }}
                      style={{ cursor: 'pointer', accentColor: 'var(--tint-blue-fg)' }} />
                    ControlNet
                  </label>
                )}
                <button style={S.btnSm} disabled={generating} onClick={generateDesignImage}>
                  {generating ? <><Spinner />生成中...</> : '生成人設圖'}
                </button>
              </div>
            </div>
            {ipaSupported && ipaEnabled && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>IPA 強度</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                <input type="range" min={0.1} max={1.5} step={0.05} value={ipaWeight}
                  style={{ flex: 1, accentColor: 'var(--tint-blue-fg)' }}
                  onChange={e => { const v = Number(e.target.value); setIpaWeight(v); _saveGenPref(initChar.id, null, 'ipaWeight', v) }} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
                <span style={{ fontSize: 12, color: 'var(--tint-blue-fg)', minWidth: 30, textAlign: 'right' }}>{ipaWeight.toFixed(2)}</span>
              </div>
            )}
            {cnSupported && cnEnabled && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>CN 強度</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                <input type="range" min={0.1} max={1.5} step={0.05} value={cnWeight}
                  style={{ flex: 1, accentColor: 'var(--tint-blue-fg)' }}
                  onChange={e => { const v = Number(e.target.value); setCnWeight(v); _saveGenPref(initChar.id, null, 'cnWeight', v) }} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
                <span style={{ fontSize: 12, color: 'var(--tint-blue-fg)', minWidth: 30, textAlign: 'right' }}>{cnWeight.toFixed(2)}</span>
              </div>
            )}

            {/* 待確認佇列（一次顯示一張） */}
            {pendingQueue.length > 0 && (
              <div style={{ marginBottom: 10, border: '1px solid var(--border)', borderRadius: 10, padding: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
                    {pendingQueue[0].label}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    待確認 {pendingQueue.length} 張
                  </span>
                </div>
                
                <img
                  src={pendingQueue[0].url}
                  style={{ ...S.genImg, marginTop: 0, cursor: 'zoom-in' }}
                  alt={pendingQueue[0].label}
                  title="點擊放大"
                  onClick={() => setLightboxSrc(pendingQueue[0].url)}
                />

                <div style={{ ...S.btnRow, marginTop: 6 }}>
                  <button
                    style={{ ...S.btn, flex: 1, padding: '7px 0', fontSize: 13 }}
                    disabled={savingGen || aiImages.length >= 8}
                    onClick={savePendingFirst}
                  >
                    {savingGen ? <><Spinner />儲存中...</> : aiImages.length >= 8 ? '已達上限' : '儲存此圖'}
                  </button>
                  <button style={S.btnSm} onClick={discardPendingFirst}>捨棄</button>
                  {pendingQueue.length > 1 && (
                    <button style={{ ...S.btnSm, color: 'var(--danger)' }} onClick={discardAllPending}>全捨棄</button>
                  )}
                </div>

                {lastTimings && (
                  <div style={{ marginTop: 8, padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 5, fontWeight: 600, letterSpacing: 0.5 }}>⏱ 生成耗時</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                      {[
                        lastTimings.vision_extract    != null && ['視覺分析',  lastTimings.models?.vision,   lastTimings.vision_extract],
                        lastTimings.body_coverage     != null && ['姿態偵測',  lastTimings.models?.vision,   lastTimings.body_coverage],
                        lastTimings.compile_prompt    != null && ['提示詞編譯', lastTimings.models?.text,    lastTimings.compile_prompt],
                        lastTimings.compile_ai_prompt != null && ['AI提示詞',  lastTimings.models?.text,    lastTimings.compile_ai_prompt],
                        lastTimings.canvas_expand     != null && ['Canvas Expand', lastTimings.models?.canvas_expand || lastTimings.models?.workflow, lastTimings.canvas_expand],
                        lastTimings.upload            != null && ['圖片上傳',  null,                         lastTimings.upload],
                        lastTimings.comfyui           != null && ['ComfyUI 生成', lastTimings.models?.workflow, lastTimings.comfyui],
                      ].filter(Boolean).map(([label, model, sec]) => (
                        <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                          <span style={{ color: 'var(--muted)' }}>
                            {label}
                            {model && <span style={{ color: 'var(--muted)', marginLeft: 4, fontSize: 10 }}>({model})</span>}
                          </span>
                          <span style={{ color: 'var(--text)', fontFamily: 'monospace' }}>{sec}s</span>
                        </div>
                      ))}
                      {(() => {
                        const keys = ['vision_extract','body_coverage','compile_prompt','compile_ai_prompt','canvas_expand','upload','comfyui']
                        const sum = keys.reduce((a, k) => a + (lastTimings[k] ?? 0), 0)
                        const other = Math.round((lastTimings.total - sum) * 10) / 10
                        return other > 0.5 ? (
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                            <span style={{ color: 'var(--muted)' }}>其他</span>
                            <span style={{ color: 'var(--text)', fontFamily: 'monospace' }}>{other}s</span>
                          </div>
                        ) : null
                      })()}
                      <div style={{ borderTop: '1px solid var(--border)', marginTop: 3, paddingTop: 3, display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                        <span style={{ color: 'var(--accent)', fontWeight: 600 }}>總計</span>
                        <span style={{ color: 'var(--accent)', fontFamily: 'monospace', fontWeight: 600 }}>{lastTimings.total}s</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 已儲存的 AI 圖 */}
            {aiImages.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {aiImages.map((img, idx) => (
                  <div key={idx} style={{ borderRadius: 8, overflow: 'hidden' }}>
                    <img
                      src={apiUrl(`/characters/${char.id}/ai-images/${idx}?t=${img}`)}
                      style={{ width: '100%', display: 'block', borderRadius: 8, cursor: 'zoom-in' }}
                      alt={`AI圖${idx + 1}`}
                      title="點擊放大"
                      onClick={() => setLightboxSrc(apiUrl(`/characters/${char.id}/ai-images/${idx}?t=${img}`))}
                    />
                    <div style={{ display: 'flex', gap: 4, marginTop: 4, justifyContent: 'center' }}>
                      <a href={apiUrl(`/characters/${char.id}/ai-images/${idx}`)} download={`${char.name}_ai_${idx + 1}.png`} style={{ ...S.btnSm, fontSize: 11, padding: '3px 8px', textDecoration: 'none', textAlign: 'center' }}>下載</a>
                      {deletingAiIdx === idx
                        ? <>
                            <button style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: 'none', background: 'var(--tint-red-bg)', color: 'var(--danger)', cursor: 'pointer' }} onClick={() => deleteAiImage(idx)}>確認</button>
                            <button style={{ ...S.btnSm, fontSize: 11, padding: '3px 8px' }} onClick={() => setDeletingAiIdx(null)}>取消</button>
                          </>
                        : <button style={{ ...S.btnDanger, fontSize: 11, padding: '3px 8px' }} onClick={() => setDeletingAiIdx(idx)}>移除</button>
                      }
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 刪除角色 */}
          <div>
            {!showDelete
              ? <button style={{ ...S.btnDanger, width: '100%', padding: '8px 0', textAlign: 'center' }} onClick={() => setShowDelete(true)}>刪除角色</button>
              : <DeleteConfirm
                  label={`永久刪除角色「${char.name}」`}
                  name={char.name}
                  loading={deleting}
                  onConfirm={deleteChar}
                  onCancel={() => setShowDelete(false)}
                />
            }
          </div>
        </div>

        {/* ── 右欄 ── */}
        <div style={S.detailRight}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={S.sectionLabel}>角色資料（可編輯）</span>
            <button style={S.btnSm} disabled={savingFields} onClick={saveFields}>
              {savingFields ? <><Spinner />儲存中...</> : '儲存所有變更'}
            </button>
          </div>

          <div style={S.row}>
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>角色名稱</label>
              <input style={S.input} value={charName} onChange={e => setCharName(e.target.value)} />
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}>代表色</label>
              <div style={S.colorRow}>
                <input type="color" style={S.colorPicker} value={color || '#888888'} onChange={e => setColor(e.target.value)} />
                <span style={S.colorCode}>{color || '未設定'}</span>
                {color && <button style={{ ...S.btnSm, fontSize: 11, padding: '4px 10px' }} onClick={() => setColor('')}>清除</button>}
              </div>
            </div>
          </div>

          <div style={S.row}>
            <div style={S.fieldGroup}>
              <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>年齡</label>
              <input type="number" style={S.input} value={age} onChange={e => setAge(e.target.value)} placeholder="例如：18" min="0" max="9999" />
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>身高 (cm)</label>
              <input type="number" style={S.input} value={height} onChange={e => setHeight(e.target.value)} placeholder="例如：162" min="50" max="250" />
            </div>
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>生日</label>
              <input style={S.input} value={birthday} onChange={e => setBirthday(e.target.value)} placeholder="例如：5月16日 或 1998-05-16" />
            </div>
          </div>

          <div>
            <label style={S.label}>
              性別
              {gender && age !== '' && (
                <span style={{ marginLeft: 8, fontFamily: 'monospace', fontSize: 11, color: 'var(--accent)' }}>
                  → {gender === 'female' ? (parseInt(age) < 25 ? '1girl' : parseInt(age) < 40 ? '1woman' : '1woman, mature female') : gender === 'male' ? (parseInt(age) < 25 ? '1boy' : parseInt(age) < 40 ? '1man' : '1man, mature male') : 'androgynous'}
                </span>
              )}
            </label>
            <GenderPicker value={gender} onChange={setGender} />
          </div>

          {/* 畫風 */}
          <div>
            <label style={S.label}>預設畫風</label>
            <select
              style={S.select}
              value={artStyleId ?? ''}
              onChange={e => setArtStyleId(e.target.value ? parseInt(e.target.value) : null)}
            >
              <option value="">（不設定，依全域 checkpoint 自動偵測）</option>
              {artStyles.map(s => (
                <option key={s.id} value={s.id}>{s.name} [{s.base_style}]</option>
              ))}
            </select>
          </div>

          {/* 角色專屬 LoRA（直通欄位，獨立於畫風） */}
          <div>
            <label style={S.label}>專屬 LoRA</label>
            <select
              style={S.select}
              value={loraName}
              onChange={e => setLoraName(e.target.value)}
            >
              <option value="">（不使用專屬 LoRA）</option>
              {/* 已選但清單中沒有（ComfyUI 離線）時仍保留目前值 */}
              {loraName && !loraList.includes(loraName) && (
                <option value={loraName}>{loraName}（目前設定）</option>
              )}
              {loraList.map(l => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
            {loraName && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>權重</span>
                <input
                  type="range" min="0" max="1" step="0.05"
                  value={loraWeight}
                  onChange={e => setLoraWeight(parseFloat(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ fontSize: 12, color: 'var(--text)', width: 32, textAlign: 'right' }}>
                  {Number(loraWeight).toFixed(2)}
                </span>
              </div>
            )}
          </div>

          {/* 所屬勢力 */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <label style={S.label}>所屬勢力</label>
              {availableFactions.length > 0 && (
                <button style={{ ...S.btnSm, fontSize: 11, padding: '3px 10px' }} onClick={() => setAddingFaction(s => !s)}>
                  {addingFaction ? '取消' : '+ 加入勢力'}
                </button>
              )}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {charFactions.length === 0 && !addingFaction && <span style={S.muted}>無</span>}
              {charFactions.map(f => (
                <span key={f.id} style={S.factionChip}>
                  {f.name}
                  <span style={S.chipX} onClick={() => leaveFaction(f.id)}>×</span>
                </span>
              ))}
            </div>
            {addingFaction && availableFactions.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                {availableFactions.map(f => (
                  <button key={f.id} style={S.btnSm} onClick={() => joinFaction(f.id)}>{f.name}</button>
                ))}
              </div>
            )}
          </div>

          <div>
            <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>外貌 / 個性特徵</label>
            <textarea style={{ ...S.textarea, minHeight: 70 }} value={traits} onChange={e => setTraits(e.target.value)} placeholder="髮色、體型、個性..." />
          </div>
          <div>
            <label style={S.label}>行為模式</label>
            <textarea style={{ ...S.textarea, minHeight: 70 }} value={behavior} onChange={e => setBehavior(e.target.value)} placeholder="面對危機的反應、習慣..." />
          </div>
          <div>
            <label style={S.label}>說話風格</label>
            <textarea style={{ ...S.textarea, minHeight: 50 }} value={voice} onChange={e => setVoice(e.target.value)} placeholder="語氣、口頭禪..." />
          </div>
          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={visionEnabled}
                onChange={e => { setVisionEnabled(e.target.checked); _saveGenPref(initChar.id, null, 'visionEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
              />
              <span style={{ color: 'var(--accent)' }}>✦ </span>草圖視覺特徵
            </label>
            <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>開啟時用視覺模型從概念圖抽取特徵加入提示詞；關閉則僅靠欄位設定，交由 CN／畫風主導（CN 結構偵測不受影響）</p>
          </div>
          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={outfitEnabled}
                onChange={e => { setOutfitEnabled(e.target.checked); _saveGenPref(initChar.id, null, 'outfitEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
              />
              <span style={{ color: 'var(--accent)' }}>✦ </span>服裝設定
            </label>
            {outfitEnabled && (
              <>
                <textarea
                  style={{ ...S.textarea, minHeight: 60 }}
                  value={outfit}
                  onChange={e => setOutfit(e.target.value)}
                  placeholder="例如：白色禮服、黑色窄裙、學生制服、和服..."
                />
                <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>服裝描述會加入生成提示詞，影響圖片中的穿著</p>
              </>
            )}
          </div>

          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={aiPromptEnabled}
                onChange={e => { setAiPromptEnabled(e.target.checked); _saveGenPref(initChar.id, null, 'aiPromptEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
              />
              <span style={{ color: 'var(--accent)' }}>✦ </span>AI 提示詞
            </label>
            {aiPromptEnabled && (
              <>
                <textarea
                  style={{ ...S.textarea, minHeight: 60, fontFamily: 'monospace', fontSize: 13 }}
                  value={aiPrompt}
                  onChange={e => setAiPrompt(e.target.value)}
                  placeholder="中英文皆可，例如：flat color, clean lineart 或 戲劇性光影、強烈對比"
                />
                <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>中英文皆接受，獨立編譯後置於 prompt 最前端，強制力優先於角色描述</p>
              </>
            )}
          </div>

          <div>
            <label style={S.label}>創作筆記</label>
            <textarea style={{ ...S.textarea, minHeight: 120 }} value={notes} onChange={e => setNotes(e.target.value)} placeholder="隨時新增想法..." />
            <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>供「AI 重新整理」及問答使用，不影響圖片生成</p>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ ...S.label, marginBottom: 0, fontFamily: 'monospace', letterSpacing: 1 }}>DEBUG PROMPT</span>
              <button
                style={{ ...S.btnSm, fontSize: 11, padding: '3px 10px' }}
                onClick={() => setShowDebugPrompt(s => !s)}
              >
                {showDebugPrompt ? '隱藏' : '顯示'}
              </button>
            </div>
            {showDebugPrompt && (
              lastDebugPrompt
                ? <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontSize: 10, color: 'var(--tint-blue-fg)', letterSpacing: 1, fontFamily: 'monospace' }}>中文描述（AI 翻譯前）</div>
                      {lastFlatDraft != null && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: lastFlatDraft ? 'var(--tint-amber-bg)' : 'var(--tint-green-bg)',
                          color: lastFlatDraft ? 'var(--tint-amber-fg)' : 'var(--tint-green-fg)',
                          border: `1px solid ${lastFlatDraft ? 'var(--tint-amber-bg)' : 'var(--tint-green-bg)'}` }}>
                          {lastFlatDraft ? '單色稿 → 文字優先' : '正式上色 → 視覺優先'}
                        </div>
                      )}
                      {lastIpaUsed != null && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: lastIpaUsed ? 'var(--tint-blue-bg)' : 'var(--surface-2)',
                          color: lastIpaUsed ? 'var(--tint-blue-fg)' : 'var(--muted)',
                          border: `1px solid ${lastIpaUsed ? 'var(--tint-blue-border)' : 'var(--border-strong)'}` }}>
                          {lastIpaUsed ? 'IP-Adapter ON' : 'IP-Adapter OFF'}
                        </div>
                      )}
                      {lastPromptProfile && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: lastPromptProfile.startsWith('profile:') ? 'var(--tint-purple-bg)' : 'var(--surface-2)',
                          color: lastPromptProfile.startsWith('profile:') ? 'var(--tint-purple-fg)' : 'var(--muted)',
                          border: `1px solid ${lastPromptProfile.startsWith('profile:') ? 'var(--tint-purple-bg)' : 'var(--border-strong)'}` }}>
                          {lastPromptProfile}
                        </div>
                      )}
                      {lastCoverage && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: lastCoverage.includes('→') ? 'var(--tint-amber-bg)' : 'var(--surface-2)',
                          color: lastCoverage.includes('→') ? 'var(--tint-amber-fg)' : 'var(--muted)',
                          border: `1px solid ${lastCoverage.includes('→') ? 'var(--tint-amber-bg)' : 'var(--border-strong)'}` }}>
                          {lastCoverage}
                        </div>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--tint-green-fg)', background: 'var(--tint-blue-bg)', padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, border: '1px solid var(--tint-green-bg)', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                      {lastRawDesc ?? '—'}
                    </div>
                    {lastAiPromptCompiled !== null && (
                      <>
                        <div style={{ fontSize: 10, letterSpacing: 1, fontFamily: 'monospace', marginTop: 2,
                          color: lastAiPromptCompiled === '[compilation_failed]' ? 'var(--danger)' : 'var(--tint-amber-fg)' }}>
                          AI 提示詞編譯結果{lastAiPromptCompiled === '[compilation_failed]' ? ' ⚠ 失敗' : '（置於 prompt 首位）'}
                        </div>
                        <div style={{ fontSize: 11, padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, fontFamily: 'monospace',
                          color: lastAiPromptCompiled === '[compilation_failed]' ? 'var(--danger)' : 'var(--tint-amber-fg)',
                          background: lastAiPromptCompiled === '[compilation_failed]' ? 'var(--tint-red-bg)' : 'var(--tint-amber-bg)',
                          border: `1px solid ${lastAiPromptCompiled === '[compilation_failed]' ? 'var(--tint-red-bg)' : 'var(--tint-amber-bg)'}` }}>
                          {lastAiPromptCompiled === '[compilation_failed]' ? 'AI 提示詞未套用（Ollama 翻譯錯誤）' : lastAiPromptCompiled}
                        </div>
                      </>
                    )}
                    <div style={{ fontSize: 10, color: 'var(--tint-purple-fg)', letterSpacing: 1, fontFamily: 'monospace', marginTop: 2 }}>最終 Prompt（英文）</div>
                    <div style={{ fontSize: 11, color: 'var(--tint-purple-fg)', background: 'var(--tint-purple-bg)', padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, border: '1px solid var(--tint-purple-bg)', fontFamily: 'monospace' }}>
                      {lastDebugPrompt}
                    </div>
                  </div>
                : <p style={{ ...S.muted, fontSize: 11 }}>尚未生成人設圖，無 prompt 記錄</p>
            )}
          </div>
        </div>
      </div>
      ) : (
      /* ── Variant detail (Tab 2 / Tab 3) ── */
      <div style={S.detail}>
        {/* Left col: variant images */}
        <div style={S.detailLeft}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={S.sectionLabel}>AI 整理資訊</span>
              <button style={S.btnSm} onClick={runVariantSummarize} disabled={vState.summarizing}>
                {vState.summarizing ? <><Spinner />整理中...</> : 'AI 重新整理'}
              </button>
            </div>
            {vState.aiSummary
              ? <div style={S.summaryCard}>{vState.aiSummary}</div>
              : <div style={S.summaryPlaceholder}>點擊「AI 重新整理」生成此版本設定檔</div>
            }
          </div>

          {/* Variant concept images */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={S.sectionLabel}>概念圖（{vState.conceptImages.length}/3）</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
              {vState.conceptImages.map((img, idx) => (
                <div key={idx} style={{ position: 'relative', aspectRatio: '1/1', borderRadius: 8, overflow: 'hidden', background: 'var(--border)' }}>
                  <img
                    src={apiUrl(`/characters/${char.id}/variants/${activeTab}/concept-images/${idx}?t=${img}`)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover', cursor: 'zoom-in' }}
                    alt={`概念圖${idx + 1}`}
                    onClick={() => setLightboxSrc(apiUrl(`/characters/${char.id}/variants/${activeTab}/concept-images/${idx}?t=${img}`))}
                  />
                  {vState.deletingConceptIdx === idx
                    ? <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.75)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                        <span style={{ fontSize: 11, color: 'var(--danger)' }}>確認刪除？</span>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button onClick={() => deleteVariantConceptImage(activeTab, idx)} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: 'none', background: 'var(--tint-red-bg)', color: 'var(--danger)', cursor: 'pointer' }}>刪除</button>
                          <button onClick={() => setV(activeTab, { deletingConceptIdx: null })} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'transparent', color: 'var(--muted)', cursor: 'pointer' }}>取消</button>
                        </div>
                      </div>
                    : <button onClick={() => setV(activeTab, { deletingConceptIdx: idx })}
                        style={{ position: 'absolute', top: 3, right: 3, width: 20, height: 20, borderRadius: '50%', border: 'none', background: 'rgba(0,0,0,0.72)', color: 'var(--accent-contrast)', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}
                      >×</button>
                  }
                </div>
              ))}
              {vState.conceptImages.length < 3 && (
                <label
                  htmlFor={`vconc-slot-${activeTab}`}
                  style={{ aspectRatio: '1/1', borderRadius: 8, border: '2px dashed var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--muted)', fontSize: 24, transition: 'border-color .2s' }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                  onClick={() => console.log('[vConc] label clicked, activeTab:', activeTab, 'htmlFor:', `vconc-slot-${activeTab}`)}
                >
                  {vState.uploadingConcept ? <Spinner /> : '+'}
                </label>
              )}
            </div>
            {[1, 2].map(slot => (
              <input key={slot} id={`vconc-slot-${slot}`} type="file" accept="image/*" style={{ display: 'none' }}
                onChange={e => {
                  console.log('[vConc] input onChange', { inputSlot: slot, activeTab, file: e.target.files[0]?.name })
                  if (e.target.files[0]) uploadVariantConceptImage(slot, e.target.files[0])
                  e.target.value = ''
                }} />
            ))}
          </div>

          {/* Variant AI images */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: (ipaSupported && vState.ipaEnabled) || (cnSupported && (vState.cnEnabled ?? true)) ? 8 : 6 }}>
              <span style={S.sectionLabel}>AI 人設圖（{vState.aiImages.length}/8）</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {ipaSupported && (
                  <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: vState.ipaEnabled ? 'var(--tint-blue-fg)' : 'var(--muted)', cursor: 'pointer', userSelect: 'none' }}>
                    <input type="checkbox" checked={vState.ipaEnabled} onChange={e => { setV(activeTab, { ipaEnabled: e.target.checked }); _saveGenPref(initChar.id, activeTab, 'ipaEnabled', e.target.checked) }}
                      style={{ cursor: 'pointer', accentColor: 'var(--tint-blue-fg)' }} />
                    概念圖參考
                  </label>
                )}
                {cnSupported && (
                  <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: (vState.cnEnabled ?? true) ? 'var(--tint-blue-fg)' : 'var(--muted)', cursor: 'pointer', userSelect: 'none' }}>
                    <input type="checkbox" checked={vState.cnEnabled ?? true} onChange={e => { setV(activeTab, { cnEnabled: e.target.checked }); _saveGenPref(initChar.id, activeTab, 'cnEnabled', e.target.checked) }}
                      style={{ cursor: 'pointer', accentColor: 'var(--tint-blue-fg)' }} />
                    ControlNet
                  </label>
                )}
                <button style={S.btnSm} disabled={vState.generating} onClick={generateVariantDesignImage}>
                  {vState.generating ? <><Spinner />生成中...</> : '生成人設圖'}
                </button>
              </div>
            </div>
            {ipaSupported && vState.ipaEnabled && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>IPA 強度</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                <input type="range" min={0.1} max={1.5} step={0.05} value={vState.ipaWeight ?? 0.6}
                  style={{ flex: 1, accentColor: 'var(--tint-blue-fg)' }}
                  onChange={e => { const v = Number(e.target.value); setV(activeTab, { ipaWeight: v }); _saveGenPref(initChar.id, activeTab, 'ipaWeight', v) }} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
                <span style={{ fontSize: 12, color: 'var(--tint-blue-fg)', minWidth: 30, textAlign: 'right' }}>{(vState.ipaWeight ?? 0.6).toFixed(2)}</span>
              </div>
            )}
            {cnSupported && (vState.cnEnabled ?? true) && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>CN 強度</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>0.1</span>
                <input type="range" min={0.1} max={1.5} step={0.05} value={vState.cnWeight ?? 0.85}
                  style={{ flex: 1, accentColor: 'var(--tint-blue-fg)' }}
                  onChange={e => { const v = Number(e.target.value); setV(activeTab, { cnWeight: v }); _saveGenPref(initChar.id, activeTab, 'cnWeight', v) }} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>1.5</span>
                <span style={{ fontSize: 12, color: 'var(--tint-blue-fg)', minWidth: 30, textAlign: 'right' }}>{(vState.cnWeight ?? 0.85).toFixed(2)}</span>
              </div>
            )}
            {vState.pendingQueue.length > 0 && (
              <div style={{ marginBottom: 10, border: '1px solid var(--border)', borderRadius: 10, padding: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>{vState.pendingQueue[0].label}</span>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>待確認 {vState.pendingQueue.length} 張</span>
                </div>
                <img src={vState.pendingQueue[0].url} style={{ ...S.genImg, marginTop: 0, cursor: 'zoom-in' }} alt="pending"
                  onClick={() => setLightboxSrc(vState.pendingQueue[0].url)} />
                <div style={{ ...S.btnRow, marginTop: 6 }}>
                  <button style={{ ...S.btn, flex: 1, padding: '7px 0', fontSize: 13 }}
                    disabled={vState.savingGen || vState.aiImages.length >= 8} onClick={saveVariantPendingFirst}>
                    {vState.savingGen ? <><Spinner />儲存中...</> : vState.aiImages.length >= 8 ? '已達上限' : '儲存此圖'}
                  </button>
                  <button style={S.btnSm} disabled={vState.savingGen} onClick={() => { URL.revokeObjectURL(vState.pendingQueue[0].url); setV(activeTab, { pendingQueue: vState.pendingQueue.slice(1) }) }}>捨棄</button>
                </div>
                {vState.lastTimings && (
                  <div style={{ marginTop: 8, padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 5, fontWeight: 600 }}>⏱ 生成耗時</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                      {[
                        vState.lastTimings.vision_extract    != null && ['視覺分析',   vState.lastTimings.models?.vision,   vState.lastTimings.vision_extract],
                        vState.lastTimings.body_coverage     != null && ['姿態偵測',   vState.lastTimings.models?.vision,   vState.lastTimings.body_coverage],
                        vState.lastTimings.compile_prompt    != null && ['提示詞編譯', vState.lastTimings.models?.text,     vState.lastTimings.compile_prompt],
                        vState.lastTimings.compile_ai_prompt != null && ['AI提示詞',  vState.lastTimings.models?.text,     vState.lastTimings.compile_ai_prompt],
                        vState.lastTimings.pass1             != null && ['Pass 1 粗稿', vState.lastTimings.models?.workflow, vState.lastTimings.pass1],
                        vState.lastTimings.upload            != null && ['圖片上傳',  null,                                 vState.lastTimings.upload],
                        vState.lastTimings.comfyui           != null && ['ComfyUI 生成', vState.lastTimings.models?.workflow, vState.lastTimings.comfyui],
                      ].filter(Boolean).map(([label, model, sec]) => (
                        <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                          <span style={{ color: 'var(--muted)' }}>
                            {label}
                            {model && <span style={{ color: 'var(--muted)', marginLeft: 4, fontSize: 10 }}>({model})</span>}
                          </span>
                          <span style={{ fontFamily: 'monospace' }}>{sec}s</span>
                        </div>
                      ))}
                      {(() => {
                        const keys = ['vision_extract','body_coverage','compile_prompt','compile_ai_prompt','canvas_expand','upload','comfyui']
                        const sum = keys.reduce((a, k) => a + (vState.lastTimings[k] ?? 0), 0)
                        const other = Math.round((vState.lastTimings.total - sum) * 10) / 10
                        return other > 0.5 ? (
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                            <span style={{ color: 'var(--muted)' }}>其他</span>
                            <span style={{ fontFamily: 'monospace' }}>{other}s</span>
                          </div>
                        ) : null
                      })()}
                      <div style={{ borderTop: '1px solid var(--border)', marginTop: 3, paddingTop: 3, display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                        <span style={{ color: 'var(--accent)', fontWeight: 600 }}>總計</span>
                        <span style={{ color: 'var(--accent)', fontFamily: 'monospace', fontWeight: 600 }}>{vState.lastTimings.total}s</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
            {vState.aiImages.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {vState.aiImages.map((img, idx) => (
                  <div key={idx} style={{ borderRadius: 8, overflow: 'hidden' }}>
                    <img src={apiUrl(`/characters/${char.id}/variants/${activeTab}/ai-images/${idx}?t=${img}`)}
                      style={{ width: '100%', display: 'block', borderRadius: 8, cursor: 'zoom-in' }} alt={`AI圖${idx + 1}`}
                      onClick={() => setLightboxSrc(apiUrl(`/characters/${char.id}/variants/${activeTab}/ai-images/${idx}?t=${img}`))} />
                    <div style={{ display: 'flex', gap: 4, marginTop: 4, justifyContent: 'center' }}>
                      <a href={apiUrl(`/characters/${char.id}/variants/${activeTab}/ai-images/${idx}`)}
                        download={`${char.name}_v${activeTab}_ai_${idx + 1}.png`}
                        style={{ ...S.btnSm, fontSize: 11, padding: '3px 8px', textDecoration: 'none', textAlign: 'center' }}>下載</a>
                      {vState.deletingAiIdx === idx
                        ? <>
                            <button style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, border: 'none', background: 'var(--tint-red-bg)', color: 'var(--danger)', cursor: 'pointer' }} onClick={() => deleteVariantAiImage(activeTab, idx)}>確認</button>
                            <button style={{ ...S.btnSm, fontSize: 11, padding: '3px 8px' }} onClick={() => setV(activeTab, { deletingAiIdx: null })}>取消</button>
                          </>
                        : <button style={{ ...S.btnDanger, fontSize: 11, padding: '3px 8px' }} onClick={() => setV(activeTab, { deletingAiIdx: idx })}>移除</button>
                      }
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right col: variant fields (name locked) */}
        <div style={S.detailRight}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={S.sectionLabel}>角色資料（可編輯）</span>
            <button style={S.btnSm} disabled={vState.savingFields} onClick={saveVariantFields}>
              {vState.savingFields ? <><Spinner />儲存中...</> : '儲存所有變更'}
            </button>
          </div>
          <div style={S.row}>
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>角色名稱（鎖定）</label>
              <input style={{ ...S.input, opacity: 0.5, cursor: 'not-allowed' }} value={char.name} readOnly />
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}>代表色</label>
              <div style={S.colorRow}>
                <input type="color" style={S.colorPicker} value={vState.color || '#888888'} onChange={e => setV(activeTab, { color: e.target.value })} />
                <span style={S.colorCode}>{vState.color || '未設定'}</span>
                {vState.color && <button style={{ ...S.btnSm, fontSize: 11, padding: '4px 10px' }} onClick={() => setV(activeTab, { color: '' })}>清除</button>}
              </div>
            </div>
          </div>
          <div style={S.row}>
            <div style={S.fieldGroup}>
              <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>年齡</label>
              <input type="number" style={S.input} value={vState.age} onChange={e => setV(activeTab, { age: e.target.value })} placeholder="例如：18" min="0" max="9999" />
            </div>
            <div style={S.fieldGroup}>
              <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>身高 (cm)</label>
              <input type="number" style={S.input} value={vState.height} onChange={e => setV(activeTab, { height: e.target.value })} placeholder="例如：162" min="50" max="250" />
            </div>
            <div style={{ ...S.fieldGroup, flex: 2 }}>
              <label style={S.label}>生日</label>
              <input style={S.input} value={vState.birthday} onChange={e => setV(activeTab, { birthday: e.target.value })} placeholder="例如：5月16日" />
            </div>
          </div>
          <div>
            <label style={S.label}>性別</label>
            <GenderPicker value={vState.gender} onChange={v => setV(activeTab, { gender: v })} />
          </div>
          <div>
            <label style={S.label}><span style={{ color: 'var(--accent)' }}>✦ </span>外貌 / 個性特徵</label>
            <textarea style={{ ...S.textarea, minHeight: 70 }} value={vState.traits} onChange={e => setV(activeTab, { traits: e.target.value })} placeholder="髮色、體型、個性..." />
          </div>
          <div>
            <label style={S.label}>行為模式</label>
            <textarea style={{ ...S.textarea, minHeight: 70 }} value={vState.behavior} onChange={e => setV(activeTab, { behavior: e.target.value })} placeholder="面對危機的反應、習慣..." />
          </div>
          <div>
            <label style={S.label}>說話風格</label>
            <textarea style={{ ...S.textarea, minHeight: 50 }} value={vState.voice} onChange={e => setV(activeTab, { voice: e.target.value })} placeholder="語氣、口頭禪..." />
          </div>
          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={vState.visionEnabled ?? true} onChange={e => { setV(activeTab, { visionEnabled: e.target.checked }); _saveGenPref(initChar.id, activeTab, 'visionEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
              <span style={{ color: 'var(--accent)' }}>✦ </span>草圖視覺特徵
            </label>
            <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>開啟時用視覺模型從概念圖抽取特徵加入提示詞；關閉則僅靠欄位設定，交由 CN／畫風主導</p>
          </div>
          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={vState.outfitEnabled} onChange={e => { setV(activeTab, { outfitEnabled: e.target.checked }); _saveGenPref(initChar.id, activeTab, 'outfitEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
              <span style={{ color: 'var(--accent)' }}>✦ </span>服裝設定
            </label>
            {vState.outfitEnabled && (
              <>
                <textarea style={{ ...S.textarea, minHeight: 60 }}
                  value={vState.outfit} onChange={e => setV(activeTab, { outfit: e.target.value })}
                  placeholder="例如：白色禮服、黑色窄裙、學生制服、和服..." />
                <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>服裝描述會加入生成提示詞，影響圖片中的穿著</p>
              </>
            )}
          </div>

          <div>
            <label style={{ ...S.label, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={vState.aiPromptEnabled} onChange={e => { setV(activeTab, { aiPromptEnabled: e.target.checked }); _saveGenPref(initChar.id, activeTab, 'aiPromptEnabled', e.target.checked) }}
                style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
              <span style={{ color: 'var(--accent)' }}>✦ </span>AI 提示詞
            </label>
            {vState.aiPromptEnabled && (
              <>
                <textarea style={{ ...S.textarea, minHeight: 60, fontFamily: 'monospace', fontSize: 13 }}
                  value={vState.aiPrompt} onChange={e => setV(activeTab, { aiPrompt: e.target.value })}
                  placeholder="中英文皆可，例如：flat color, clean lineart" />
                <p style={{ ...S.muted, fontSize: 11, marginTop: 4 }}>中英文皆接受，獨立編譯後置於 prompt 最前端</p>
              </>
            )}
          </div>
          <div>
            <label style={S.label}>創作筆記</label>
            <textarea style={{ ...S.textarea, minHeight: 120 }} value={vState.notes} onChange={e => setV(activeTab, { notes: e.target.value })} placeholder="隨時新增想法..." />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ ...S.label, marginBottom: 0, fontFamily: 'monospace', letterSpacing: 1 }}>DEBUG PROMPT</span>
              <button style={{ ...S.btnSm, fontSize: 11, padding: '3px 10px' }} onClick={() => setV(activeTab, { showDebugPrompt: !vState.showDebugPrompt })}>
                {vState.showDebugPrompt ? '隱藏' : '顯示'}
              </button>
            </div>
            {vState.showDebugPrompt && (
              vState.lastDebugPrompt
                ? <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontSize: 10, color: 'var(--tint-blue-fg)', letterSpacing: 1, fontFamily: 'monospace' }}>中文描述（AI 翻譯前）</div>
                      {vState.lastFlatDraft != null && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: vState.lastFlatDraft ? 'var(--tint-amber-bg)' : 'var(--tint-green-bg)',
                          color: vState.lastFlatDraft ? 'var(--tint-amber-fg)' : 'var(--tint-green-fg)',
                          border: `1px solid ${vState.lastFlatDraft ? 'var(--tint-amber-bg)' : 'var(--tint-green-bg)'}` }}>
                          {vState.lastFlatDraft ? '單色稿 → 文字優先' : '正式上色 → 視覺優先'}
                        </div>
                      )}
                      {vState.lastIpaUsed != null && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: vState.lastIpaUsed ? 'var(--tint-blue-bg)' : 'var(--surface-2)',
                          color: vState.lastIpaUsed ? 'var(--tint-blue-fg)' : 'var(--muted)',
                          border: `1px solid ${vState.lastIpaUsed ? 'var(--tint-blue-border)' : 'var(--border-strong)'}` }}>
                          {vState.lastIpaUsed ? 'IP-Adapter ON' : 'IP-Adapter OFF'}
                        </div>
                      )}
                      {vState.lastPromptProfile && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: vState.lastPromptProfile.startsWith('profile:') ? 'var(--tint-purple-bg)' : 'var(--surface-2)',
                          color: vState.lastPromptProfile.startsWith('profile:') ? 'var(--tint-purple-fg)' : 'var(--muted)',
                          border: `1px solid ${vState.lastPromptProfile.startsWith('profile:') ? 'var(--tint-purple-bg)' : 'var(--border-strong)'}` }}>
                          {vState.lastPromptProfile}
                        </div>
                      )}
                      {vState.lastCoverage && (
                        <div style={{ fontSize: 10, padding: '1px 7px', borderRadius: 4, fontFamily: 'monospace',
                          background: vState.lastCoverage.includes('→') ? 'var(--tint-amber-bg)' : 'var(--surface-2)',
                          color: vState.lastCoverage.includes('→') ? 'var(--tint-amber-fg)' : 'var(--muted)',
                          border: `1px solid ${vState.lastCoverage.includes('→') ? 'var(--tint-amber-bg)' : 'var(--border-strong)'}` }}>
                          {vState.lastCoverage}
                        </div>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--tint-green-fg)', background: 'var(--tint-blue-bg)', padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, border: '1px solid var(--tint-green-bg)', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                      {vState.lastRawDesc ?? '—'}
                    </div>
                    {vState.lastAiPromptCompiled !== null && (
                      <>
                        <div style={{ fontSize: 10, letterSpacing: 1, fontFamily: 'monospace', marginTop: 2,
                          color: vState.lastAiPromptCompiled === '[compilation_failed]' ? 'var(--danger)' : 'var(--tint-amber-fg)' }}>
                          AI 提示詞編譯結果{vState.lastAiPromptCompiled === '[compilation_failed]' ? ' ⚠ 失敗' : '（置於 prompt 首位）'}
                        </div>
                        <div style={{ fontSize: 11, padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, fontFamily: 'monospace',
                          color: vState.lastAiPromptCompiled === '[compilation_failed]' ? 'var(--danger)' : 'var(--tint-amber-fg)',
                          background: vState.lastAiPromptCompiled === '[compilation_failed]' ? 'var(--tint-red-bg)' : 'var(--tint-amber-bg)',
                          border: `1px solid ${vState.lastAiPromptCompiled === '[compilation_failed]' ? 'var(--tint-red-bg)' : 'var(--tint-amber-bg)'}` }}>
                          {vState.lastAiPromptCompiled === '[compilation_failed]' ? 'AI 提示詞未套用（Ollama 翻譯錯誤）' : vState.lastAiPromptCompiled}
                        </div>
                      </>
                    )}
                    <div style={{ fontSize: 10, color: 'var(--tint-purple-fg)', letterSpacing: 1, fontFamily: 'monospace', marginTop: 2 }}>最終 Prompt（英文）</div>
                    <div style={{ fontSize: 11, color: 'var(--tint-purple-fg)', background: 'var(--tint-purple-bg)', padding: '8px 10px', borderRadius: 6, wordBreak: 'break-all', lineHeight: 1.5, border: '1px solid var(--tint-purple-bg)', fontFamily: 'monospace' }}>
                      {vState.lastDebugPrompt}
                    </div>
                  </div>
                : <p style={{ ...S.muted, fontSize: 11 }}>尚未生成變體圖，無 prompt 記錄</p>
            )}
          </div>
        </div>
      </div>
      )}
      {lightboxSrc && <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />}
    </div>
  )
}
