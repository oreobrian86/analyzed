import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { ACTIVE, SOURCE_LABEL, dateTime, num } from '../lib/format'
import { Badge, ErrorBox, Progress, Spinner } from '../components/ui'

export default function Processing() {
  const { id } = useParams()
  const nav = useNavigate()
  const [a, setA] = useState(null)
  const [logs, setLogs] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [kick, setKick] = useState(0)
  const lastLog = useRef(0)

  async function load() {
    const [data, newLogs] = await Promise.all([api(`/api/analyses/${id}`), api(`/api/analyses/${id}/logs?after_id=${lastLog.current}`)])
    setA(data)
    if (newLogs.length) {
      lastLog.current = newLogs[newLogs.length - 1].id
      setLogs((l) => [...l, ...newLogs].slice(-400))
    }
    return data
  }

  useEffect(() => {
    let timer, stopped = false
    const tick = () => load().then((d) => {
      setError(null)
      // polling cũng giữ server free không bị spin-down khi bạn đang xem
      if (!stopped && ACTIVE.includes(d.status)) timer = setTimeout(tick, 4000)
    }).catch((e) => { setError(e); if (!stopped) timer = setTimeout(tick, 10000) })
    tick()
    return () => { stopped = true; clearTimeout(timer) }
  }, [id, kick])

  async function act(path, method = 'POST', confirmText) {
    if (confirmText && !window.confirm(confirmText)) return
    setBusy(true)
    try {
      await api(path, { method })
      if (method === 'DELETE') return nav('/')
      setKick((k) => k + 1) // chạy lại polling
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  if (!a) return error ? <ErrorBox error={error} /> : <Spinner />
  const active = ACTIVE.includes(a.status)

  return (
    <div>
      <header className="page-head">
        <div>
          <h1>{a.title}</h1>
          <p className="muted">{SOURCE_LABEL[a.source]} · tạo {dateTime(a.created_at)} {a.expires_at && `· dữ liệu lưu đến ${dateTime(a.expires_at)}`}</p>
        </div>
        <div className="actions">
          {(a.status === 'done' || a.status === 'partial') && <Link className="btn primary" to={`/analyses/${id}/report`}>Xem báo cáo</Link>}
          {active && <button className="btn" disabled={busy} onClick={() => act(`/api/analyses/${id}/cancel`, 'POST', 'Huỷ phân tích này?')}>Huỷ</button>}
          {['failed', 'partial', 'cancelled'].includes(a.status) && <button className="btn" disabled={busy} onClick={() => act(`/api/analyses/${id}/retry`)}>Retry</button>}
          {!active && <button className="btn danger ghost" disabled={busy} onClick={() => act(`/api/analyses/${id}`, 'DELETE', 'Xoá vĩnh viễn phân tích và mọi dữ liệu liên quan?')}>Xoá</button>}
        </div>
      </header>
      <ErrorBox error={error} />

      <div className="card">
        <div className="proc-head">
          <Badge status={a.status} />
          <span className="stage">{a.stage}</span>
          <span className="muted tiny">{Math.round(a.progress * 100)}%</span>
        </div>
        <Progress value={a.progress} />
        <div className="proc-stats">
          <span>Tổng: <b>{a.video_count}</b></span><span>Xong: <b>{a.videos_done}</b></span>
          <span>Lỗi: <b className={a.videos_failed ? 'err' : ''}>{a.videos_failed}</b></span><span>Bỏ qua: <b>{a.videos_skipped}</b></span>
          {active && <span className="muted">Hàng đợi: {a.jobs?.queued} job chờ · {a.jobs?.running} đang chạy{a.queue_ahead > 0 && ` · ${a.queue_ahead} job của người khác xếp trước`}</span>}
        </div>
        {a.error && <div className="alert alert-error">{a.error}</div>}
        {a.status === 'failed' && a.source === 'profile' && a.video_count === 0 && (
          <div className="alert alert-info">Gợi ý: tạo <Link to="/new">phân tích mới</Link> bằng tab “Danh sách URL video”, “Upload video” hoặc “Import”.</div>
        )}
      </div>

      <div className="grid-2">
        <div className="card table-card">
          <h3>Trạng thái từng video</h3>
          <table>
            <thead><tr><th>#</th><th>Video</th><th>Views</th><th>Trạng thái</th><th /></tr></thead>
            <tbody>
              {a.videos.map((v) => (
                <tr key={v.id}>
                  <td><Link to={`/videos/${v.id}`}>{v.ref}</Link></td>
                  <td className="clip">{v.caption || v.url || '—'}
                    {(v.error || (v.status === 'processing' && v.stage)) && <div className={`tiny ${v.error ? 'err' : 'muted'}`}>{v.error || v.stage}</div>}
                    {!v.error && v.last_job_error && v.status !== 'done' && <div className="tiny muted">Lần thử {v.attempts}: {v.last_job_error.slice(0, 160)}</div>}
                  </td>
                  <td>{num(v.views)}</td>
                  <td><Badge status={v.status} /></td>
                  <td>{['failed', 'cancelled', 'skipped'].includes(v.status) && !active &&
                    <button className="btn small ghost" disabled={busy} onClick={() => act(`/api/videos/${v.id}/retry`)}>Retry</button>}</td>
                </tr>
              ))}
              {a.videos.length === 0 && <tr><td colSpan={5} className="muted">Chưa có video (đang thu thập hoặc chờ hàng đợi).</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>Logs</h3>
          <div className="logs">
            {logs.map((l) => (
              <div key={l.id} className={`log log-${l.level}`}><span>{new Date(l.created_at).toLocaleTimeString('vi-VN')}</span>{l.message}</div>
            ))}
            {logs.length === 0 && <div className="muted">Chưa có log.</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
