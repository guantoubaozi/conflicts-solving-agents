import { useEffect, useState } from 'react'
import { Save, CheckCircle, Eye, EyeOff } from 'lucide-react'
import { api } from '../api'

export default function ConfigPage() {
  const [url, setUrl] = useState('')
  const [key, setKey] = useState('')
  const [modelName, setModelName] = useState('deepseek-chat')
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getConfig().then(c => {
      setUrl(c.api_url || '')
      setKey(c.api_key_masked || '')
      setModelName((c as any).model_name || 'deepseek-chat')
    }).catch(() => {})
  }, [])

  async function save() {
    setError(''); setSaved(false)
    try {
      const keyToSend = key.includes('*') ? '' : key
      await api.putConfig(url, keyToSend, modelName)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setError(e.message) }
  }

  return (
    <div style={{ maxWidth: 520 }}>
      <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 22, fontWeight: 700, margin: '0 0 24px' }}>
        系统配置
      </h2>

      <div style={card}>
        <Field label="AI 模型 URL">
          <input value={url} onChange={e => setUrl(e.target.value)} style={inputStyle}
            placeholder="https://api.openai.com/v1" />
        </Field>

        <Field label="模型名称">
          <input value={modelName} onChange={e => setModelName(e.target.value)}
            placeholder="如 deepseek-chat / gpt-4o" style={inputStyle} />
        </Field>

        <Field label="API Key">
          <div style={{ position: 'relative' }}>
            <input type={showKey ? 'text' : 'password'} value={key}
              onChange={e => setKey(e.target.value)}
              style={{ ...inputStyle, paddingRight: 40 }} />
            <button onClick={() => setShowKey(!showKey)}
              style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--color-text-subtle)', padding: 4 }}>
              {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          {key && key.includes('*') && (
            <div style={{ fontSize: 12, color: 'var(--color-text-subtle)', marginTop: 4 }}>
              当前已保存（已脱敏显示）
            </div>
          )}
        </Field>

        {error && <div style={{ padding: '10px 14px', background: 'var(--color-danger-bg)', color: 'var(--color-danger)', borderRadius: 'var(--radius-md)', fontSize: 13, marginBottom: 12 }}>{error}</div>}
        {saved && <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 14px', background: 'var(--color-success-bg)', color: 'var(--color-success)', borderRadius: 'var(--radius-md)', fontSize: 13, marginBottom: 12 }}><CheckCircle size={14} /> 保存成功</div>}

        <button onClick={save} style={btnPrimary}><Save size={16} /> 保存配置</button>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--color-text)', marginBottom: 6 }}>{label}</label>
      {children}
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
const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 12px', fontSize: 14,
  border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
  background: 'var(--color-surface-2)', outline: 'none', fontFamily: 'var(--font-body)',
}
