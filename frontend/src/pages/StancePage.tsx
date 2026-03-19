import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, CheckCircle } from 'lucide-react'
import { api } from '../api'

export default function StancePage() {
  const { debateId, partyId } = useParams<{ debateId: string; partyId: string }>()
  const [viewpoint, setViewpoint] = useState('')
  const [facts, setFacts] = useState('')
  const [evidenceText, setEvidenceText] = useState('')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!debateId || !partyId) return
    api.getStance(debateId, partyId).then(s => {
      setViewpoint(s.viewpoint || '')
      setFacts(s.facts || '')
      setEvidenceText(s.evidence_pool?.map((e: any) => e.content).join('\n---\n') || '')
    }).catch(() => {})
  }, [debateId, partyId])

  const viewpointOver = viewpoint.length > 200
  const factsOver = facts.length > 1000

  async function save() {
    if (viewpointOver || factsOver || !debateId || !partyId) return
    setError(''); setSaved(false)
    try {
      const evidence_pool = evidenceText.trim()
        ? evidenceText.split('\n---\n').map((c, i) => ({
            evidence_id: `e${i}`, content: c.trim(), is_valid: true,
            created_round: 0, compress_status: 'NONE',
          }))
        : []
      await api.submitStance(debateId, partyId, { viewpoint, facts, evidence_pool })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setError(e.message) }
  }

  return (
    <div style={{ maxWidth: 640 }}>
      <button onClick={() => navigate(-1)} style={backBtn}><ArrowLeft size={16} /> 返回</button>

      <div style={card}>
        <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 20, fontWeight: 700, margin: '0 0 20px' }}>编辑立论</h2>

        <Field label="观点" required limit={200} current={viewpoint.length} over={viewpointOver}>
          <textarea value={viewpoint} onChange={e => setViewpoint(e.target.value)}
            rows={3} style={{ ...inputStyle, resize: 'vertical', borderColor: viewpointOver ? 'var(--color-danger)' : undefined }} />
        </Field>

        <Field label="事实" limit={1000} current={facts.length} over={factsOver}>
          <textarea value={facts} onChange={e => setFacts(e.target.value)}
            rows={5} style={{ ...inputStyle, resize: 'vertical', borderColor: factsOver ? 'var(--color-danger)' : undefined }} />
        </Field>

        <Field label="论据库" hint="多条用 --- 分隔">
          <textarea value={evidenceText} onChange={e => setEvidenceText(e.target.value)}
            rows={6} style={{ ...inputStyle, resize: 'vertical' }} />
        </Field>

        {error && <div style={{ padding: '10px 14px', background: 'var(--color-danger-bg)', color: 'var(--color-danger)', borderRadius: 'var(--radius-md)', fontSize: 13, marginBottom: 12 }}>{error}</div>}
        {saved && <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 14px', background: 'var(--color-success-bg)', color: 'var(--color-success)', borderRadius: 'var(--radius-md)', fontSize: 13, marginBottom: 12 }}><CheckCircle size={14} /> 保存成功</div>}

        <button onClick={save} disabled={viewpointOver || factsOver || !viewpoint.trim()} style={btnPrimary}>
          <Save size={16} /> 保存立论
        </button>
      </div>
    </div>
  )
}

function Field({ label, required, limit, current, over, hint, children }: {
  label: string; required?: boolean; limit?: number; current?: number; over?: boolean; hint?: string; children: React.ReactNode
}) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text)' }}>
          {label} {required && <span style={{ color: 'var(--color-danger)' }}>*</span>}
          {hint && <span style={{ fontWeight: 400, color: 'var(--color-text-subtle)', marginLeft: 6 }}>（{hint}）</span>}
        </label>
        {limit != null && current != null && (
          <span style={{ fontSize: 12, color: over ? 'var(--color-danger)' : 'var(--color-text-subtle)' }}>
            {current}/{limit}
          </span>
        )}
      </div>
      {children}
      {over && <div style={{ color: 'var(--color-danger)', fontSize: 12, marginTop: 4 }}>{label}超出字数限制</div>}
    </div>
  )
}

const card: React.CSSProperties = {
  background: 'var(--color-surface)', border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-lg)', padding: '24px', boxShadow: 'var(--shadow-sm)',
}
const btnPrimary: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 20px', borderRadius: 'var(--radius-md)',
  background: 'var(--color-primary)', color: '#fff',
  border: 'none', fontSize: 14, fontWeight: 500, cursor: 'pointer',
}
const backBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 0', marginBottom: 16, background: 'none', border: 'none',
  color: 'var(--color-text-muted)', fontSize: 13, cursor: 'pointer',
}
const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 12px', fontSize: 14,
  border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
  background: 'var(--color-surface-2)', outline: 'none', fontFamily: 'var(--font-body)',
}
