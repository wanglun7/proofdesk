import { useState } from 'react'
import KBPanel from './components/KBPanel'
import WorkbenchPanel from './components/WorkbenchPanel'

export default function App() {
  const [activeQid, setActiveQid] = useState<string | null>(null)

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'system-ui', background: '#f8fafc' }}>
      <div
        style={{
          width: 300,
          borderRight: '1px solid #e2e8f0',
          padding: 20,
          overflowY: 'auto',
          background: '#fff',
        }}
      >
        <h2 style={{ margin: '0 0 16px', fontSize: 16, color: '#1e293b' }}>Knowledge Base</h2>
        <KBPanel />
      </div>
      <div style={{ flex: 1, padding: 20, overflowY: 'auto' }}>
        <h2 style={{ margin: '0 0 16px', fontSize: 16, color: '#1e293b' }}>
          Questionnaire Workbench
        </h2>
        <WorkbenchPanel onQidChange={setActiveQid} activeQid={activeQid} />
      </div>
    </div>
  )
}
