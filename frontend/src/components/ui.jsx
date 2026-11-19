import { Link } from 'react-router-dom'
import { STATUS_LABEL, pct } from '../lib/format'

export function Badge({ status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABEL[status] || status}</span>
}

export function Progress({ value }) {
  const v = Math.max(0, Math.min(1, Number(value) || 0))
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(v * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div style={{ width: `${v * 100}%` }} />
    </div>
  )
}

export function Confidence({ value }) {
  if (value === null || value === undefined) return null
  const v = Number(value)
  const level = v >= 0.7 ? 'high' : v >= 0.45 ? 'mid' : 'low'
  return <span className={`conf conf-${level}`} title="Độ tin cậy do AI tự đánh giá, đã bị hạ nếu thiếu bằng chứng">tin cậy {pct(v, 0)}</span>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return <div className="alert alert-error">{String(error.message || error)}</div>
}

export function Empty({ title, children }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children}
    </div>
  )
}

export function Spinner({ label = 'Đang tải…' }) {
  return <div className="spinner"><span />{label}</div>
}

export function RefLinks({ refs, refMap }) {
  if (!refs?.length) return null
  return (
    <span className="refs">
      {refs.map((r) => (refMap?.[r]
        ? <Link key={r} to={`/videos/${refMap[r]}`} className="ref">{r}</Link>
        : <span key={r} className="ref">{r}</span>))}
    </span>
  )
}

export function Insight({ item, refMap }) {
  return (
    <div className="insight">
      <div className="insight-head">
        <strong>{item.conclusion}</strong>
        <Confidence value={item.confidence} />
      </div>
      <dl>
        {item.evidence?.length > 0 && (<><dt>Bằng chứng</dt><dd><ul>{item.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul></dd></>)}
        {item.video_refs?.length > 0 && (<><dt>Video</dt><dd><RefLinks refs={item.video_refs} refMap={refMap} /></dd></>)}
        {item.observed_data && (<><dt>Dữ liệu quan sát</dt><dd>{item.observed_data}</dd></>)}
        {item.pattern && (<><dt>Pattern</dt><dd>{item.pattern}</dd></>)}
        {item.hypothesis && (<><dt>Giả thuyết</dt><dd className="muted">{item.hypothesis}</dd></>)}
        {item.recommendation && (<><dt>Khuyến nghị</dt><dd>{item.recommendation}</dd></>)}
      </dl>
      {item.quality_flags?.map((f, i) => <div key={i} className="flag">⚠ {f}</div>)}
    </div>
  )
}

export function Bar({ value, max = 1, label }) {
  const w = max ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="bar">
      <div className="bar-fill" style={{ width: `${w}%` }} />
      {label && <span>{label}</span>}
    </div>
  )
}
