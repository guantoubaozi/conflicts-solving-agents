import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Check, User, Plus, Loader, ChevronDown, ChevronUp, Flag, ThumbsUp, ThumbsDown } from 'lucide-react'
import { api } from '../api'
import MarkdownContent from '../components/MarkdownContent'
import ProgressBar from '../components/ProgressBar'

export default function HumanReviewPage() {
  const { debateId, round } = useParams<{ debateId: string; round: string }>()
  const roundNum = Number(round)
  const [debate, setDebate] = useState<any>(null)
  const [parties, setParties] = useState<any[]>([])
  const [stances, setStances] = useState<Record<string, any>>({})
  const [editFacts, setEditFacts] = useState<Record<string, string>>({})
  const [appendTexts, setAppendTexts] = useState<Record<string, string>>({})
  const [showAppend, setShowAppend] = useState<Record<string, boolean>>({})
  const [organizing, setOrganizing] = useState<Record<string, boolean>>({})
  const [confirmed, setConfirmed] = useState<string[]>([])
  const [finalRequestBy, setFinalRequestBy] = useState<string | null>(null)
  const [finalVotes, setFinalVotes] = useState<Record<string, boolean>>({})
  const [finalTriggered, setFinalTriggered] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const esRef = useRef<EventSource | null>(null)

  // 构建 partyId -> name 映射
  const partyNameMap: Record<string, string> = {}
  for (const p of parties) partyNameMap[p.party_id] = p.name

  async function load() {
    if (!debateId) return
    const d = await api.getDebate(debateId).catch(() => null)
    setDebate(d)
    if (d) {
      setFinalRequestBy(d.final_request_by || null)
      setFinalVotes(d.final_request_votes || {})
    }
    const ps = await api.listParties(debateId).catch(() => [])
    setParties(ps)
    const sc: Record<string, any> = {}
    const ef: Record<string, string> = {}
    const org: Record<string, boolean> = {}
    for (const p of ps) {
      const s = await api.getStance(debateId, p.party_id).catch(() => null)
      if (s) {
        sc[p.party_id] = s; ef[p.party_id] = s.facts || ''
        org[p.party_id] = s.facts_organizing || false
      }
    }
    setStances(sc); setEditFacts(ef); setOrganizing(org)
    setConfirmed(d?.round_status?.[roundNum]?.human_confirmed || [])
  }

  useEffect(() => { load() }, [debateId, roundNum])

  // SSE 监听
  useEffect(() => {
    if (!debateId) return
    const es = new EventSource(`/api/debates/${debateId}/stream`)
    esRef.current = es
    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'facts_organized') {
          const pid = msg.party_id || msg.data?.party_id
          if (pid) {
            setOrganizing(prev => ({ ...prev, [pid]: false }))
            api.getStance(debateId, pid).then(s => {
              if (s) {
                setStances(prev => ({ ...prev, [pid]: s }))
                setEditFacts(prev => ({ ...prev, [pid]: s.facts || '' }))
              }
            }).catch(() => {})
          }
        }
        if (msg.type === 'final_vote_update') {
          const d = msg.data || msg
          setFinalRequestBy(d.final_request_by || null)
          setFinalVotes(d.final_request_votes || {})
        }
        if (msg.type === 'debate_final') {
          setFinalTriggered(true)
          setTimeout(() => navigate(`/debates/${debateId}/final`), 1500)
        }
      } catch {}
    }
    return () => es.close()
  }, [debateId])

  async function handleAppendFact(partyId: string) {
    if (!debateId) return
    const text = (appendTexts[partyId] || '').trim()
    if (!text) return; setError('')
    try {
      await api.appendFact(debateId, partyId, text, roundNum)
      setAppendTexts(prev => ({ ...prev, [partyId]: '' }))
      setOrganizing(prev => ({ ...prev, [partyId]: true }))
      setShowAppend(prev => ({ ...prev, [partyId]: false }))
      const s = await api.getStance(debateId, partyId).catch(() => null)
      if (s) {
        setStances(prev => ({ ...prev, [partyId]: s }))
        setEditFacts(prev => ({ ...prev, [partyId]: s.facts || '' }))
      }
    } catch (e: any) { setError(e.message) }
  }

  async function confirm(partyId: string) {
    if (!debateId) return; setError('')
    try {
      const result: any = await api.confirmRound(debateId, roundNum, partyId)
      setConfirmed(result.confirmed || [])
      if (result.debate_status === 'FINAL') navigate(`/debates/${debateId}/final`)
      else if (result.all_confirmed) navigate(`/debates/${debateId}/rounds/${roundNum + 1}`)
    } catch (e: any) { setError(e.message) }
  }

  async function handleRequestFinal(partyId: string) {
    if (!debateId) return; setError('')
    try {
      const r: any = await api.requestFinal(debateId, roundNum, partyId)
      setFinalRequestBy(r.final_request_by)
      setFinalVotes(r.final_request_votes || {})
      if (r.final_triggered) {
        setFinalTriggered(true)
        setTimeout(() => navigate(`/debates/${debateId}/final`), 1500)
      }
    } catch (e: any) { setError(e.message) }
  }

  async function handleVoteFinal(partyId: string, agree: boolean) {
    if (!debateId) return; setError('')
    try {
      const r: any = await api.voteFinal(debateId, roundNum, partyId, agree)
      setFinalRequestBy(r.final_request_by)
      setFinalVotes(r.final_request_votes || {})
      if (r.final_triggered) {
        setFinalTriggered(true)
        setTimeout(() => navigate(`/debates/${debateId}/final`), 1500)
      }
    } catch (e: any) { setError(e.message) }
  }

  if (!debate) return (
    <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>加载中...</div>
  )

  return (
    <div>
      <button onClick={() => navigate(-1)} style={backBtn}>
        <ArrowLeft size={16} /> 返回
      </button>
      <ProgressBar status={debate.status} currentRound={debate.current_round} roundPhase="HUMAN_REVIEW" />

      <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 22, fontWeight: 700, margin: '0 0 8px' }}>
        第 {roundNum} 轮 — 人工确认
      </h2>
      <p style={{ color: 'var(--color-text-muted)', fontSize: 14, marginBottom: 20 }}>
        各方可追加事实（LLM 自动整理），确认后推进下一轮。
      </p>

      {/* 终论申请区域 */}
      {finalTriggered && (
        <div style={{ ...infoCard, background: 'var(--color-success-bg)', borderColor: 'var(--color-success)', marginBottom: 16 }}>
          <Check size={18} style={{ color: 'var(--color-success)' }} />
          <span style={{ color: 'var(--color-success)', fontWeight: 500 }}>终论已触发，正在处理...</span>
        </div>
      )}

      {!finalTriggered && finalRequestBy && (
        <div style={{ ...card, marginBottom: 16, borderColor: 'var(--color-warning)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Flag size={16} style={{ color: 'var(--color-warning)' }} />
            <span style={{ fontWeight: 600, fontSize: 14 }}>
              {partyNameMap[finalRequestBy] || finalRequestBy} 申请直接终论
            </span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {parties.map(p => {
              const vote = finalVotes[p.party_id]
              const isRequester = p.party_id === finalRequestBy
              return (
                <div key={p.party_id} style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', borderRadius: 'var(--radius-md)',
                  background: vote === true ? 'var(--color-success-bg)' : vote === false ? 'var(--color-danger-bg)' : 'var(--color-surface-2)',
                  border: `1px solid ${vote === true ? 'var(--color-success)' : vote === false ? 'var(--color-danger)' : 'var(--color-border)'}`,
                  fontSize: 13,
                }}>
                  <span style={{ fontWeight: 500 }}>{p.name}</span>
                  {vote === true && <Check size={12} style={{ color: 'var(--color-success)' }} />}
                  {vote === false && <ThumbsDown size={12} style={{ color: 'var(--color-danger)' }} />}
                  {vote === undefined && !isRequester && (
                    <span style={{ color: 'var(--color-text-subtle)' }}>待投票</span>
                  )}
                </div>
              )
            })}
          </div>
          {/* 非发起方的投票按钮 */}
          {parties.filter(p => p.party_id !== finalRequestBy && finalVotes[p.party_id] === undefined).map(p => (
            <div key={p.party_id} style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{p.name}：</span>
              <button onClick={() => handleVoteFinal(p.party_id, true)} style={btnSuccess}>
                <ThumbsUp size={13} /> 同意终论
              </button>
              <button onClick={() => handleVoteFinal(p.party_id, false)} style={btnDanger}>
                <ThumbsDown size={13} /> 不同意
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 各方卡片 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {parties.map(p => {
          const stance = stances[p.party_id]
          const isConfirmed = confirmed.includes(p.party_id)
          const isOrganizing = organizing[p.party_id] || false
          const factsVal = editFacts[p.party_id] || ''
          const isAppendOpen = showAppend[p.party_id] || false
          return (
            <div key={p.party_id} style={card}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={avatar}><User size={14} /></div>
                  <span style={{ fontWeight: 600, fontSize: 15 }}>{p.name}</span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  {isOrganizing && (
                    <span style={{ ...badge, color: 'var(--color-info)', background: 'var(--color-info-bg)' }}>
                      <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> 整理中
                    </span>
                  )}
                  {isConfirmed && (
                    <span style={{ ...badge, color: 'var(--color-success)', background: 'var(--color-success-bg)' }}>
                      <Check size={12} /> 已确认
                    </span>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: 12 }}>
                <div style={sectionLabel}>观点（不可修改）</div>
                <div style={readonlyBox}><MarkdownContent content={stance?.viewpoint || ''} /></div>
              </div>

              <div style={{ marginBottom: 12 }}>
                <div style={sectionLabel}>事实库</div>
                <div style={readonlyBox}>
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6,
                    fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                    {factsVal || '（暂无事实）'}
                  </pre>
                </div>
              </div>

              {!isConfirmed && (
                <div style={{ marginBottom: 12 }}>
                  <button onClick={() => setShowAppend(prev => ({ ...prev, [p.party_id]: !isAppendOpen }))}
                    style={{ ...btnSmall, marginBottom: isAppendOpen ? 8 : 0 }}>
                    {isAppendOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                    {isAppendOpen ? '收起' : '追加事实'}
                  </button>
                  {isAppendOpen && (
                    <div>
                      <textarea value={appendTexts[p.party_id] || ''}
                        onChange={e => setAppendTexts(prev => ({ ...prev, [p.party_id]: e.target.value }))}
                        rows={3} placeholder="输入新增事实内容，提交后 LLM 将自动整理合并"
                        disabled={isOrganizing}
                        style={{ ...inputStyle, resize: 'vertical', opacity: isOrganizing ? 0.6 : 1 }} />
                      <div style={{ marginTop: 6 }}>
                        <button onClick={() => handleAppendFact(p.party_id)}
                          disabled={isOrganizing || !(appendTexts[p.party_id] || '').trim()}
                          style={btnGhost}><Plus size={14} /> 提交追加</button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {!isConfirmed && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <button onClick={() => confirm(p.party_id)} disabled={isOrganizing}
                    style={{ ...btnPrimary, opacity: isOrganizing ? 0.6 : 1 }}>
                    <Check size={14} /> 确认推进
                  </button>
                  {!finalRequestBy && !finalTriggered && (
                    <button onClick={() => handleRequestFinal(p.party_id)} style={btnWarning}>
                      <Flag size={14} /> 申请直接终论
                    </button>
                  )}
                  {isOrganizing && (
                    <span style={{ fontSize: 12, color: 'var(--color-text-subtle)' }}>事实整理中，请稍候</span>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {error && <div style={{ marginTop: 12, padding: '10px 14px',
        background: 'var(--color-danger-bg)', color: 'var(--color-danger)',
        borderRadius: 'var(--radius-md)', fontSize: 13 }}>{error}</div>}

      <div style={{ marginTop: 16, fontSize: 13, color: 'var(--color-text-subtle)', textAlign: 'center' }}>
        已确认：{confirmed.length}/{parties.length}，全员确认后自动推进
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}


const card: React.CSSProperties = {
  background: 'var(--color-surface)', border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-lg)', padding: '20px 24px', boxShadow: 'var(--shadow-sm)',
}
const infoCard: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8,
  padding: '12px 16px', borderRadius: 'var(--radius-md)',
  border: '1px solid var(--color-border)',
}
const avatar: React.CSSProperties = {
  width: 28, height: 28, borderRadius: '50%',
  background: 'var(--color-primary-light)', color: 'var(--color-primary)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
}
const badge: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 4,
  fontSize: 12, padding: '3px 10px', borderRadius: 'var(--radius-sm)',
}
const sectionLabel: React.CSSProperties = {
  fontSize: 13, fontWeight: 600, color: 'var(--color-text)', marginBottom: 6,
}
const readonlyBox: React.CSSProperties = {
  padding: '10px 14px', background: 'var(--color-surface-2)',
  borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)',
}
const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 12px', fontSize: 14,
  border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
  background: 'var(--color-surface-2)', outline: 'none', fontFamily: 'var(--font-body)',
}
const btnPrimary: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 20px', borderRadius: 'var(--radius-md)',
  background: 'var(--color-primary)', color: '#fff',
  border: 'none', fontSize: 13, fontWeight: 500, cursor: 'pointer',
}
const btnGhost: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 16px', borderRadius: 'var(--radius-md)',
  background: 'transparent', color: 'var(--color-text-muted)',
  border: '1px solid var(--color-border)', fontSize: 13, cursor: 'pointer',
}
const btnSmall: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  padding: '4px 12px', borderRadius: 'var(--radius-sm)',
  background: 'var(--color-surface)', color: 'var(--color-primary)',
  border: '1px solid var(--color-border)', fontSize: 12, cursor: 'pointer',
}
const btnWarning: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 16px', borderRadius: 'var(--radius-md)',
  background: 'var(--color-warning-bg)', color: 'var(--color-warning)',
  border: '1px solid var(--color-warning)', fontSize: 13, fontWeight: 500, cursor: 'pointer',
}
const btnSuccess: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 14px', borderRadius: 'var(--radius-md)',
  background: 'var(--color-success-bg)', color: 'var(--color-success)',
  border: '1px solid var(--color-success)', fontSize: 12, cursor: 'pointer',
}
const btnDanger: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 14px', borderRadius: 'var(--radius-md)',
  background: 'var(--color-danger-bg)', color: 'var(--color-danger)',
  border: '1px solid var(--color-danger)', fontSize: 12, cursor: 'pointer',
}
const backBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 0', marginBottom: 16, background: 'none', border: 'none',
  color: 'var(--color-text-muted)', fontSize: 13, cursor: 'pointer',
}
