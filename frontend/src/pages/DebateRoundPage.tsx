import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Zap, Users } from 'lucide-react'
import { api } from '../api'
import ProgressBar from '../components/ProgressBar'
import AiProcessing from '../components/AiProcessing'
import MarkdownContent from '../components/MarkdownContent'
import JudgeSummaryCard from '../components/JudgeSummaryCard'

export default function DebateRoundPage() {
  const { debateId, round } = useParams<{ debateId: string; round: string }>()
  const roundNum = Number(round)
  const [debate, setDebate] = useState<any>(null)
  const [solutions, setSolutions] = useState<any[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [aiActive, setAiActive] = useState(false)
  const [partyNameMap, setPartyNameMap] = useState<Record<string, string>>({})
  const navigate = useNavigate()

  async function load() {
    if (!debateId) return
    const d = await api.getDebate(debateId).catch(() => null)
    setDebate(d)
    if (d?.parties) {
      const map: Record<string, string> = {}
      for (const p of d.parties) map[p.party_id] = p.name
      setPartyNameMap(map)
    }
    setSolutions(await api.getSolutions(debateId, roundNum).catch(() => []))
    setSummary(await api.getJudgeSummary(debateId, roundNum).catch(() => null))
  }

  useEffect(() => { load() }, [debateId, roundNum])

  function handleSseEvent(type: string) {
    if (type === 'agent_start') setAiActive(true)
    if (type === 'agent_done') { setAiActive(false); load() }
    if (type === 'round_phase_change') load()
  }

  if (!debate) return (
    <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>加载中...</div>
  )

  const roundPhase = (debate.current_round === roundNum
    ? debate.current_round_phase : null) || 'SOLUTION'

  const aiRunning = debate.ai_running || false

  async function triggerPhase() {
    if (!debateId) return
    if (roundPhase === 'SOLUTION') await api.runSolutionPhase(debateId, roundNum)
    else if (roundPhase === 'JUDGE') await api.runJudgePhase(debateId, roundNum)
    else if (roundPhase === 'DEBATE') await api.runDebatePhase(debateId, roundNum)
    setAiActive(true)
  }

  const triggerLabel: Record<string, string> = {
    SOLUTION: '生成解决方案', DEBATE: '辩论阶段',
  }

  const card: React.CSSProperties = {
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-lg)',
    padding: '16px 20px',
    boxShadow: 'var(--shadow-sm)',
  }

  return (
    <div>
      <button onClick={() => navigate(`/debates/${debateId}`)} style={backBtn}>
        <ArrowLeft size={16} /> 返回
      </button>
      <ProgressBar status={debate.status} currentRound={debate.current_round}
        roundPhase={roundPhase} />

      <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 22,
        fontWeight: 700, margin: '0 0 20px' }}>
        第 {roundNum} 轮辩论
      </h2>

      {debateId && <AiProcessing debateId={debateId} onEvent={handleSseEvent} />}

      {['SOLUTION', 'DEBATE'].includes(roundPhase) && !aiActive && !aiRunning
        && !(roundPhase === 'SOLUTION' && solutions.length > 0) && (
        <button onClick={triggerPhase} style={btnAction}>
          <Zap size={16} /> 触发 AI {triggerLabel[roundPhase]}
        </button>
      )}

      {aiRunning && !aiActive && (
        <div style={{ padding: '8px 16px', borderRadius: 'var(--radius-md)',
          background: 'var(--color-warning-bg, #fff8e1)', color: 'var(--color-warning, #f59e0b)',
          fontSize: 14, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Zap size={14} /> AI 正在后台处理中…
        </div>
      )}

      {/* 各方解决方案 */}
      <div style={{ marginTop: 20 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>各方解决方案</h3>
        {solutions.length === 0 ? (
          <div style={{ padding: '24px 0', textAlign: 'center',
            color: 'var(--color-text-subtle)', fontSize: 14 }}>
            暂无解决方案
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {solutions.map(s => (
              <div key={s.solution_id} style={card}>
                <div style={{ display: 'flex', alignItems: 'center',
                  gap: 8, marginBottom: 8 }}>
                  <div style={avatarSm}><Users size={12} /></div>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>
                    {partyNameMap[s.party_id] || s.party_id}
                  </span>
                  {s.is_valid === false && (
                    <span style={{ fontSize: 12, padding: '2px 8px',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--color-danger-bg)',
                      color: 'var(--color-danger)' }}>
                      无效：{s.invalid_reason}
                    </span>
                  )}
                </div>
                <MarkdownContent content={s.content} />
              </div>
            ))}
          </div>
        )}
      </div>

      {summary && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>裁判梳理</h3>
          <JudgeSummaryCard consensus={summary.consensus}
            contradictions={summary.contradictions || '无'}
            combinedSolution={summary.combined_solution} />
        </div>
      )}

      {roundPhase === 'HUMAN_REVIEW' && (
        <div style={{ marginTop: 20 }}>
          <button onClick={() => navigate(
            `/debates/${debateId}/rounds/${roundNum}/review`)}
            disabled={aiActive} style={btnPrimary}>
            <Users size={16} /> 进入人工确认
          </button>
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
const btnAction: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 20px', borderRadius: 'var(--radius-md)',
  background: 'var(--color-success)', color: '#fff',
  border: 'none', fontSize: 14, fontWeight: 500, cursor: 'pointer',
}
const btnPrimary: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 20px', borderRadius: 'var(--radius-md)',
  background: 'var(--color-primary)', color: '#fff',
  border: 'none', fontSize: 14, fontWeight: 500, cursor: 'pointer',
}
const avatarSm: React.CSSProperties = {
  width: 24, height: 24, borderRadius: '50%',
  background: 'var(--color-primary-light)', color: 'var(--color-primary)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
}
