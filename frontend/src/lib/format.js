export const num = (n) => {
  if (n === null || n === undefined) return '—'
  const x = Number(n)
  if (x >= 1e6) return (x / 1e6).toFixed(x >= 1e7 ? 0 : 1).replace('.0', '') + 'M'
  if (x >= 1e3) return (x / 1e3).toFixed(x >= 1e4 ? 0 : 1).replace('.0', '') + 'K'
  return String(Math.round(x))
}

export const pct = (v, digits = 1) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(digits)}%`)

export const date = (s) => (s ? new Date(s).toLocaleDateString('vi-VN') : '—')
export const dateTime = (s) => (s ? new Date(s).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' }) : '—')

export const bytes = (b) => {
  if (!b) return '0 MB'
  return `${(b / 1024 / 1024).toFixed(b > 100 * 1024 * 1024 ? 0 : 1)} MB`
}

export const STATUS_LABEL = {
  draft: 'Nháp', queued: 'Đang chờ', collecting: 'Thu thập', processing: 'Đang xử lý', aggregating: 'Tổng hợp',
  done: 'Hoàn tất', partial: 'Xong một phần', failed: 'Lỗi', cancelled: 'Đã huỷ', pending: 'Chờ', skipped: 'Bỏ qua',
}

export const ACTIVE = ['draft', 'queued', 'collecting', 'processing', 'aggregating']

export const SOURCE_LABEL = { profile: 'Profile', urls: 'URL video', upload: 'Upload', import: 'Import' }
