# Craftflow Consistency Report

- Source file: `writing/drafts/consistency_test.md`
- Generated at: 2026-05-02T17:29:39

## Summary

- Paragraphs analyzed: 4
- Total issues: **6** (high: 3, medium: 3, low: 0)

---

## Paragraph 1
- Mentioned characters: 艾莉絲
- Issues: 1

> 這是一個正常的開場段落。艾莉絲走進房間，輕輕關上了門。她看了...

### [MEDIUM] character_voice → 艾莉絲
- Source: `semantic`
- 情緒外顯方式不符 voice_style 短句、克制
- Evidence: `情緒激動到難以自抑`

## Paragraph 2
- Mentioned characters: 艾莉絲
- Issues: 2

> 艾莉絲突然大聲叫罵了起來，整個酒館的客人都嚇了一跳。她拍著桌...

### [HIGH] character_behavior → 艾莉絲
- Source: `surface`
- Forbidden action keyword hit: '大聲叫罵'
- Evidence: `艾莉絲突然大聲叫罵了起來，整個酒館的客人都嚇了一跳。她拍著...`

### [MEDIUM] character_voice → 艾莉絲
- Source: `semantic`
- 情緒外顯方式不符 voice_style 短句、克制
- Evidence: `情緒激動到難以自抑`

## Paragraph 3
- Mentioned characters: 艾莉絲
- Issues: 3

> Alice 拿出手機，撥了一通電話。電話那頭沒有人接。她嘆了...

### [HIGH] forbidden_keyword → 主世界
- Source: `surface`
- World forbidden keyword hit: '手機'
- Evidence: `Alice 拿出手機，撥了一通電話。電話那頭沒有人接。她嘆了...`

### [HIGH] forbidden_keyword → 主世界
- Source: `surface`
- World forbidden keyword hit: '飛機'
- Evidence: `...她嘆了口氣，把手機收回口袋，走到窗邊看著飛機從雲層下方掠過。`

### [MEDIUM] character_voice → 艾莉絲
- Source: `semantic`
- 情緒外顯方式不符 voice_style 短句、克制
- Evidence: `情緒激動到難以自抑`

## Paragraph 4
- Mentioned characters: (none)
- Issues: 0

> 這是一段沒有任何違規的描寫。月光透過木窗的縫隙落在地板上，把...
