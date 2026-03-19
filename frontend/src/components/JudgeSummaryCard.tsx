import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import MarkdownContent from './MarkdownContent'

interface Props {
  consensus: string
  contradictions: string
  combinedSolution: string
}

function parseItems(text: string): string[] {
  if (!text || text.trim() === '无') return []
  return text.split(/\n/).map(l => l.replace(/^\d+[\.\、]\s*/, '').trim()).filter(Boolean)
}

function Section({ title, defaultOpen, children }: {
  title: string; defaultOpen?: boolean; children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen ?? true)
  return (
    <div style={{ marginBottom: 12 }}>
      <div onClick={() => setOpen(!open)} style={{
        display: 'flex', alignItems: 'center', gap: 6,
        cursor: 'pointer', userSelect: 'none',
        fontWeight: 600, fontSize: 15, marginBottom: open ? 8 : 0,
        color: 'var(--color-text)',
      }}>
        <ChevronRight size={14} style={{
          transition: 'transform var(--transition-fast)',
          transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
        }} />
        {title}
      </div>
      {open && children}
    </div>
  )
}

export default function JudgeSummaryCard({ consensus, contradictions, combinedSolution }: Props) {
  const consensusItems = parseItems(consensus)
  const contradictionItems = parseItems(contradictions)

  return (
    <div style={{
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-lg)',
      padding: '20px 24px',
      background: 'var(--color-surface)',
      boxShadow: 'var(--shadow-sm)',
    }}>
      <Section title="共识" defaultOpen>
        {consensusItems.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {consensusItems.map((item, i) => (
              <div key={i} style={{
                background: 'var(--color-success-bg)',
                border: '1px solid #c6e6d0',
                borderRadius: 'var(--radius-md)',
                padding: '8px 12px', fontSize: 14, lineHeight: 1.6,
              }}>
                <span style={{ color: 'var(--color-success)', fontWeight: 600, marginRight: 6 }}>{i + 1}.</span>
                {item}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: 'var(--color-text-subtle)', fontSize: 14 }}>暂无共识</div>
        )}
      </Section>

      <Section title="矛盾" defaultOpen>
        {contradictionItems.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {contradictionItems.map((item, i) => (
              <div key={i} style={{
                background: 'var(--color-warning-bg)',
                border: '1px solid #f0dca0',
                borderRadius: 'var(--radius-md)',
                padding: '8px 12px', fontSize: 14, lineHeight: 1.6,
              }}>
                <span style={{ color: 'var(--color-warning)', fontWeight: 600, marginRight: 6 }}>{i + 1}.</span>
                {item}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: 'var(--color-success)', fontSize: 14 }}>✓ 无矛盾</div>
        )}
      </Section>

      <Section title="综合方案" defaultOpen>
        <div style={{
          background: 'var(--color-surface-2)',
          borderRadius: 'var(--radius-md)',
          padding: '12px 16px',
        }}>
          <MarkdownContent content={combinedSolution} />
        </div>
      </Section>
    </div>
  )
}
