import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { ACTIVE, SOURCE_LABEL, dateTime } from '../lib/format'
import { Badge, Empty, ErrorBox, Progress, Spinner } from '../components/ui'

function Usage({ me }) {
  if (!me) return null
  const u = me.usage_today, l = me.limits
  const items = [
    ['Phân tích hôm nay', u.analyses, l.max_analyses_per_day],
    ['Video hôm nay', u.videos, l.max_videos_per_day],
    ['AI request hôm nay', u.ai_requests, l.max_ai_requests_per_day],
    ['Đang chạy', me.active_analyses, l.max_active_analyses],
  ]
  return (
    <div className="stats">
      {items.map(([label, v, max]) => (
        <div className="stat" key={label}>
          <div className="stat-label">{label}</div>
          <div className="stat-value">{v}<small> / {max}</small></div>
          <Progress value={max ? v / max : 0} />
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const [me, setMe] = useState(null)
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let timer
    const load = () => Promise.all([api('/api/me'), api('/api/analyses')])
      .then(([m, r]) => {
        setMe(m); setRows(r); setError(null)
        if (r.some((a) => ACTIVE.includes(a.status))) timer = setTimeout(load, 8000)
      })
      .catch(setError)
    load()
    return () => clearTimeout(timer)
  }, [])

  return (
    <div>
      <header className="page-head">
        <div><h1>Dashboard</h1><p className="muted">Các kênh đã phân tích, trạng thái và mức sử dụng.</p></div>
        <Link to="/new" className="btn primary">+ Phân tích mới</Link>
      </header>
      <ErrorBox error={error} />
      <Usage me={me} />
      {!rows ? <Spinner /> : rows.length === 0 ? (
        <Empty title="Chưa có phân tích nào">
          <p>Bắt đầu bằng cách nhập một profile TikTok, dán URL video, upload video hoặc import dữ liệu.</p>
          <Link to="/new" className="btn primary">Phân tích kênh đầu tiên</Link>
        </Empty>
      ) : (
        <div className="card table-card">
          <table>
            <thead><tr><th>Kênh / tên</th><th>Nguồn</th><th>Trạng thái</th><th>Video</th><th>Tạo lúc</th><th /></tr></thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/analyses/${a.id}`}><b>{a.title}</b></Link>{ACTIVE.includes(a.status) && <div className="tiny muted">{a.stage}</div>}</td>
                  <td>{SOURCE_LABEL[a.source]}</td>
                  <td><Badge status={a.status} />{ACTIVE.includes(a.status) && <Progress value={a.progress} />}</td>
                  <td>{a.videos_done}/{a.video_count}{a.videos_failed > 0 && <span className="tiny err"> · {a.videos_failed} lỗi</span>}</td>
                  <td className="tiny">{dateTime(a.created_at)}</td>
                  <td>{a.has_report ? <Link className="btn small" to={`/analyses/${a.id}/report`}>Báo cáo</Link>
                    : <Link className="btn small ghost" to={`/analyses/${a.id}`}>Chi tiết</Link>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
