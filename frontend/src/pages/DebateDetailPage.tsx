import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, UserPlus, Play, Pencil, Plus, User, Save, CheckCircle } from 'lucide-react'
import { api } from '../api'
import ProgressBar from '../components/ProgressBar'

const SOUL_PLACEHOLDER = '示例：我倾向于周全考虑，决策时优先评估风险和可行性。习惯用SWOT分析框架思考问题。风格偏保守稳健，注重长期影响而非短期收益。'

export default function DebateDetailPage() {
  const { debateId } = useParams<{ debateId: string }>()
  const [debate, setDebate] = useState<any>(null)
  const [newPartyName, setNewPartyName] = useState('')
  const [newPartySoul, setNewPartySoul] = useState('')
  const [error, setError] = useState('')
  const [editingBg, setEditingBg] = useState(false)
  const [bgDraft, setBgDraft] = useState('')
  const [bgSaving, setBgSaving] = useState(false)
  const [editingSoulId, setEditingSoulId] = useState<string | null>(null)
  const [soulDraft, setSoulDraft] = useState('')
  const [soulSaving, setSoulSaving] = useState(false)
  const [soulSaved, setSoulSaved] = useState<string | null>(null)
  const navigate = useNavigate()

  async function load() {
    if (!debateId) return
    const d = await api.getDebate(debateId).catch(() => null)
    setDebate(d)
  }
  useEffect(() => { load() }, [debateId])

  async function addParty() {
    if (!newPartyName.trim() || !debateId) return
    setError('')
    try {
      await api.addParty(debateId, newPartyName.trim(), newPartySoul.trim())
      setNewPartyName(''); setNewPartySoul(''); load()
    } catch (e: any) { setError(e.message) }
  }

  async function startDebate() {
    if (!debateId) return; setError('')
    try { await api.startDebate(debateId); load() }
    catch (e: any) { setError(e.message) }
  }

  async function saveBackground() {
    if (!debateId) return; setBgSaving(true)
    try { await api.updateBackground(debateId, bgDraft.trim()); setEditingBg(false); load() }
    catch (e: any) { setError(e.message) }
    finally { setBgSaving(false) }
  }

  async function saveSoul(partyId: string) {
    if (!debateId) return; setSoulSaving(true)
    try {
      await api.updatePartySoul(debateId, partyId, soulDraft.trim())
      setEditingSoulId(null); setSoulSaved(partyId)
      setTimeout(() => setSoulSaved(null), 2000)
      load()
    } catch (e: any) { setError(e.message) }
    finally { setSoulSaving(false) }
  }

  if (!debate) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>加载中...</div>

  const { proposition, status, current_round, parties } = debate
  const roundPhase = debate.round_status?.[current_round]?.phase
  const canEditBg = status === 'INIT' || status === 'STANCE'

  return (
    <div>
      <button onClick={() => navigate('/')} style={backBtn}><ArrowLeft size={16} /> 返回列表</button>

      <ProgressBar status={status} currentRound={current_round} roundPhase={roundPhase} />

      {/* 命题卡片 */}
      <div style={card}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-subtle)', textTransform: 'uppercase' as const, letterSpacing: '0.05em', marginBottom: 8 }}>辩论命题</div>
        <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 22, fontWeight: 700, margin: 0, lineHeight: 1.4 }}>
          {proposition?.content}
        </h2>
        <div style={{ fontSize: 12, color: 'var(--color-text-subtle)', marginTop: 8 }}>ID: {debateId}</div>
      </div>

      {/* 背景 */}
      <div style={{ ...card, marginTop: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>题目背景</span>
          {canEditBg && !editingBg && (
            <button onClick={() => { setBgDraft(proposition?.background || ''); setEditingBg(true) }} style={btnSmall}>
              <Pencil size={13} /> {proposition?.background ? '编辑' : '添加'}
            </button>
          )}
        </div>
        {editingBg ? (
          <div>
            <textarea value={bgDraft} onChange={e => setBgDraft(e.target.value.slice(0, 200))}
              rows={3} style={{ ...inputStyle, resize: 'vertical' }} />
            <div style={{ fontSize: 12, color: bgDraft.length > 180 ? 'var(--color-danger)' : 'var(--color-text-subtle)', textAlign: 'right', marginTop: 4 }}>
              {bgDraft.length}/200
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button onClick={saveBackground} disabled={bgSaving} style={btnPrimary}>{bgSaving ? '保存中...' : '保存'}</button>
              <button onClick={() => setEditingBg(false)} style={btnGhost}>取消</button>
            </div>
          </div>
        ) : proposition?.background ? (
          <div style={{ padding: '10px 14px', background: 'var(--color-primary-light)', borderRadius: 'var(--radius-md)', borderLeft: '3px solid var(--color-primary)', fontSize: 14, lineHeight: 1.6, color: 'var(--color-text)' }}>
            {proposition.background}
          </div>
        ) : (
          <div style={{ color: 'var(--color-text-subtle)', fontSize: 13 }}>（未设置）</div>
        )}
      </div>

      {/* 辩论方 */}
      <div style={{ ...card, marginTop: 12 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>辩论方</div>
        {parties?.length === 0 && <div style={{ color: 'var(--color-text-subtle)', fontSize: 13 }}>尚未添加辩论方</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {parties?.map((p: any) => (
            <div key={p.party_id} style={{
              padding: '12px 14px', background: 'var(--color-surface-2)',
              borderRadius: 'var(--radius-md)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={avatar}><User size={16} /></div>
                  <span style={{ fontWeight: 500, fontSize: 14 }}>{p.name}</span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  {(status === 'STANCE' || status === 'INIT') && (
                    <button onClick={() => navigate(`/debates/${debateId}/stance/${p.party_id}`)} style={btnSmall}>编辑立论</button>
                  )}
                  {status === 'ROUND' && (
                    <button onClick={() => navigate(`/debates/${debateId}/rounds/${current_round}`)} style={btnSmall}>查看本轮</button>
                  )}
                  {status === 'FINAL' && (
                    <button onClick={() => navigate(`/debates/${debateId}/final`)} style={btnSmall}>查看终论</button>
                  )}
                </div>
              </div>
              {/* 性格显示/编辑 */}
              {editingSoulId === p.party_id ? (
                <div style={{ marginTop: 8 }}>
                  <textarea value={soulDraft} onChange={e => setSoulDraft(e.target.value.slice(0, 200))}
                    rows={3} placeholder={SOUL_PLACEHOLDER}
                    style={{ ...inputStyle, resize: 'vertical', fontSize: 13 }} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
                    <span style={{ fontSize: 12, color: soulDraft.length > 180 ? 'var(--color-danger)' : 'var(--color-text-subtle)' }}>
                      {soulDraft.length}/200
                    </span>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => saveSoul(p.party_id)} disabled={soulSaving} style={{ ...btnSmall, color: 'var(--color-primary)' }}>
                        <Save size={12} /> {soulSaving ? '保存中...' : '保存'}
                      </button>
                      <button onClick={() => setEditingSoulId(null)} style={btnSmall}>取消</button>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: 6, display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                  {p.soul ? (
                    <div style={{ flex: 1, fontSize: 12, color: 'var(--color-text-muted)', lineHeight: 1.5, padding: '4px 8px', background: 'var(--color-surface)', borderRadius: 'var(--radius-sm)', border: '1px dashed var(--color-border)' }}>
                      🧠 {p.soul}
                    </div>
                  ) : (
                    <span style={{ fontSize: 12, color: 'var(--color-text-subtle)', fontStyle: 'italic' }}>未设置性格</span>
                  )}
                  {status !== 'FINAL' && (
                    <button onClick={() => { setSoulDraft(p.soul || ''); setEditingSoulId(p.party_id) }}
                      style={{ ...btnSmall, padding: '2px 8px', fontSize: 11 }}>
                      <Pencil size={11} /> {p.soul ? '改' : '设置性格'}
                    </button>
                  )}
                  {soulSaved === p.party_id && (
                    <span style={{ fontSize: 12, color: 'var(--color-success)', display: 'flex', alignItems: 'center', gap: 3 }}>
                      <CheckCircle size={12} /> 已保存
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {status !== 'FINAL' && (
          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <input value={newPartyName} onChange={e => setNewPartyName(e.target.value)}
                placeholder="辩论方名称" style={{ ...inputStyle, flex: 1 }}
                onKeyDown={e => e.key === 'Enter' && addParty()} />
              <button onClick={addParty} style={btnGhost}><UserPlus size={14} /> 添加</button>
            </div>
            {newPartyName.trim() && (
              <div style={{ marginTop: 8 }}>
                <textarea value={newPartySoul} onChange={e => setNewPartySoul(e.target.value.slice(0, 200))}
                  rows={2} placeholder={SOUL_PLACEHOLDER}
                  style={{ ...inputStyle, resize: 'vertical', fontSize: 13 }} />
                <div style={{ fontSize: 12, color: newPartySoul.length > 180 ? 'var(--color-danger)' : 'var(--color-text-subtle)', textAlign: 'right', marginTop: 2 }}>
                  性格（选填）{newPartySoul.length}/200
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 开始辩论 */}
      {status === 'STANCE' && parties?.length >= 2 && (
        <div style={{ marginTop: 16 }}>
          <button onClick={startDebate} style={btnPrimary}><Play size={16} /> 开始辩论</button>
        </div>
      )}

      {error && <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--color-danger-bg)', color: 'var(--color-danger)', borderRadius: 'var(--radius-md)', fontSize: 13 }}>{error}</div>}
    </div>
  )
}


/* ── styles ── */
const card: React.CSSProperties = {
  background: 'var(--color-surface)', border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-lg)', padding: '20px 24px', boxShadow: 'var(--shadow-sm)',
}
const btnPrimary: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 20px', borderRadius: 'var(--radius-md)',
  background: 'var(--color-primary)', color: '#fff',
  border: 'none', fontSize: 14, fontWeight: 500, cursor: 'pointer',
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
const avatar: React.CSSProperties = {
  width: 32, height: 32, borderRadius: '50%',
  background: 'var(--color-primary-light)', color: 'var(--color-primary)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
}
