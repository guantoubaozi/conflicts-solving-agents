import { useEffect, useRef, useState } from 'react'
import { Loader } from 'lucide-react'

interface Props {
  debateId: string
  onEvent?: (type: string, data: any) => void
}

export default function AiProcessing({ debateId, onEvent }: Props) {
  const [agentName, setAgentName] = useState('')
  const [thinking, setThinking] = useState('')
  const [active, setActive] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const es = new EventSource(`/api/debates/${debateId}/stream`)
    esRef.current = es
    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        onEvent?.(msg.type, msg.data)
        if (msg.type === 'agent_start') {
          setActive(true); setAgentName(msg.data?.agent || ''); setThinking('')
        } else if (msg.type === 'agent_thinking') {
          setThinking(prev => prev + (msg.data?.chunk || ''))
        } else if (msg.type === 'agent_done') {
          setActive(false)
        }
      } catch {}
    }
    return () => es.close()
  }, [debateId])

  if (!active) return null

  return (
    <div style={{
      border: '1px solid var(--color-info)',
      borderRadius: 'var(--radius-lg)',
      padding: '16px 20px',
      marginBottom: 16,
      background: 'var(--color-info-bg)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        fontWeight: 600, fontSize: 14, marginBottom: thinking ? 10 : 0,
        color: 'var(--color-info)',
      }}>
        <Loader size={16} style={{ animation: 'spin 1s linear infinite' }} />
        {agentName ? `${agentName} 正在处理...` : 'AI 正在处理...'}
      </div>
      {thinking && (
        <pre style={{
          fontSize: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap',
          maxHeight: 200, overflow: 'auto', margin: 0,
          padding: '10px 12px', background: 'var(--color-surface)',
          borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)',
          color: 'var(--color-text-muted)',
        }}>
          {thinking}
        </pre>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
