import { useState } from 'react'
import { supabase } from '../lib/api'

export default function Login() {
  const [mode, setMode] = useState('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    const fn = mode === 'signin' ? supabase.auth.signInWithPassword : supabase.auth.signUp
    const { data, error } = await fn.call(supabase.auth, { email, password })
    setBusy(false)
    if (error) return setMsg({ type: 'error', text: error.message })
    if (mode === 'signup' && !data.session) {
      setMsg({ type: 'info', text: 'Đã tạo tài khoản. Nếu admin bật xác nhận email, hãy mở email để xác nhận rồi đăng nhập.' })
    }
  }

  return (
    <div className="center-page">
      <form className="card narrow login" onSubmit={submit}>
        <div className="brand big"><span className="logo" />Channel<b>Intel</b></div>
        <p className="muted">Phân tích chiến lược nội dung kênh TikTok bằng AI — chạy hoàn toàn trên cloud.</p>
        <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
        <label>Mật khẩu<input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} /></label>
        {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}
        <button className="btn primary" disabled={busy}>{busy ? 'Đang xử lý…' : mode === 'signin' ? 'Đăng nhập' : 'Tạo tài khoản'}</button>
        <button type="button" className="btn link" onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}>
          {mode === 'signin' ? 'Chưa có tài khoản? Đăng ký' : 'Đã có tài khoản? Đăng nhập'}
        </button>
        <p className="tiny muted">App chỉ dành cho người được admin cho phép. Email lạ sẽ bị từ chối khi dùng.</p>
      </form>
    </div>
  )
}
