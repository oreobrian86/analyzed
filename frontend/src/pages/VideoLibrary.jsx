import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { date, num } from '../lib/format'
import { Badge, Confidence, Empty, ErrorBox, Spinner } from '../components/ui'

export default function VideoLibrary() {
  const [params, setParams] = useSearchParams()
  const [rows, setRows] = useState(null)
  const [q, setQ] = useState(params.get('q') || '')
  const [error, setError] = useState(null)
  const analysisId = params.get('analysis_id')

  useEffect(() => {
    const qs = new URLSearchParams()
    if (analysisId) qs.set('analysis_id', analysisId)
    if (params.get('q')) qs.set('q', params.get('q'))
    setRows(null)
    api(`/api/videos?${qs}`).then(setRows).catch(setError)
  }, [params])

  function search(e) {
    e.preventDefault()
    const p = new URLSearchParams(params)
    q ? p.set('q', q) : p.delete('q')
    setParams(p)
  }

  return (
    <div>
      <header className="page-head">
        <div><h1>Video Library</h1><p className="muted">Toàn bộ video đã đưa vào phân tích{analysisId && ' (đang lọc theo 1 phân tích)'}.</p></div>
        <form onSubmit={search} className="search"><input placeholder="Tìm caption / chủ đề…" value={q} onChange={(e) => setQ(e.target.value)} /><button className="btn">Tìm</button></form>
      </header>
      <ErrorBox error={error} />
      {!rows ? <Spinner /> : rows.length === 0 ? <Empty title="Không có video nào" /> : (
        <div className="video-grid">
          {rows.map((v) => (
            <Link to={`/videos/${v.id}`} className="video-card" key={v.id}>
              <div className="thumb">
                {v.preview_url ? <img src={v.preview_url} alt="" loading="lazy" /> : <div className="thumb-empty">{v.ref}</div>}
                <span className="thumb-ref">{v.ref}</span>
              </div>
              <div className="video-body">
                <div className="video-topic">{v.main_topic || v.caption || 'Chưa phân tích'}</div>
                <div className="tiny muted clip2">{v.analysis_title}</div>
                <div className="video-meta">
                  <span>▶ {num(v.views)}</span><span>♥ {num(v.likes)}</span><span>{date(v.posted_at)}</span>
                </div>
                <div className="video-tags">
                  <Badge status={v.status} />
                  {v.content_format && <span className="chip">{v.content_format}</span>}
                  {v.hook_type && <span className="chip">hook: {v.hook_type}</span>}
                  <Confidence value={v.confidence} />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
