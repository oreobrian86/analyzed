import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { CONFIG_OK, pingServer, supabase } from './lib/api'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import NewAnalysis from './pages/NewAnalysis'
import Processing from './pages/Processing'
import VideoLibrary from './pages/VideoLibrary'
import VideoDetail from './pages/VideoDetail'
import ChannelReport from './pages/ChannelReport'
import Settings from './pages/Settings'
import Profile from './pages/Profile'
import { Spinner } from './components/ui'

function WakeBanner() {
  const [state, setState] = useState('checking')
  useEffect(() => {
    let done = false
    const slow = setTimeout(() => !done && setState('waking'), 2500)
    pingServer().then((r) => {
      done = true
      clearTimeout(slow)
      setState(r.ok ? 'ok' : 'down')
      if (r.data && r.data.ok === false) setState('misconfigured')
    })
    return () => clearTimeout(slow)
  }, [])
  if (state === 'waking') return <div className="banner">Server miễn phí đang khởi động lại sau thời gian nghỉ (thường ≤ 1 phút)…</div>
  if (state === 'down') return <div className="banner banner-error">Chưa kết nối được server. Đợi 1 phút rồi tải lại trang.</div>
  if (state === 'misconfigured') return <div className="banner banner-error">Server thiếu biến môi trường — xem /api/health và docs/TROUBLESHOOTING.md.</div>
  return null
}

const NAV = [
  ['/', 'Dashboard'],
  ['/new', 'Phân tích mới'],
  ['/videos', 'Video Library'],
  ['/settings', 'Settings'],
  ['/profile', 'Tài khoản'],
]

export default function App() {
  const [session, setSession] = useState(undefined)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])

  if (!CONFIG_OK) {
    return (
      <div className="center-page">
        <div className="card narrow">
          <h2>Thiếu cấu hình frontend</h2>
          <p>Cần đặt VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_API_URL trong Cloudflare Pages → Settings → Environment variables, rồi deploy lại.</p>
        </div>
      </div>
    )
  }
  if (session === undefined) return <div className="center-page"><Spinner /></div>
  if (!session) return <Login />

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="logo" />Channel<b>Intel</b></div>
        <nav>
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>{label}</NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">{session.user.email}</div>
      </aside>
      <main className="main">
        <WakeBanner />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewAnalysis />} />
          <Route path="/analyses/:id" element={<Processing />} />
          <Route path="/analyses/:id/report" element={<ChannelReport />} />
          <Route path="/videos" element={<VideoLibrary />} />
          <Route path="/videos/:id" element={<VideoDetail />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
