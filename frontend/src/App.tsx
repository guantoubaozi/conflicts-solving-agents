import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { MessageSquare, Settings } from 'lucide-react'
import ConfigPage from './pages/ConfigPage'
import DebateListPage from './pages/DebateListPage'
import DebateDetailPage from './pages/DebateDetailPage'
import StancePage from './pages/StancePage'
import DebateRoundPage from './pages/DebateRoundPage'
import HumanReviewPage from './pages/HumanReviewPage'
import FinalPage from './pages/FinalPage'

function NavBar() {
  const loc = useLocation()
  const isActive = (path: string) => loc.pathname === path

  const linkStyle = (path: string): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '6px 14px', borderRadius: 'var(--radius-md)',
    fontSize: 14, fontWeight: 500,
    color: isActive(path) ? 'var(--color-primary)' : 'var(--color-text-muted)',
    background: isActive(path) ? 'var(--color-primary-light)' : 'transparent',
    transition: 'background var(--transition-fast), color var(--transition-fast)',
  })

  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 50,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 24px', height: 56,
      background: 'var(--color-surface)',
      borderBottom: '1px solid var(--color-border)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
        <Link to="/" style={{
          fontFamily: 'var(--font-heading)', fontSize: 18, fontWeight: 700,
          color: 'var(--color-text)', letterSpacing: '-0.02em',
        }}>
          争端解决仪
        </Link>
        <Link to="/" style={linkStyle('/')}>
          <MessageSquare size={16} /> 议题列表
        </Link>
      </div>
      <Link to="/config" style={linkStyle('/config')}>
        <Settings size={16} /> 配置
      </Link>
    </nav>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <main style={{ maxWidth: 960, margin: '0 auto', padding: '32px 24px' }}>
        <Routes>
          <Route path="/" element={<DebateListPage />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="/debates/:debateId" element={<DebateDetailPage />} />
          <Route path="/debates/:debateId/stance/:partyId" element={<StancePage />} />
          <Route path="/debates/:debateId/rounds/:round" element={<DebateRoundPage />} />
          <Route path="/debates/:debateId/rounds/:round/review" element={<HumanReviewPage />} />
          <Route path="/debates/:debateId/final" element={<FinalPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
