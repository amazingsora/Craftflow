/**
 * CapabilityNotice — 能力閘控可視化（2026-07-25 D'）
 *
 * 背景：IPA / CN 控制項原本用 `{ipaSupported && (...)}` 條件式渲染，模型不支援時整組
 * 從畫面消失。使用者看不到東西、也不知道為什麼，只覺得「功能壞了」。
 * 改為一律渲染：不支援時顯示置灰卡片，明說「為什麼不支援」與「替代方案是什麼」。
 *
 * 純呈現元件，不含狀態、不發 API。
 */

// family → 不支援原因（沒對到就用泛用說法，不假裝知道細節）
const REASON = {
  anima: {
    ipa: 'Anima 為 Cosmos-Predict2 架構，沒有對應的 IP-Adapter（本機的 ip-adapter-plus_sdxl 是 SDXL 專用，維度不符）。',
    cn: 'Anima 官方未提供 ControlNet 支援。社群的 ControlNet-LLLite 可補上這塊，但需要另外安裝節點與權重（未安裝時自動改走 img2img）。',
  },
  flux: {
    ipa: 'Flux 架構不支援目前的 IP-Adapter 注入。',
    cn: 'Flux 架構不支援目前的 ControlNet 注入。',
  },
}

const FALLBACK_HINT = {
  // D'-1：IPA 的替代 —— 既有的 vision→prompt 路徑（use_vision），本來就不受能力閘控影響
  ipa_vision:
    '替代方案：改用「視覺特徵抽取」——參考圖會先由視覺模型讀成文字特徵再併入提示詞，同樣能帶出外觀。開啟上方的視覺特徵選項即可。',
  // D'-2：CN 的替代 —— img2img 低 denoise
  cn_img2img:
    '替代方案：已自動改用 img2img 構圖引導（參考圖進 latent，降低重繪幅度來貼合構圖）。控制項仍可使用，強度滑桿沿用同一個值。',
  // 2026-08-12：CN 的首選替代 —— ControlNet-LLLite（真條件注入，非 latent 污染）
  cn_lllite:
    '已改走 ControlNet-LLLite：草圖以低秩修正注入 DiT 的 attention，latent 仍從空白起跑 —— 與 SDXL ControlNet 同機制，姿勢約束不會犧牲色彩。強度滑桿即 LLLite strength。',
}

export default function CapabilityNotice({ title, kind, family, fallback }) {
  const reason = REASON[family]?.[kind] || `目前的模型（${family || '未知'}）不支援這項功能。`
  const hint =
    kind === 'ipa' ? FALLBACK_HINT.ipa_vision
      : fallback === 'lllite' ? FALLBACK_HINT.cn_lllite
        : fallback === 'img2img' ? FALLBACK_HINT.cn_img2img
          : null

  return (
    <div
      style={{
        border: '1px dashed var(--border)', borderRadius: 10,
        padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6,
        opacity: 0.75,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--muted)' }}>{title}</span>
        <span
          style={{
            fontSize: 11, padding: '3px 10px', borderRadius: 6,
            border: '1px solid var(--border)', color: 'var(--muted)',
            cursor: 'not-allowed', whiteSpace: 'nowrap',
          }}
          title={reason}
        >
          此模型不支援
        </span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--muted)', lineHeight: 1.5 }}>{reason}</div>
      {hint && (
        <div style={{ fontSize: 11, color: 'var(--muted)', lineHeight: 1.5, opacity: 0.9 }}>
          {hint}
        </div>
      )}
    </div>
  )
}
