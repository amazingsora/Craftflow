import { useState, useEffect } from 'react'
import { notifyEnabled, soundEnabled, setNotifyEnabled, setSoundEnabled, ensureNotifyPermission, notifyPermission, requestNotifyPermission } from '../notify.js'

const S = {
  root: { display: 'flex', flexDirection: 'column', gap: 24 },
  section: {
    display: 'flex', flexDirection: 'column', gap: 12,
    padding: '16px 20px',
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    borderRadius: 10,
  },
  sectionTitle: { fontSize: 13, fontWeight: 600, color: 'var(--muted)', marginBottom: 4 },
  radioGroup: { display: 'flex', flexDirection: 'column', gap: 10 },
  radioLabel: {
    display: 'flex', alignItems: 'flex-start', gap: 10,
    cursor: 'pointer', padding: '10px 14px', borderRadius: 8,
    border: '1px solid var(--border)', transition: 'border-color .15s',
  },
  radioLabelActive: { borderColor: 'var(--accent)', background: 'var(--accent-soft)' },
  radioTitle: { fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 2 },
  radioDesc: { fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 },
  radio: { marginTop: 2, accentColor: 'var(--accent)', width: 16, height: 16, flexShrink: 0 },
  configArea: { display: 'flex', flexDirection: 'column', gap: 12 },
  fieldLabel: { fontSize: 12, color: 'var(--muted)', marginBottom: 4, display: 'block' },
  select: {
    width: '100%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text)',
    padding: '8px 10px',
    fontSize: 13,
    outline: 'none',
  },
  input: {
    width: '100%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text)',
    padding: '8px 10px',
    fontSize: 13,
    outline: 'none',
    boxSizing: 'border-box',
  },
  sliderRow: { display: 'flex', alignItems: 'center', gap: 10 },
  slider: { flex: 1, accentColor: 'var(--accent)' },
  sliderVal: { width: 36, textAlign: 'right', color: 'var(--text)', fontSize: 13, fontWeight: 600 },
  statusRow: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 },
  dot: (online) => ({
    width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
    background: online ? 'var(--tint-green-fg)' : 'var(--danger)',
  }),
  statusText: { color: 'var(--muted)' },
  saveBtn: {
    alignSelf: 'flex-start',
    padding: '8px 20px', borderRadius: 8, border: 'none',
    background: 'var(--accent)', color: 'var(--accent-contrast)',
    fontSize: 13, fontWeight: 600, cursor: 'pointer',
  },
  savedMsg: { fontSize: 12, color: 'var(--tint-green-fg)', alignSelf: 'center' },
  infoBox: {
    padding: '10px 14px', borderRadius: 8,
    background: 'var(--accent-soft)',
    border: '1px solid var(--accent-border)',
    fontSize: 12, color: 'var(--muted)', lineHeight: 1.6,
  },
  workflowList: { display: 'flex', flexDirection: 'column', gap: 6 },
  workflowItem: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '8px 12px', borderRadius: 6,
    border: '1px solid var(--border)',
    fontSize: 12, color: 'var(--text)',
  },
  workflowActive: { borderColor: 'var(--accent)', color: 'var(--accent)' },
  workflowBadge: {
    fontSize: 10, padding: '1px 6px', borderRadius: 4, fontWeight: 600,
    background: 'var(--accent-soft-2)', color: 'var(--accent)',
  },
  loraNone: { color: 'var(--muted)', fontSize: 12, marginTop: 2 },
}

export default function SettingsTab({
  generationMode, setGenerationMode,
  checkpoints, activeCheckpoint, onCheckpointChange,
  workflows, activeWorkflow, onWorkflowChange,
  visionModels, visionOnlyModels, modelCaps,
  activeVisionModel, onVisionModelChange,
  activeTextModel, onTextModelChange,
}) {
  // 後端未升級（無 vision_models 欄位）時退回完整清單，行為不破壞
  const _visionList = (visionOnlyModels && visionOnlyModels.length > 0) ? visionOnlyModels : visionModels
  const _caps = modelCaps ?? {}
  const _hasVision = (m) => (_caps[m] ?? []).includes('vision')
  // 文字欄沿用完整清單，但把多模態模型標出來，方便辨識
  const _textLabel = (m) => _hasVision(m) ? `${m}（多模態）` : m
  const [comfyStatus, setComfyStatus] = useState(null)
  const [manualCheckpoint, setManualCheckpoint] = useState(activeCheckpoint)
  const [ckptSaved, setCkptSaved] = useState(false)

  // LoRA state
  const [loraList, setLoraList] = useState([])
  const [activeLora, setActiveLora] = useState(
    () => localStorage.getItem('craftflow_lora') ?? ''
  )
  const [loraStrength, setLoraStrength] = useState(
    () => parseFloat(localStorage.getItem('craftflow_lora_strength') ?? '0.8')
  )
  const [loraSaved, setLoraSaved] = useState(false)

  useEffect(() => {
    // 連線檢查 + 同時拉 LoRA 清單
    fetch('/api/v1/settings/loras')
      .then(r => { setComfyStatus(r.ok); return r.ok ? r.json() : null })
      .then(data => {
        if (!data) return
        setLoraList(data.loras ?? [])
        // 若伺服器已有 active lora 且本地沒記憶，以伺服器為準
        if (!localStorage.getItem('craftflow_lora') && data.active?.name) {
          setActiveLora(data.active.name)
          setLoraStrength(data.active.strength ?? 0.8)
        }
      })
      .catch(() => setComfyStatus(false))
  }, [])

  useEffect(() => {
    setManualCheckpoint(activeCheckpoint)
  }, [activeCheckpoint])

  // workflow が 1 つしかない場合など、activeWorkflow がリストに存在しない時に自動補正
  useEffect(() => {
    if (workflows.length > 0 && !workflows.includes(activeWorkflow)) {
      onWorkflowChange(workflows[0])
    }
  }, [workflows, activeWorkflow])

  const handleSaveCheckpoint = () => {
    if (!manualCheckpoint.trim()) return
    onCheckpointChange(manualCheckpoint.trim())
    setCkptSaved(true)
    setTimeout(() => setCkptSaved(false), 2000)
  }

  const handleLoraChange = (name) => {
    setActiveLora(name)
    localStorage.setItem('craftflow_lora', name)
    syncLora(name, loraStrength)
  }

  const handleStrengthChange = (v) => {
    setLoraStrength(v)
    localStorage.setItem('craftflow_lora_strength', String(v))
  }

  const handleSaveLora = () => {
    syncLora(activeLora, loraStrength)
    setLoraSaved(true)
    setTimeout(() => setLoraSaved(false), 2000)
  }

  const syncLora = (name, strength) => {
    fetch('/api/v1/settings/lora', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, strength }),
    }).catch(() => {})
  }

  const [notifyOn, setNotifyOn] = useState(notifyEnabled())
  const [soundOn, setSoundOn] = useState(soundEnabled())
  const [notifPerm, setNotifPerm] = useState(notifyPermission())

  return (
    <div style={S.root}>
      {/* ComfyUI 連線狀態 */}
      <div style={S.section}>
        <div style={S.sectionTitle}>ComfyUI 連線狀態</div>
        <div style={S.statusRow}>
          <div style={S.dot(comfyStatus === true)} />
          <span style={S.statusText}>
            {comfyStatus === null ? '檢查中…'
              : comfyStatus ? 'ComfyUI 已連線 (localhost:8188)'
              : 'ComfyUI 離線 — 請啟動後重新整理頁面'}
          </span>
        </div>
      </div>

      {/* 生成完成通知 */}
      <div style={S.section}>
        <div style={S.sectionTitle}>生成完成通知</div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text)' }}>
          <input type="checkbox" checked={notifyOn} onChange={e => { const v = e.target.checked; setNotifyOn(v); setNotifyEnabled(v); if (v) ensureNotifyPermission() }} />
          桌面通知（生成 / 訓練完成時，螢幕右下角彈出）
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text)' }}>
          <input type="checkbox" checked={soundOn} onChange={e => { const v = e.target.checked; setSoundOn(v); setSoundEnabled(v) }} />
          通知音
        </label>
        <div style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span>桌面通知權限：{notifPerm === 'granted' ? '已授權' : notifPerm === 'denied' ? '已封鎖（請到瀏覽器/系統通知設定開啟）' : notifPerm === 'unsupported' ? '瀏覽器不支援' : '未授權'}</span>
          {notifPerm !== 'granted' && notifPerm !== 'unsupported' && (
            <button
              style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)', fontSize: 12, cursor: 'pointer' }}
              onClick={async () => { const p = await requestNotifyPermission(); setNotifPerm(p) }}
            >要求授權</button>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)' }}>
          註：app 內右下角提示一定會顯示；OS 桌面通知需授權，且 Windows「專注輔助 / 勿擾」開啟時會被系統隱藏。
        </div>
      </div>

      {/* 視覺模型 — 僅列具視覺能力（capabilities 含 vision）的模型 */}
      <div style={S.section}>
        <div style={S.sectionTitle}>視覺模型（Ollama）</div>
        <div style={S.configArea}>
          {_visionList && _visionList.length > 0 ? (
            <div>
              <span style={S.fieldLabel}>選擇模型（草圖問答、角色概念圖分析）— 僅顯示支援視覺的模型</span>
              <select
                style={S.select}
                value={activeVisionModel}
                onChange={e => onVisionModelChange(e.target.value)}
              >
                {_visionList.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          ) : (
            <div style={S.infoBox}>
              {visionModels && visionModels.length > 0
                ? '目前已安裝的模型皆不支援視覺。請先 ollama pull 一顆 VL 模型（如 huihui_ai/qwen3-vl-abliterated）。'
                : '無法連接 Ollama，模型清單不可用。請確認 Ollama 正在執行。'}
            </div>
          )}
        </div>
      </div>

      {/* 文字／提示詞模型 — 文字分析、prompt 生成、翻譯共用 */}
      <div style={S.section}>
        <div style={S.sectionTitle}>文字／提示詞模型（Ollama）</div>
        <div style={S.configArea}>
          {visionModels && visionModels.length > 0 ? (
            <div>
              <span style={S.fieldLabel}>選擇模型（中文描述 → SD 英文 tag、角色文字分析）</span>
              <select
                style={S.select}
                value={activeTextModel}
                onChange={e => onTextModelChange(e.target.value)}
              >
                {visionModels.map(m => <option key={m} value={m}>{_textLabel(m)}</option>)}
              </select>
            </div>
          ) : (
            <div style={S.infoBox}>
              無法連接 Ollama，模型清單不可用。請確認 Ollama 正在執行。
            </div>
          )}
        </div>
      </div>

      {/* 生成模式 */}
      <div style={S.section}>
        <div style={S.sectionTitle}>生成模式</div>
        <div style={S.radioGroup}>
          <label
            style={{ ...S.radioLabel, ...(generationMode === 'checkpoint' ? S.radioLabelActive : {}) }}
            onClick={() => setGenerationMode('checkpoint')}
          >
            <input
              type="radio" name="genMode" value="checkpoint"
              checked={generationMode === 'checkpoint'}
              onChange={() => setGenerationMode('checkpoint')}
              style={S.radio}
            />
            <div>
              <div style={S.radioTitle}>Checkpoint + LoRA 模式</div>
              <div style={S.radioDesc}>
                使用系統 text_to_image 工作流，手動選擇 Checkpoint 與全局 LoRA。
              </div>
            </div>
          </label>
          <label
            style={{ ...S.radioLabel, ...(generationMode === 'workflow' ? S.radioLabelActive : {}) }}
            onClick={() => setGenerationMode('workflow')}
          >
            <input
              type="radio" name="genMode" value="workflow"
              checked={generationMode === 'workflow'}
              onChange={() => setGenerationMode('workflow')}
              style={S.radio}
            />
            <div>
              <div style={S.radioTitle}>自訂 Workflow 模式</div>
              <div style={S.radioDesc}>
                使用從 ComfyUI 匯出的 API 格式 JSON，Checkpoint/LoRA 由 workflow 本身決定。
              </div>
            </div>
          </label>
        </div>
      </div>

      {/* Checkpoint 設定 */}
      {generationMode === 'checkpoint' && (
        <div style={S.section}>
          <div style={S.sectionTitle}>Checkpoint</div>
          {checkpoints.length > 0 ? (
            <div>
              <span style={S.fieldLabel}>選擇模型</span>
              <select
                style={S.select}
                value={activeCheckpoint}
                onChange={e => onCheckpointChange(e.target.value)}
              >
                {checkpoints.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          ) : (
            <div style={S.configArea}>
              <div style={S.infoBox}>
                ComfyUI 離線，無法讀取清單。可手動輸入名稱，連線後自動生效。
              </div>
              <div>
                <span style={S.fieldLabel}>手動輸入 Checkpoint 名稱</span>
                <input
                  style={S.input}
                  value={manualCheckpoint}
                  onChange={e => setManualCheckpoint(e.target.value)}
                  placeholder="例如：Illustrious-XL-v2.0.safetensors"
                  onKeyDown={e => e.key === 'Enter' && handleSaveCheckpoint()}
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <button style={S.saveBtn} onClick={handleSaveCheckpoint}>儲存</button>
                {ckptSaved && <span style={S.savedMsg}>✓ 已儲存</span>}
              </div>
            </div>
          )}
        </div>
      )}

      {/* LoRA 設定 */}
      {generationMode === 'checkpoint' && (
        <div style={S.section}>
          <div style={S.sectionTitle}>全局 LoRA</div>
          <div style={S.configArea}>
            {loraList.length > 0 ? (
              <div>
                <span style={S.fieldLabel}>選擇 LoRA（留空 = 不套用）</span>
                <select
                  style={S.select}
                  value={activeLora}
                  onChange={e => handleLoraChange(e.target.value)}
                >
                  <option value="">— 不使用 LoRA —</option>
                  {loraList.map(l => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
            ) : (
              <div style={S.configArea}>
                <div style={S.infoBox}>
                  ComfyUI 離線，無法讀取 LoRA 清單。可手動輸入 LoRA 檔名。
                </div>
                <div>
                  <span style={S.fieldLabel}>手動輸入 LoRA 名稱（留空 = 不套用）</span>
                  <input
                    style={S.input}
                    value={activeLora}
                    onChange={e => { setActiveLora(e.target.value); localStorage.setItem('craftflow_lora', e.target.value) }}
                    placeholder="例如：my_style_v1.safetensors"
                  />
                </div>
              </div>
            )}

            {/* 強度滑桿（有選 LoRA 才顯示） */}
            {activeLora && (
              <div>
                <span style={S.fieldLabel}>強度：{loraStrength.toFixed(2)}</span>
                <div style={S.sliderRow}>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>0</span>
                  <input
                    type="range" min={0} max={1} step={0.05}
                    value={loraStrength}
                    style={S.slider}
                    onChange={e => handleStrengthChange(Number(e.target.value))}
                  />
                  <span style={S.sliderVal}>{loraStrength.toFixed(2)}</span>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button style={S.saveBtn} onClick={handleSaveLora}>套用</button>
              {loraSaved && <span style={S.savedMsg}>✓ 已套用</span>}
              {activeLora && (
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                  每次生成都會注入此 LoRA
                </span>
              )}
              {!activeLora && (
                <span style={S.loraNone}>未選擇，不會注入</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Workflow 設定 */}
      {generationMode === 'workflow' && (
        <div style={S.section}>
          <div style={S.sectionTitle}>自訂 Workflow</div>
          {workflows.length > 0 ? (
            <div style={S.configArea}>
              <div>
                <span style={S.fieldLabel}>選擇 Workflow</span>
                <select
                  style={S.select}
                  value={activeWorkflow}
                  onChange={e => onWorkflowChange(e.target.value)}
                >
                  {workflows.map(w => (
                    <option key={w} value={w}>{w.replace('.json', '')}</option>
                  ))}
                </select>
              </div>
              <div style={S.workflowList}>
                {workflows.map(w => (
                  <div key={w} style={{ ...S.workflowItem, ...(w === activeWorkflow ? S.workflowActive : {}) }}>
                    <span>{w.replace('.json', '')}</span>
                    {w === activeWorkflow && <span style={S.workflowBadge}>使用中</span>}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={S.infoBox}>
              尚無自訂 workflow。<br /><br />
              請在 ComfyUI 中：<br />
              1. 啟用 <strong>Dev Mode</strong>（齒輪圖示 → Enable Dev mode options）<br />
              2. 點擊 <strong>Save (API format)</strong> 匯出 JSON<br />
              3. 放入專案目錄：<code style={{ fontSize: 11 }}>data/custom_workflows/</code><br /><br />
              放入後重新整理頁面即可看到。
            </div>
          )}
        </div>
      )}
    </div>
  )
}
