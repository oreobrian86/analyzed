import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { bytes } from '../lib/format'
import { ErrorBox, Spinner } from '../components/ui'

const LABELS = {
  max_videos_per_analysis: 'Video tối đa / phân tích',
  max_analyses_per_day: 'Phân tích / ngày',
  max_videos_per_day: 'Video / ngày',
  max_ai_requests_per_day: 'AI request / ngày',
  max_active_analyses: 'Phân tích chạy cùng lúc',
  max_upload_mb: 'Dung lượng 1 file upload (MB)',
  max_upload_bytes_per_day_mb: 'Tổng upload / ngày (MB)',
  max_storage_mb: 'Lưu trữ tạm tối đa (MB)',
}

export default function Settings() {
  const [cfg, setCfg] = useState(null)
  const [me, setMe] = useState(null)
  const [admin, setAdmin] = useState(null)
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    Promise.all([api('/api/config'), api('/api/me')]).then(([c, m]) => {
      setCfg(c); setMe(m)
      if (m.role === 'admin') api('/api/admin/overview').then(setAdmin).catch(() => {})
    }).catch(setError)
  }, [])

  async function wipe() {
    if (!window.confirm('Xoá TOÀN BỘ phân tích, video, báo cáo và file của bạn? Không thể hoàn tác.')) return
    try {
      const r = await api('/api/me/data', { method: 'DELETE' })
      setMsg(`Đã xoá ${r.deleted_analyses} phân tích.`)
    } catch (e) { setError(e) }
  }

  if (!cfg || !me) return error ? <ErrorBox error={error} /> : <Spinner />
  return (
    <div>
      <header className="page-head"><div><h1>Settings</h1><p className="muted">Giới hạn sử dụng, AI provider và dữ liệu. Giới hạn do admin cấu hình trên server.</p></div></header>
      <ErrorBox error={error} />
      {msg && <div className="alert alert-info">{msg}</div>}
      <div className="grid-2">
        <div className="card">
          <h3>Giới hạn của bạn</h3>
          <table><tbody>
            {Object.entries(me.limits).map(([k, v]) => <tr key={k}><td>{LABELS[k] || k}</td><td><b>{v}</b></td></tr>)}
            <tr><td>Đang dùng lưu trữ tạm</td><td><b>{bytes(me.storage_used_bytes)}</b></td></tr>
          </tbody></table>
          <p className="tiny muted">Quota tính theo ngày UTC (reset lúc 7:00 sáng giờ Việt Nam). Ngoài quota cá nhân còn có giới hạn tổng cho cả hệ thống để không vượt free tier.</p>
        </div>
        <div className="card">
          <h3>AI & xử lý</h3>
          <table><tbody>
            {Object.entries(cfg.ai).map(([k, v]) => <tr key={k}><td>{k}</td><td><code>{String(v)}</code></td></tr>)}
            <tr><td>Collector</td><td>{cfg.collectors.join(', ')}</td></tr>
            <tr><td>Thời lượng phân tích tối đa / video</td><td>{cfg.max_video_seconds}s</td></tr>
            <tr><td>Ngôn ngữ báo cáo</td><td>{cfg.report_language}</td></tr>
          </tbody></table>
          <p className="tiny muted">Video chỉ được gửi tới AI provider ở trên. Lưu ý: ở free tier của Gemini, Google có thể dùng nội dung gửi lên để cải thiện sản phẩm — không phân tích video riêng tư/nhạy cảm.</p>
        </div>
        <div className="card">
          <h3>Dữ liệu & lưu trữ</h3>
          <ul>
            <li>Video gốc: <b>không lưu lâu dài</b> — file tạm trên server bị xoá sau mỗi job; file upload bị xoá ngay khi phân tích xong.</li>
            <li>Keyframe (ảnh nhỏ): giữ {cfg.keyframe_retention_days} ngày.</li>
            <li>Phân tích, báo cáo: tự xoá sau {cfg.retention_days} ngày kể từ khi hoàn tất.</li>
          </ul>
          <button className="btn danger" onClick={wipe}>Xoá toàn bộ dữ liệu của tôi</button>
        </div>
        {admin && (
          <div className="card">
            <h3>Admin · hôm nay</h3>
            <table><tbody>
              <tr><td>AI request toàn hệ thống</td><td><b>{admin.global_usage_today.ai_requests}</b> / {admin.global_limits.ai_requests}</td></tr>
              <tr><td>Video toàn hệ thống</td><td><b>{admin.global_usage_today.videos}</b> / {admin.global_limits.videos}</td></tr>
              <tr><td>Token in / out</td><td>{admin.global_usage_today.ai_input_tokens} / {admin.global_usage_today.ai_output_tokens}</td></tr>
            </tbody></table>
            <h4>Hàng đợi</h4>
            <ul className="tiny">{admin.queue.map((q, i) => <li key={i}>{q.type} · {q.status}: {q.n}</li>)}</ul>
            <h4>User</h4>
            <table className="tiny"><tbody>{admin.users.map((u) => <tr key={u.email}><td>{u.email}</td><td>{u.role}</td><td>{u.analyses ?? 0} pt · {u.videos ?? 0} video · {u.ai_requests ?? 0} AI</td></tr>)}</tbody></table>
          </div>
        )}
      </div>
    </div>
  )
}
