import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { dateTime, num, pct } from '../lib/format'
import { Badge, Confidence, ErrorBox, Spinner } from '../components/ui'

function Field({ label, children }) {
  if (children === null || children === undefined || children === '' || (Array.isArray(children) && !children.length)) return null
  return <div className="field"><div className="field-label">{label}</div><div className="field-value">{children}</div></div>
}

const List = ({ items }) => (items?.length ? <ul>{items.map((x, i) => <li key={i}>{typeof x === 'string' ? x : JSON.stringify(x)}</li>)}</ul> : null)

export default function VideoDetail() {
  const { id } = useParams()
  const [d, setD] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api(`/api/videos/${id}`).then(setD).catch(setError) }, [id])
  if (!d) return error ? <ErrorBox error={error} /> : <Spinner />

  const v = d.video, va = d.analysis, a = va?.analysis || {}
  const er = v.views ? ((v.likes || 0) + (v.comments || 0) + (v.shares || 0)) / v.views : null
  const mm = v.media_meta || {}

  return (
    <div>
      <header className="page-head">
        <div>
          <h1>{v.ref} · {a.main_topic || 'Video'}</h1>
          <p className="muted"><Link to={`/analyses/${v.analysis_id}`}>← Về phân tích</Link>{v.url && <> · <a href={v.url} target="_blank" rel="noreferrer">Mở trên TikTok ↗</a></>}</p>
        </div>
        <div className="actions"><Badge status={v.status} />{va && <Confidence value={va.confidence} />}</div>
      </header>
      {v.error && <div className="alert alert-error">{v.error}</div>}

      <div className="stats">
        {[['Views', num(v.views)], ['Likes', num(v.likes)], ['Comments', num(v.comments)], ['Shares', num(v.shares)],
          ['Engagement', pct(er)], ['Đăng lúc', dateTime(v.posted_at)]].map(([k, val]) => (
          <div className="stat" key={k}><div className="stat-label">{k}</div><div className="stat-value small">{val}</div></div>
        ))}
      </div>
      <p className="tiny muted">Nguồn metrics: {v.metrics_source === 'collector' ? 'thu thập tự động' : v.metrics_source === 'user_import' ? 'người dùng import' : 'không có'}
        {mm.analyzed_seconds && ` · phân tích ${mm.analyzed_seconds}s${mm.truncated ? ` / ${mm.original_duration}s (đã cắt theo giới hạn)` : ''}`}
        {mm.cuts_per_minute != null && ` · ${mm.scene_cuts} lần cắt cảnh (${mm.cuts_per_minute}/phút, đo bằng FFmpeg)`}
        {va && ` · chế độ: ${va.input_mode}${va.from_cache ? ' (cache)' : ''} · ${va.model}`}</p>

      {v.keyframes?.length > 0 && (
        <div className="keyframes">
          {v.keyframes.map((k) => <figure key={k.path}>{k.url ? <img src={k.url} alt="" /> : <div className="thumb-empty" />}<figcaption>{k.time}s</figcaption></figure>)}
        </div>
      )}

      {!va ? <div className="card muted">Video chưa có kết quả phân tích nội dung.</div> : (
        <div className="grid-2">
          <div className="card">
            <h3>Nội dung</h3>
            <Field label="Chủ đề chính">{a.main_topic}</Field>
            <Field label="Chủ đề phụ">{a.subtopics?.join(' · ')}</Field>
            <Field label="Format">{a.content_format}</Field>
            <Field label="Khán giả mục tiêu">{a.target_audience}</Field>
            <Field label={`Hook (${a.hook?.type || '?'})`}>{a.hook?.text}{a.hook?.first_seconds_description && <div className="muted">{a.hook.first_seconds_description}</div>}</Field>
            <Field label="Storytelling">{a.storytelling}</Field>
            <Field label="Cấu trúc kể">{a.narrative_structure}</Field>
            <Field label="Giữ chân người xem"><List items={a.retention_mechanisms} /></Field>
            <Field label="CTA">{a.cta?.present ? `${a.cta.type || ''} — ${a.cta.text || ''}` : 'Không có'}</Field>
            <Field label="Kết thúc">{a.ending}</Field>
            <Field label="Content formula"><code>{a.content_formula}</code></Field>
          </div>
          <div className="card">
            <h3>Hình ảnh & âm thanh</h3>
            <Field label="Visual style">{a.visual_style}</Field>
            <Field label="Nhịp dựng">{a.editing_rhythm}</Field>
            <Field label="Âm thanh">{[a.audio?.voice, a.audio?.music, a.audio?.sound_effects].filter(Boolean).join(' · ')}</Field>
            <Field label="Cấu trúc cảnh">
              {a.scene_structure?.length > 0 && <ol className="scenes">{a.scene_structure.map((s, i) => <li key={i}><span>{s.start_sec}–{s.end_sec}s</span> {s.description}</li>)}</ol>}
            </Field>
            <Field label="Điểm mạnh"><List items={a.strengths} /></Field>
            <Field label="Điểm yếu"><List items={a.weaknesses} /></Field>
            <Field label="Bằng chứng">
              {a.evidence?.length > 0 && <ul>{a.evidence.map((e, i) => <li key={i}>{e.claim} <span className="tiny muted">[{e.source}{e.timestamp_sec != null ? ` @${e.timestamp_sec}s` : ''}]</span></li>)}</ul>}
            </Field>
            <Field label="Giới hạn dữ liệu"><List items={a.data_limitations} /></Field>
          </div>
          <div className="card span-2">
            <h3>Transcript</h3><p className="pre">{va.transcript || <span className="muted">Không có lời thoại.</span>}</p>
            <h3>Chữ trên màn hình (OCR)</h3><p className="pre">{va.ocr_text || <span className="muted">Không có.</span>}</p>
            {v.caption && <><h3>Caption</h3><p className="pre">{v.caption}</p></>}
          </div>
        </div>
      )}
    </div>
  )
}
