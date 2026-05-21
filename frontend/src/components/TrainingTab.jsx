import React, { useState, useEffect, useRef, useCallback } from 'react'

const API = '/api/v1/training'

const S = {
  root: { display: 'flex', flexDirection: 'column', gap: 24 },
  section: { display: 'flex', flexDirection: 'column', gap: 12 },
  sectionTitle: { fontSize: 13, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 1 },
  row: { display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' },
  btn: {
    padding: '7px 18px', borderRadius: 8, border: '1px solid var(--border)',
    background: 'var(--surface2, #1e2130)', color: 'var(--text)', fontSize: 13,
    cursor: 'pointer', transition: 'opacity .15s',
  },
  btnPrimary: { background: 'var(--accent)', color: '#fff', border: 'none' },
  btnDanger: { background: '#5c2d2d', color: '#f77', border: 'none' },
  input: {
    padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border)',
    background: 'var(--surface2, #1e2130)', color: 'var(--text)', fontSize: 13, outline: 'none',
  },
  label: { fontSize: 12, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 4 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12 },
  imgCard: {
    background: 'var(--surface2, #1e2130)', border: '1px solid var(--border)',
    borderRadius: 8, overflow: 'hidden', display: 'flex', flexDirection: 'column',
  },
  imgThumb: { width: '100%', aspectRatio: '1/1', objectFit: 'cover' },
  imgCaption: {
    padding: '4px 8px 8px', fontSize: 11,
    background: 'none', border: 'none', borderTop: '1px solid var(--border)',
    color: 'var(--text)', outline: 'none', width: '100%', resize: 'none', minHeight: 56,
    fontFamily: 'inherit',
  },
  imgFooter: { display: 'flex', justifyContent: 'space-between', padding: '2px 6px 6px', alignItems: 'center' },
  delBtn: { fontSize: 11, color: 'var(--muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px' },
  jobCard: {
    background: 'var(--surface2, #1e2130)', border: '1px solid var(--border)',
    borderRadius: 8, padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8,
  },
  jobHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  jobName: { fontWeight: 600, fontSize: 14 },
  statusBadge: { fontSize: 11, borderRadius: 4, padding: '2px 8px', fontWeight: 600 },
  progressBar: { height: 6, borderRadius: 3, background: 'var(--border)', overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 3, background: 'var(--accent)', transition: 'width .3s' },
  logBox: {
    background: '#0d0f17', borderRadius: 6, padding: '8px 10px',
    fontSize: 11, color: '#8af', fontFamily: 'monospace', maxHeight: 120, overflowY: 'auto',
    whiteSpace: 'pre-wrap', wordBreak: 'break-all',
  },
  formGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 },
  divider: { border: 'none', borderTop: '1px solid var(--border)', margin: '4px 0' },
}

const STATUS_COLOR = {
  pending: { background: '#2d3a1e', color: '#9ef77e' },
  running: { background: '#1e2d3a', color: '#7eb8f7' },
  done:    { background: '#1e3a2d', color: '#7ef7c0' },
  failed:  { background: '#3a1e1e', color: '#f77' },
  stopped: { background: '#2d2d1e', color: '#f7d07e' },
}

export default function TrainingTab() {
  const [images, setImages]       = useState([])
  const [jobs, setJobs]           = useState([])
  const [checkpoints, setCheckpoints] = useState([])
  const [artStyles, setArtStyles] = useState([])
  const [activeJobId, setActiveJobId] = useState(null)
  const [log, setLog]             = useState({})
  const [captioning, setCaptioning] = useState(false)
  const [envStatus, setEnvStatus] = useState(null)
  const esRef = useRef(null)

  // form state
  const [form, setForm] = useState({
    name: '', base_checkpoint: '', trigger_word: '',
    lora_rank: 32, learning_rate: 0.0001, epochs: 10, resolution: 1024, art_style_id: '',
  })

  const loadImages = useCallback(() =>
    fetch(`${API}/images`).then(r => r.json()).then(setImages).catch(() => {}), [])

  const loadJobs = useCallback(() =>
    fetch(`${API}/jobs`).then(r => r.json()).then(setJobs).catch(() => {}), [])

  useEffect(() => {
    fetch(`${API}/status`).then(r => r.json()).then(setEnvStatus).catch(() => {})
    loadImages()
    loadJobs()
    fetch('/api/v1/settings/checkpoints').then(r => r.json())
      .then(d => { setCheckpoints(d.checkpoints ?? []); setForm(f => ({ ...f, base_checkpoint: d.active ?? '' })) })
      .catch(() => {})
    fetch('/api/v1/art-styles').then(r => r.json()).then(setArtStyles).catch(() => {})
  }, [])

  // Poll jobs every 5s when there's a running job
  useEffect(() => {
    const hasRunning = jobs.some(j => j.status === 'running')
    if (!hasRunning) return
    const t = setInterval(loadJobs, 5000)
    return () => clearInterval(t)
  }, [jobs, loadJobs])

  // SSE subscription for a running job
  const subscribeSSE = useCallback((jobId) => {
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    if (!jobId) return
    const es = new EventSource(`${API}/jobs/${jobId}/progress`)
    es.onmessage = e => {
      const data = JSON.parse(e.data)
      if (data.heartbeat) return
      if (data.message) {
        setLog(prev => ({ ...prev, [jobId]: ((prev[jobId] || '') + data.message + '\n').slice(-3000) }))
      }
      setJobs(prev => prev.map(j => j.id === jobId
        ? { ...j, current_step: data.step || j.current_step, total_steps: data.total_steps || j.total_steps, last_loss: data.loss ?? j.last_loss }
        : j
      ))
    }
    es.onerror = () => { es.close(); esRef.current = null }
    esRef.current = es
  }, [])

  useEffect(() => {
    const running = jobs.find(j => j.status === 'running')
    if (running && running.id !== activeJobId) {
      setActiveJobId(running.id)
      subscribeSSE(running.id)
    }
  }, [jobs, activeJobId, subscribeSSE])

  // Upload images
  const onUpload = async (e) => {
    const files = Array.from(e.target.files)
    for (const file of files) {
      const fd = new FormData(); fd.append('file', file)
      await fetch(`${API}/images/upload`, { method: 'POST', body: fd }).catch(() => {})
    }
    loadImages()
    e.target.value = ''
  }

  const updateCaption = async (id, caption) => {
    await fetch(`${API}/images/${id}/caption`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caption }),
    }).catch(() => {})
  }

  const deleteImage = async (id) => {
    await fetch(`${API}/images/${id}`, { method: 'DELETE' }).catch(() => {})
    setImages(prev => prev.filter(i => i.id !== id))
  }

  const captionAll = async () => {
    const running = jobs.find(j => j.status === 'running')
    const jobId = running?.id || jobs[0]?.id
    if (!jobId) { alert('請先建立一個訓練任務再執行批次 caption'); return }
    setCaptioning(true)
    await fetch(`${API}/jobs/${jobId}/caption-all`, { method: 'POST' }).catch(() => {})
    await loadImages()
    setCaptioning(false)
  }

  // Create job
  const createJob = async () => {
    const body = { ...form, art_style_id: form.art_style_id ? Number(form.art_style_id) : null }
    const res = await fetch(`${API}/jobs`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) { alert(await res.text()); return }
    loadJobs()
  }

  const startJob = async (id) => {
    const res = await fetch(`${API}/jobs/${id}/start`, { method: 'POST' })
    if (!res.ok) { alert(await res.text()); return }
    loadJobs()
    subscribeSSE(id)
  }

  const stopJob = async (id) => {
    await fetch(`${API}/jobs/${id}/stop`, { method: 'POST' }).catch(() => {})
    loadJobs()
  }

  const setF = (k, v) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div style={S.root}>

      {/* ── 環境狀態 ── */}
      {envStatus && (
        <div style={{
          padding: '10px 16px', borderRadius: 8, fontSize: 13,
          background: envStatus.ready ? '#1e3a2d' : '#3a1e1e',
          color: envStatus.ready ? '#7ef7c0' : '#f77',
          border: `1px solid ${envStatus.ready ? '#2d5a40' : '#5a2d2d'}`,
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <span style={{ fontSize: 16 }}>{envStatus.ready ? '✓' : '✗'}</span>
          <span>
            {envStatus.ready
              ? `kohya_ss 就緒（${envStatus.kohya_path}）`
              : `kohya_ss 未找到（${envStatus.kohya_path}）— 安裝完成後重整頁面`
            }
            {!envStatus.comfyui_loras_dir_exists &&
              `　·　ComfyUI loras 目錄不存在（${envStatus.comfyui_loras_dir}）`
            }
          </span>
        </div>
      )}

      {/* ── 訓練圖片 ── */}
      <div style={S.section}>
        <div style={S.row}>
          <span style={S.sectionTitle}>訓練圖片 ({images.length} 張)</span>
          <label style={{ ...S.btn, cursor: 'pointer' }}>
            + 新增圖片
            <input type="file" multiple accept="image/*" style={{ display: 'none' }} onChange={onUpload} />
          </label>
          <button style={S.btn} onClick={captionAll} disabled={captioning}>
            {captioning ? 'AI 生成中…' : 'AI 批次生成 caption'}
          </button>
        </div>

        {images.length === 0
          ? <div style={{ color: 'var(--muted)', fontSize: 13 }}>尚未上傳圖片，點「+ 新增圖片」上傳 PNG / JPG</div>
          : (
            <div style={S.grid}>
              {images.map(img => (
                <ImageCard key={img.id} img={img} onDelete={deleteImage} onCaptionBlur={updateCaption} />
              ))}
            </div>
          )
        }
      </div>

      <hr style={S.divider} />

      {/* ── 新增訓練任務 ── */}
      <div style={S.section}>
        <span style={S.sectionTitle}>新增訓練任務</span>
        <div style={S.formGrid}>
          <label style={S.label}>任務名稱
            <input style={S.input} value={form.name} onChange={e => setF('name', e.target.value)} placeholder="my_artstyle_v1" />
          </label>
          <label style={S.label}>基底 Checkpoint
            {checkpoints.length > 0
              ? <select style={S.input} value={form.base_checkpoint} onChange={e => setF('base_checkpoint', e.target.value)}>
                  <option value="">選擇…</option>
                  {checkpoints.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              : <input style={S.input} value={form.base_checkpoint} onChange={e => setF('base_checkpoint', e.target.value)} placeholder="model.safetensors" />
            }
          </label>
          <label style={S.label}>Trigger Word
            <input style={S.input} value={form.trigger_word} onChange={e => setF('trigger_word', e.target.value)} placeholder="myartstyle" />
          </label>
          <label style={S.label}>LoRA Rank
            <input style={S.input} type="number" min={1} max={128} value={form.lora_rank} onChange={e => setF('lora_rank', Number(e.target.value))} />
          </label>
          <label style={S.label}>學習率
            <input style={S.input} type="number" step="0.00001" value={form.learning_rate} onChange={e => setF('learning_rate', Number(e.target.value))} />
          </label>
          <label style={S.label}>Epochs
            <input style={S.input} type="number" min={1} max={200} value={form.epochs} onChange={e => setF('epochs', Number(e.target.value))} />
          </label>
          <label style={S.label}>解析度
            <input style={S.input} type="number" step={64} min={512} max={2048} value={form.resolution} onChange={e => setF('resolution', Number(e.target.value))} />
          </label>
          <label style={S.label}>綁定畫風（完成後自動掛載）
            <select style={S.input} value={form.art_style_id} onChange={e => setF('art_style_id', e.target.value)}>
              <option value="">不綁定</option>
              {artStyles.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
        </div>
        <div>
          <button style={{ ...S.btn, ...S.btnPrimary }} onClick={createJob}
            disabled={!form.name || !form.base_checkpoint || !form.trigger_word}>
            建立任務
          </button>
        </div>
      </div>

      <hr style={S.divider} />

      {/* ── 任務列表 ── */}
      <div style={S.section}>
        <span style={S.sectionTitle}>訓練任務 ({jobs.length})</span>
        {jobs.length === 0
          ? <div style={{ color: 'var(--muted)', fontSize: 13 }}>尚無任務</div>
          : jobs.map(job => (
            <JobCard
              key={job.id}
              job={job}
              log={log[job.id] || job.log_tail || ''}
              onStart={() => startJob(job.id)}
              onStop={() => stopJob(job.id)}
            />
          ))
        }
      </div>

    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function ImageCard({ img, onDelete, onCaptionBlur }) {
  const [caption, setCaption] = useState(img.caption || '')
  return (
    <div style={S.imgCard}>
      <img src={`/api/v1/training/images/${img.id}/file`} style={S.imgThumb} alt={img.filename}
        onError={e => { e.target.style.display = 'none' }} />
      <textarea
        style={S.imgCaption}
        value={caption}
        onChange={e => setCaption(e.target.value)}
        onBlur={() => onCaptionBlur(img.id, caption)}
        placeholder="caption（失焦自動儲存）"
        rows={3}
      />
      <div style={S.imgFooter}>
        <span style={{ fontSize: 10, color: 'var(--muted)' }}>{img.width}×{img.height}</span>
        <button style={S.delBtn} onClick={() => onDelete(img.id)}>刪除</button>
      </div>
    </div>
  )
}

function JobCard({ job, log, onStart, onStop }) {
  const [showLog, setShowLog] = useState(false)
  const pct = job.total_steps > 0 ? Math.round(job.current_step / job.total_steps * 100) : 0
  const badgeStyle = { ...S.statusBadge, ...(STATUS_COLOR[job.status] || {}) }
  return (
    <div style={S.jobCard}>
      <div style={S.jobHeader}>
        <span style={S.jobName}>{job.name}</span>
        <span style={badgeStyle}>{job.status}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)' }}>
        {job.trigger_word} · rank {job.lora_rank} · {job.epochs} epochs · {job.base_checkpoint}
      </div>
      {job.status === 'running' && (
        <>
          <div style={S.progressBar}>
            <div style={{ ...S.progressFill, width: `${pct}%` }} />
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>
            step {job.current_step}/{job.total_steps} ({pct}%)
            {job.last_loss != null && ` · loss ${job.last_loss.toFixed(4)}`}
          </div>
        </>
      )}
      {job.status === 'done' && job.output_lora_name && (
        <div style={{ fontSize: 12, color: '#7ef7c0' }}>輸出：{job.output_lora_name}</div>
      )}
      <div style={S.row}>
        {job.status === 'pending' && (
          <button style={{ ...S.btn, ...S.btnPrimary }} onClick={onStart}>開始訓練</button>
        )}
        {job.status === 'running' && (
          <button style={{ ...S.btn, ...S.btnDanger }} onClick={onStop}>停止</button>
        )}
        {log && (
          <button style={S.btn} onClick={() => setShowLog(v => !v)}>
            {showLog ? '隱藏 Log' : '查看 Log'}
          </button>
        )}
      </div>
      {showLog && log && <div style={S.logBox}>{log}</div>}
    </div>
  )
}
