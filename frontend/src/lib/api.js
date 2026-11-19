import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL || 'https://missing.supabase.co',
  import.meta.env.VITE_SUPABASE_ANON_KEY || 'missing',
)

const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
export const CONFIG_OK = Boolean(import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_ANON_KEY && BASE)

async function authHeader() {
  const { data } = await supabase.auth.getSession()
  return data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {}
}

function errorMessage(data, status) {
  if (data && data.detail) return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
  if (status === 502 || status === 503) return 'Server đang khởi động hoặc quá tải. Đợi khoảng 1 phút rồi thử lại.'
  return `Lỗi ${status}`
}

export async function api(path, { method = 'GET', body, signal } = {}) {
  const headers = await authHeader()
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let res
  try {
    res = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new Error('Không kết nối được server. Server miễn phí có thể đang "ngủ" — đợi ~1 phút rồi tải lại trang.')
  }
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (res.status === 401) {
    await supabase.auth.signOut()
  }
  if (!res.ok) throw new Error(errorMessage(data, res.status))
  return data
}

export function uploadFile(path, file, onProgress) {
  return new Promise(async (resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', BASE + path)
    const h = await authHeader()
    Object.entries(h).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
    xhr.onload = () => {
      let data = null
      try { data = JSON.parse(xhr.responseText) } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data)
      else reject(new Error(errorMessage(data, xhr.status)))
    }
    xhr.onerror = () => reject(new Error('Upload thất bại (mất kết nối).'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

export async function pingServer() {
  const t0 = Date.now()
  try {
    const r = await fetch(BASE + '/api/health')
    return { ok: r.ok, ms: Date.now() - t0, data: await r.json().catch(() => null) }
  } catch {
    return { ok: false, ms: Date.now() - t0 }
  }
}
