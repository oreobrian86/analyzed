import { useEffect, useState } from 'react'
import { api, supabase } from '../lib/api'
import { ErrorBox, Progress, Spinner } from '../components/ui'

export default function Profile() {
  const [me, setMe] = useState(null)
  const [error, setError] = useState(null)
  const [pw, setPw] = useState('')
  const [msg, setMsg] = useState(null)
  useEffect(() => { api('/api/me').then(setMe).catch(setError) }, [])

  async function changePw(e) {
    e.preventDefault()
    const { error } = await supabase.auth.updateUser({ password: pw })
    setMsg(error ? error.message : 'Đã đổi mật khẩu.')
    setPw('')
  }

  if (!me) return error ? <ErrorBox error={error} /> : <Spinner />
  const u = me.usage_today, l = me.limits
  return (
    <div>
      <header className="page-head"><div><h1>Tài khoản</h1><p className="muted">{me.email} · vai trò: {me.role}</p></div>
        <button className="btn" onClick={() => supabase.auth.signOut()}>Đăng xuất</button></header>
      <div className="grid-2">
        <div className="card">
          <h3>Sử dụng hôm nay</h3>
          {[['Phân tích', u.analyses, l.max_analyses_per_day], ['Video', u.videos, l.max_videos_per_day], ['AI request', u.ai_requests, l.max_ai_requests_per_day]].map(([k, v, m]) => (
            <div key={k} className="usage-row"><span>{k}</span><span>{v} / {m}</span><Progress value={m ? v / m : 0} /></div>
          ))}
          <p className="tiny muted">Token AI hôm nay: {u.ai_input_tokens.toLocaleString('vi-VN')} vào · {u.ai_output_tokens.toLocaleString('vi-VN')} ra.</p>
        </div>
        <form className="card form" onSubmit={changePw}>
          <h3>Đổi mật khẩu</h3>
          <label>Mật khẩu mới<input type="password" minLength={8} required value={pw} onChange={(e) => setPw(e.target.value)} /></label>
          {msg && <div className="alert alert-info">{msg}</div>}
          <button className="btn">Cập nhật</button>
        </form>
      </div>
    </div>
  )
}
