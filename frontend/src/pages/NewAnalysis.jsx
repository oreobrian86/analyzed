import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, uploadFile } from '../lib/api'
import { bytes } from '../lib/format'
import { ErrorBox, Progress } from '../components/ui'

const TABS = [
  ['profile', 'Profile TikTok'],
  ['urls', 'Danh sách URL video'],
  ['upload', 'Upload video'],
  ['import', 'Import CSV / JSON'],
]

const IMPORT_SAMPLE = `url,views,likes,comments,shares,date,caption
https://www.tiktok.com/@kenh/video/7400000000000000001,15200,830,41,12,2026-10-02,3 mẹo ...
https://www.tiktok.com/@kenh/video/7400000000000000002,9800,410,22,5,2026-10-05,Sai lầm khi ...`

export default function NewAnalysis() {
  const nav = useNavigate()
  const [me, setMe] = useState(null)
  const [tab, setTab] = useState('profile')
  const [profile, setProfile] = useState('')
  const [urls, setUrls] = useState('')
  const [importText, setImportText] = useState('')
  const [files, setFiles] = useState([])
  const [maxVideos, setMaxVideos] = useState(10)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [uploadState, setUploadState] = useState(null)

  useEffect(() => { api('/api/me').then(setMe).catch(setError) }, [])
  const maxAllowed = me?.limits?.max_videos_per_analysis || 20
  const maxUpload = me?.limits?.max_upload_mb || 50

  async function readFile(e) {
    const f = e.target.files?.[0]
    if (f) setImportText(await f.text())
  }

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const body = { source: tab, max_videos: Math.min(maxVideos, maxAllowed), title: title || undefined }
      if (tab === 'profile') Object.assign(body, { profile_url: profile, date_from: dateFrom || undefined, date_to: dateTo || undefined })
      if (tab === 'urls') body.urls = urls
      if (tab === 'import') body.import_text = importText
      if (tab === 'upload') {
        const list = files.slice(0, maxAllowed)
        if (!list.length) throw new Error('Chọn ít nhất 1 video.')
        const big = list.find((f) => f.size > maxUpload * 1024 * 1024)
        if (big) throw new Error(`${big.name} vượt ${maxUpload} MB.`)
        body.max_videos = list.length
        const a = await api('/api/analyses', { method: 'POST', body })
        for (let i = 0; i < list.length; i++) {
          setUploadState({ i, n: list.length, name: list[i].name, p: 0 })
          await uploadFile(`/api/analyses/${a.id}/uploads`, list[i], (p) => setUploadState({ i, n: list.length, name: list[i].name, p }))
        }
        await api(`/api/analyses/${a.id}/start`, { method: 'POST' })
        return nav(`/analyses/${a.id}`)
      }
      const a = await api('/api/analyses', { method: 'POST', body })
      nav(`/analyses/${a.id}`)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <header className="page-head"><div><h1>Phân tích mới</h1>
        <p className="muted">Chọn cách đưa video vào. Nếu thu thập profile tự động bị TikTok chặn, dùng URL, upload hoặc import.</p></div></header>
      <form className="card form" onSubmit={submit}>
        <div className="tabs">
          {TABS.map(([k, label]) => (
            <button type="button" key={k} className={tab === k ? 'tab active' : 'tab'} onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>

        {tab === 'profile' && (
          <>
            <label>Profile TikTok
              <input placeholder="https://www.tiktok.com/@tenkenh hoặc @tenkenh" value={profile} onChange={(e) => setProfile(e.target.value)} required />
            </label>
            <div className="row">
              <label>Từ ngày (tuỳ chọn)<input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
              <label>Đến ngày (tuỳ chọn)<input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
            </div>
            <p className="hint">Lọc ngày áp dụng sau khi đọc metadata từng video; video ngoài khoảng sẽ bị bỏ qua (không tốn AI quota). Thu thập tự động phụ thuộc TikTok và có thể thất bại.</p>
          </>
        )}

        {tab === 'urls' && (
          <label>URL video (mỗi dòng một link)
            <textarea rows={8} value={urls} onChange={(e) => setUrls(e.target.value)} required
              placeholder="https://www.tiktok.com/@kenh/video/74...&#10;https://vm.tiktok.com/..." />
          </label>
        )}

        {tab === 'upload' && (
          <>
            <label>File video (mp4/mov/webm, ≤ {maxUpload} MB mỗi file)
              <input type="file" accept="video/*" multiple onChange={(e) => setFiles([...e.target.files])} />
            </label>
            {files.length > 0 && <ul className="filelist">{files.slice(0, maxAllowed).map((f) => <li key={f.name}>{f.name} · {bytes(f.size)}</li>)}</ul>}
            <p className="hint">Video upload không có views/likes nên báo cáo sẽ không có phần hiệu suất. File gốc bị xoá khỏi cloud ngay sau khi phân tích xong.</p>
            {uploadState && (
              <div className="upload-state">Đang upload {uploadState.i + 1}/{uploadState.n}: {uploadState.name}<Progress value={uploadState.p} /></div>
            )}
          </>
        )}

        {tab === 'import' && (
          <>
            <label>Dán CSV/JSON hoặc chọn file
              <textarea rows={8} value={importText} onChange={(e) => setImportText(e.target.value)} placeholder={IMPORT_SAMPLE} required />
            </label>
            <input type="file" accept=".csv,.json,.txt" onChange={readFile} />
            <p className="hint">Cột nhận diện: url, views, likes, comments, shares, saves, date, caption. Metrics import được giữ nguyên; video vẫn được tải qua URL để phân tích nội dung thực tế — nếu không tải được, video chỉ dùng cho phần hiệu suất.</p>
          </>
        )}

        <div className="row">
          {tab !== 'upload' && (
            <label>Số video tối đa: <b>{Math.min(maxVideos, maxAllowed)}</b>
              <input type="range" min={1} max={maxAllowed} value={Math.min(maxVideos, maxAllowed)} onChange={(e) => setMaxVideos(Number(e.target.value))} />
            </label>
          )}
          <label>Tên phân tích (tuỳ chọn)<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} /></label>
        </div>
        {me && (
          <p className="hint">Hôm nay bạn còn {Math.max(0, me.limits.max_videos_per_day - me.usage_today.videos)} video và{' '}
            {Math.max(0, me.limits.max_analyses_per_day - me.usage_today.analyses)} lượt phân tích. Ước tính ~1 AI request / video + 4–10 request cho bước tổng hợp kênh.</p>
        )}
        <ErrorBox error={error} />
        <button className="btn primary" disabled={busy}>{busy ? 'Đang gửi…' : 'Bắt đầu phân tích'}</button>
      </form>
    </div>
  )
}
