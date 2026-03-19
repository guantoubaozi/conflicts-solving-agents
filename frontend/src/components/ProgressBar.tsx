interface Props {
  status: string
  currentRound: number
  roundPhase?: string
}

const PHASES = ['立论', '辩论轮次', '终论']
const ROUND_PHASES = ['提交方案', '裁判梳理', '辩论', '人工确认']
const ROUND_PHASE_MAP: Record<string, number> = {
  SOLUTION: 0, JUDGE: 1, DEBATE: 2, HUMAN_REVIEW: 3, DONE: 3,
}

export default function ProgressBar({ status, currentRound, roundPhase }: Props) {
  const activeMain = status === 'STANCE' ? 0 : status === 'ROUND' ? 1 : 2

  return (
    <div style={{ marginBottom: 20 }}>
      {/* 主进度 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {PHASES.map((p, i) => {
          const done = i < activeMain
          const active = i === activeMain
          return (
            <span key={p} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 14px', borderRadius: 'var(--radius-xl)',
                fontSize: 13, fontWeight: 500,
                background: active ? 'var(--color-primary)' : done ? 'var(--color-success)' : 'var(--color-surface-2)',
                color: active || done ? '#fff' : 'var(--color-text-subtle)',
                border: `1px solid ${active ? 'var(--color-primary)' : done ? 'var(--color-success)' : 'var(--color-border)'}`,
                transition: 'all var(--transition-normal)',
              }}>
                {done && '✓ '}
                {i === 1 && status === 'ROUND' ? `第${currentRound}轮` : p}
              </span>
              {i < PHASES.length - 1 && (
                <span style={{ width: 20, height: 1, background: done ? 'var(--color-success)' : 'var(--color-border)', display: 'block' }} />
              )}
            </span>
          )
        })}
      </div>

      {/* 轮次子进度 */}
      {status === 'ROUND' && roundPhase && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 10, paddingLeft: 4 }}>
          {ROUND_PHASES.map((p, i) => {
            const active = ROUND_PHASE_MAP[roundPhase] ?? -1
            const done = i < active
            const isCurrent = i === active
            return (
              <span key={p} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{
                  padding: '2px 10px', borderRadius: 'var(--radius-xl)',
                  fontSize: 12, fontWeight: 500,
                  background: isCurrent ? 'var(--color-info)' : done ? 'var(--color-info-bg)' : 'var(--color-surface-2)',
                  color: isCurrent ? '#fff' : done ? 'var(--color-info)' : 'var(--color-text-subtle)',
                  border: `1px solid ${isCurrent ? 'var(--color-info)' : done ? 'var(--color-info)' : 'var(--color-border)'}`,
                }}>
                  {done && '✓ '}{p}
                </span>
                {i < ROUND_PHASES.length - 1 && (
                  <span style={{ width: 12, height: 1, background: done ? 'var(--color-info)' : 'var(--color-border)', display: 'block' }} />
                )}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}
