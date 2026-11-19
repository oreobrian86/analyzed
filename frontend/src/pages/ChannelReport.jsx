import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { dateTime, num, pct } from '../lib/format'
import { Bar, Confidence, ErrorBox, Insight, RefLinks, Spinner } from '../components/ui'

const SECTIONS = [['dna', 'Channel DNA'], ['pillars', 'Content Pillars'], ['formula', 'Content Formula'],
  ['performance', 'Performance'], ['strategy', 'Strategy'], ['opportunities', 'Content Opportunities']]

function Section({ id, title, children }) {
  return <section id={id} className="card report-section"><h2>{title}</h2>{children}</section>
}

export default function ChannelReport() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api(`/api/analyses/${id}/report`).then(setData).catch(setError) }, [id])
  const r = data?.report
  const refMap = useMemo(() => Object.fromEntries((r?.videos || []).map((v) => [v.ref, v.id])), [r])

  if (!data) return error ? <div><ErrorBox error={error} /><Link to={`/analyses/${id}`}>← Về trang xử lý</Link></div> : <Spinner />

  function download() {
    const blob = new Blob([data.markdown], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `bao-cao-${r.meta.channel.handle || id.slice(0, 8)}.md`
    a.click()
  }

  const { channel: ch, strategy: st, performance: perf, distribution: dist } = r
  const maxShare = Math.max(...r.pillars.map((p) => p.stats.share), 0.01)

  return (
    <div className="report">
      <header className="page-head">
        <div>
          <h1>Báo cáo {r.meta.channel.handle ? `@${r.meta.channel.handle}` : r.meta.channel.title}</h1>
          <p className="muted">{r.meta.channel.videos_analyzed}/{r.meta.channel.videos_total} video phân tích nội dung · tạo {dateTime(r.meta.generated_at)} · {r.meta.ai?.video_model || r.meta.ai?.video_provider}</p>
        </div>
        <div className="actions">
          <Link className="btn ghost" to={`/videos?analysis_id=${id}`}>Video</Link>
          <button className="btn" onClick={download}>Tải Markdown</button>
        </div>
      </header>
      <nav className="toc">{SECTIONS.map(([k, label]) => <a key={k} href={`#${k}`}>{label}</a>)}</nav>

      {r.meta.data_notes?.length > 0 && (
        <div className="alert alert-info"><b>Giới hạn dữ liệu</b><ul>{r.meta.data_notes.map((n, i) => <li key={i}>{n}</li>)}</ul></div>
      )}

      <Section id="dna" title="Channel DNA">
        <div className="head-row"><p className="lead">{ch.dna.summary}</p><Confidence value={ch.dna.confidence} /></div>
        <div className="grid-3">
          <div><div className="field-label">Định vị</div>{ch.dna.positioning}</div>
          <div><div className="field-label">Khán giả</div>{ch.dna.target_audience}</div>
          <div><div className="field-label">Giọng điệu / persona</div>{ch.dna.tone_and_persona}</div>
        </div>
        {ch.dna.signature_elements?.length > 0 && <div className="chips">{ch.dna.signature_elements.map((s, i) => <span className="chip" key={i}>{s}</span>)}</div>}
        {ch.insights.length > 0 && <><h3>Insight chính</h3>{ch.insights.map((i, k) => <Insight key={k} item={i} refMap={refMap} />)}</>}
      </Section>

      <Section id="pillars" title="Content Pillars">
        <p className="tiny muted">Nhóm tự động bằng embedding + clustering ({r.meta.embedding?.provider}, k={r.meta.clustering?.k}, silhouette={r.meta.clustering?.silhouette ?? '—'}), AI chỉ đặt tên & mô tả. Số liệu tính bằng thống kê, không do AI tạo.</p>
        <div className="pillars">
          {r.pillars.map((p) => (
            <div className="pillar" key={p.key}>
              <div className="head-row"><h3>{p.key}. {p.name}</h3><Confidence value={p.confidence} /></div>
              <Bar value={p.stats.share} max={maxShare} label={`${p.stats.video_count} video · ${pct(p.stats.share, 0)}`} />
              <p>{p.description}</p>
              <div className="kv">
                <span>Median views <b>{num(p.stats.median_views)}</b></span>
                <span>So với kênh <b>{p.stats.median_vs_channel != null ? `${p.stats.median_vs_channel}×` : '—'}</b></span>
                <span>ER median <b>{pct(p.stats.median_engagement_rate)}</b></span>
                {p.stats.small_sample && <span className="flag">mẫu nhỏ</span>}
              </div>
              <div className="field-label">Topic · Format</div><div>{p.topic} · {p.content_format}</div>
              <div className="field-label">Pattern</div><div>{p.pattern}</div>
              {p.content_formula && <><div className="field-label">Công thức</div><code>{p.content_formula}</code></>}
              <div className="field-label">Video đại diện</div><RefLinks refs={[p.representative_ref]} refMap={refMap} />
              <div className="field-label">Tất cả video</div><RefLinks refs={p.refs} refMap={refMap} />
            </div>
          ))}
        </div>
        <h3>Phân bổ nội dung</h3>
        <div className="grid-2">
          <div>{dist.by_format.map((f) => <Bar key={f.format} value={f.share} label={`${f.format} · ${f.videos}`} />)}</div>
          <div>{dist.by_hook_type.map((f) => <Bar key={f.hook_type} value={f.share} label={`hook ${f.hook_type} · ${f.videos}`} />)}</div>
        </div>
        <p className="tiny muted">CTA xuất hiện ở {pct(dist.cta_share, 0)} video · thời lượng median {dist.median_duration_sec ?? '—'}s · nhịp cắt median {dist.median_cuts_per_minute ?? '—'} lần/phút.</p>
      </Section>

      <Section id="formula" title="Content Formula">
        <div className="head-row"><code className="formula">{ch.content_formula.formula}</code><Confidence value={ch.content_formula.confidence} /></div>
        {ch.content_formula.steps?.length > 0 && <ol>{ch.content_formula.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>}
        {ch.content_formula.variations?.length > 0 && <><div className="field-label">Biến thể</div><ul>{ch.content_formula.variations.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
      </Section>

      <Section id="performance" title="Performance">
        <div className="stats">
          {[['Median views', num(perf.channel.median_views)], ['ER median', pct(perf.channel.median_engagement_rate)],
            ['Video / tuần', perf.channel.posts_per_week ?? '—'], ['Có metrics', perf.channel.videos_with_metrics]].map(([k, v]) => (
            <div className="stat" key={k}><div className="stat-label">{k}</div><div className="stat-value small">{v}</div></div>))}
        </div>
        <ul className="tiny muted">{perf.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        <div className="table-card">
          <table>
            <thead><tr><th>#</th><th>Chủ đề</th><th>Pillar</th><th>Views</th><th>× median</th><th>ER</th><th>Tuổi (ngày)</th><th /></tr></thead>
            <tbody>
              {[...r.videos].sort((a, b) => (b.views ?? -1) - (a.views ?? -1)).map((v) => {
                const tag = perf.outliers.over.includes(v.ref) ? 'over' : perf.outliers.under.includes(v.ref) ? 'under' : ''
                return (
                  <tr key={v.ref} className={tag ? `row-${tag}` : ''}>
                    <td><Link to={`/videos/${v.id}`}>{v.ref}</Link></td>
                    <td className="clip">{v.main_topic || v.caption}</td><td>{v.pillar || '—'}</td>
                    <td>{num(v.views)}</td><td>{v.relative_to_median ?? '—'}</td><td>{pct(v.engagement_rate)}</td><td>{v.age_days ?? '—'}</td>
                    <td>{tag === 'over' && <span className="chip good">vượt trội</span>}{tag === 'under' && <span className="chip bad">thấp</span>}</td>
                  </tr>)
              })}
            </tbody>
          </table>
        </div>
        {ch.weaknesses.length > 0 && <><h3>Điểm yếu nội dung</h3>{ch.weaknesses.map((i, k) => <Insight key={k} item={i} refMap={refMap} />)}</>}
      </Section>

      <Section id="strategy" title="Strategy">
        <p className="lead">{st.summary}</p>
        {st.strategy.map((i, k) => <Insight key={k} item={i} refMap={refMap} />)}
        {st.content_mix?.length > 0 && (
          <><h3>Đề xuất tỷ trọng nội dung</h3>
            {st.content_mix.map((m, i) => <div key={i}><Bar value={Number(m.suggested_share) || 0} label={`${m.pillar} · ${pct(m.suggested_share, 0)}`} /><p className="tiny muted">{m.reason}</p></div>)}</>
        )}
      </Section>

      <Section id="opportunities" title="Content Opportunities">
        {st.opportunities.map((i, k) => <Insight key={k} item={i} refMap={refMap} />)}
        {st.experiments?.length > 0 && (
          <><h3>Thử nghiệm đề xuất</h3>
            <table><thead><tr><th>Ý tưởng</th><th>Dựa trên</th><th>Đo bằng</th><th>Cỡ mẫu</th></tr></thead>
              <tbody>{st.experiments.map((e, i) => (
                <tr key={i}><td>{e.idea}</td><td><RefLinks refs={e.based_on_refs} refMap={refMap} /></td><td>{e.success_metric}</td><td>{e.sample_size}</td></tr>))}
              </tbody></table></>
        )}
        <p className="tiny muted">Khuyến nghị là giả thuyết cần kiểm chứng bằng thử nghiệm, không phải cam kết kết quả. Tương quan trong dữ liệu không chứng minh quan hệ nhân quả.</p>
      </Section>
    </div>
  )
}
