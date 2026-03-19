import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, MessageSquare, Clock, Trash2 } from 'lucide-react'
import { api } from '../api'

const STATUS_LABEL: Record<string, string> = {
  INIT: '初始化', STANCE: '立论中', ROUND: '辩论中', FINAL: '已终论',
}
const STATUS_COLOR: Record<string, { bg: string; fg: string }> = {
  INIT:   { bg: 'var(--color-surface-2)', fg: 'var(--color-text-muted)' },
  STANCE: { bg: 'var(--color-info-bg)',    fg: 'var(--color-info)' },
  ROUND:  { bg: 'var(--color-warning-bg)', fg: 'var(--color-warning)' },
  FINAL:  { bg: 'var(--color-success-bg)', fg: 'var(--color-success)' },
}

export default function DebateListPage() {
  const [debates, setDebates] = useState<any[]>([])
  const [proposition, setProposition] = useState('')
  const [background, setBackground] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState<string | null>(null)
  const navigate = useNavigate()

  const loadDebates = () => api.listDebates().then(setDebates).catch(() => {})
  useEffect(() => { loadDebates() }, [])

  async function handleDelete(e: React.MouseEvent, debateId: string, proposition: string) {
    e.stopPropagation()
    if (!confirm(`确定删除辩论「${proposition}」吗？删除后所有数据将无法恢复。`)) return
    setDeleting(debateId)
    try {
      await api.deleteDebate(debateId)
      setDebates(prev => prev.filter(d => d.debate_id !== debateId))
    } catch (e: any) { alert('删除失败: ' + e.message) }
    finally { setDeleting(null) }
  }

  async function create() {
    if (!proposition.trim()) return
    setCreating(true); setError('')
    try {
      const { debate_id } = await api.createDebate(proposition.trim(), 'user', background.trim())
      navigate(`/debates/${debate_id}`)
    } catch (e: any) { setError(e.message); setCreating(false) }
  }

  return (
    <div>
      {/* Hero */}
      <div style={{ textAlign: 'center', padding: '40px 0 32px' }}>
        <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700, marginBottom: 8 }}>
          AI 辅助分歧解决平台
        </h1>
        <p style={{ color: 'var(--color-text-muted)', fontSize: 15, maxWidth: 520, margin: '0 auto 24px', lineHeight: 1.7 }}>
          多方各自提出立场和方案，AI 自动梳理共识与矛盾，经过结构化的讨论与反思，逐步收敛为兼顾各方诉求的解决方案。创建一个议题，添加参与方，开始讨论。
        </p>
        {!showCreate && (
          <button onClick={() => setShowCreate(true)} style={btnPrimary}>
            <Plus size={16} /> 创建新议题
          </button>
        )}
      </div>

      {/* 创建表单 */}
      {showCreate && (
        <div style={card}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>创建新议题</div>
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>议题</label>
            <input value={proposition} onChange={e => setProposition(e.target.value)}
              placeholder="描述需要解决的分歧问题" style={inputStyle}
              onKeyDown={e => e.key === 'Enter' && create()} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>
              题目背景 <span style={{ color: 'var(--color-text-subtle)', fontWeight: 400 }}>（选填，≤200字）</span>
            </label>
            <textarea value={background}
              onChange={e => setBackground(e.target.value.slice(0, 200))}
              placeholder="所有参与方承认为真的前提和背景信息"
              rows={3} style={{ ...inputStyle, resize: 'vertical', minHeight: 72 }} />
            <div style={{ fontSize: 12, color: background.length > 180 ? 'var(--color-danger)' : 'var(--color-text-subtle)', textAlign: 'right', marginTop: 4 }}>
              {background.length}/200
            </div>
          </div>
          {error && <div style={{ color: 'var(--color-danger)', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={create} disabled={creating || !proposition.trim()} style={btnPrimary}>
              {creating ? '创建中...' : '创建议题'}
            </button>
            <button onClick={() => { setShowCreate(false); setError('') }} style={btnGhost}>取消</button>
          </div>
        </div>
      )}

      {/* 列表 */}
      {debates.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--color-text-subtle)' }}>
          <MessageSquare size={40} strokeWidth={1.2} style={{ marginBottom: 12, opacity: 0.4 }} />
          <p>暂无议题，创建一个开始讨论吧</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {debates.map(d => {
            const sc = STATUS_COLOR[d.status] || STATUS_COLOR.INIT
            return (
              <div key={d.debate_id} onClick={() => navigate(`/debates/${d.debate_id}`)}
                style={{
                  ...card, cursor: 'pointer',
                  transition: 'box-shadow var(--transition-fast)',
                }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6, lineHeight: 1.4 }}>{d.proposition}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13, color: 'var(--color-text-muted)' }}>
                      <span>第 {d.current_round} 轮</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Clock size={12} /> {new Date(d.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <span style={{
                    padding: '3px 10px', borderRadius: 'var(--radius-sm)',
                    fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap',
                    background: sc.bg, color: sc.fg,
                  }}>
                    {STATUS_LABEL[d.status] || d.status}
                  </span>
                  <button
                    title="删除辩论"
                    disabled={deleting === d.debate_id}
                    onClick={e => handleDelete(e, d.debate_id, d.proposition)}
                    style={{
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      padding: 4, borderRadius: 'var(--radius-sm)', color: 'var(--color-text-subtle)',
                      opacity: deleting === d.debate_id ? 0.4 : 0.6,
                      transition: 'opacity var(--transition-fast), color var(--transition-fast)',
                    }}
                    onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.opacity = '1'; (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-danger)' }}
                    onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.6'; (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-subtle)' }}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}


/* ── shared inline styles ── */
const card: React.CSSProperties = {
  background: 'var(--color-surface)', border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-lg)', padding: '20px 24px',
  boxShadow: 'var(--shadow-sm)',
}
const btnPrimary: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 20px', borderRadius: 'var(--radius-md)',
  background: 'var(--color-primary)', color: '#fff',
  border: 'none', fontSize: 14, fontWeight: 500, cursor: 'pointer',
  transition: 'background var(--transition-fast)',
}
const btnGhost: React.CSSProperties = {
  padding: '8px 20px', borderRadius: 'var(--radius-md)',
  background: 'transparent', color: 'var(--color-text-muted)',
  border: '1px solid var(--color-border)', fontSize: 14, cursor: 'pointer',
  transition: 'background var(--transition-fast)',
}
const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6,
  color: 'var(--color-text)',
}
const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 12px', fontSize: 14,
  border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
  background: 'var(--color-surface-2)', outline: 'none',
  transition: 'border-color var(--transition-fast)',
  fontFamily: 'var(--font-body)',
}
