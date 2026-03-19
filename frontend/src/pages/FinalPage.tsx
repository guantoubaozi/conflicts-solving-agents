import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Award, CheckCircle, AlertTriangle } from 'lucide-react'
import { api } from '../api'
import MarkdownContent from '../components/MarkdownContent'

export default function FinalPage() {
  const { debateId } = useParams<{ debateId: string }>()
  const [debate, setDebate] = useState<any>(null)
  const [summary, setSummary] = useState<any>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!debateId) return
    api.getDebate(debateId).then(d => {
      setDebate(d)
      return api.getJudgeSummary(debateId, d.current_round)
    }).then(setSummary).catch(() => {})
  }, [debateId])

  if (!debate) return (
    <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>
      加载中...
    </div>
  )

  return (
    <div style={{ maxWidth: 720 }}>
      <button onClick={() => navigate(`/debates/${debateId}`)} style={backBtn}>
        <ArrowLeft size={16} /> 返回
      </button>

      {/* Hero */}
      <div style={{ textAlign: 'center', padding: '32px 0 24px' }}>
        <Award size={48} strokeWidth={1.2}
          style={{ color: 'var(--color-primary)', marginBottom: 12 }} />
        <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 24,
          fontWeight: 700, margin: '0 0 8px' }}>
          终论结果
        </h2>
        <p style={{ color: 'var(--color-text-muted)', fontSize: 14 }}>
          {debate.proposition?.content}
        </p>
      </div>

      {summary ? (
        <div style={resultCard}>
          {/* 状态 badge */}
          {!summary.has_contradiction ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 14px', background: 'var(--color-success-bg)',
              borderRadius: 'var(--radius-md)', marginBottom: 16 }}>
              <CheckCircle size={18} style={{ color: 'var(--color-success)' }} />
              <span style={{ color: 'var(--color-success)', fontSize: 14,
                fontWeight: 500 }}>
                无矛盾，已达成共识
              </span>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 14px', background: 'var(--color-warning-bg)',
              borderRadius: 'var(--radius-md)', marginBottom: 16 }}>
              <AlertTriangle size={18}
                style={{ color: 'var(--color-warning)' }} />
              <span style={{ color: 'var(--color-warning)', fontSize: 14,
                fontWeight: 500 }}>
                已满轮次，裁判选出最优方案
              </span>
            </div>
          )}

          {/* 最终方案 */}
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
            最终方案
          </h3>
          <div style={{ padding: '16px 20px',
            background: 'var(--color-surface-2)',
            borderRadius: 'var(--radius-md)', marginBottom: 16 }}>
            <MarkdownContent content={summary.combined_solution} />
          </div>

          {/* 共识 */}
          {summary.consensus && (
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
                共识
              </h3>
              <div style={{ padding: '12px 16px',
                background: 'var(--color-success-bg)',
                borderRadius: 'var(--radius-md)', fontSize: 14,
                lineHeight: 1.6 }}>
                {summary.consensus}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '40px 0',
          color: 'var(--color-text-subtle)' }}>
          终论结果生成中...
        </div>
      )}
    </div>
  )
}

const backBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 0', marginBottom: 16, background: 'none', border: 'none',
  color: 'var(--color-text-muted)', fontSize: 13, cursor: 'pointer',
}
const resultCard: React.CSSProperties = {
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-lg)',
  padding: '24px',
  boxShadow: 'var(--shadow-md)',
}
