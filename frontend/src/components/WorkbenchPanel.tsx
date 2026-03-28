import { useRef, useState } from 'react'
import { parseQuestionnaire, answerAll, getAnswers, patchAnswer, exportUrl } from '../api'

interface Citation {
  source: string
  page: number
  excerpt: string
}

interface QItem {
  question_id: string
  seq: number
  question: string
  answer_id: string
  draft: string | null
  human_edit: string | null
  citations: Citation[] | null
  confidence: number | null
  needs_review: boolean
  status: string
}

interface Props {
  onQidChange: (id: string) => void
  activeQid: string | null
}

function badge(item: QItem): { label: string; color: string } {
  if (item.status === 'approved') return { label: '✓ Approved', color: '#dcfce7' }
  if (item.needs_review) return { label: '⚠ Review', color: '#fef9c3' }
  if (item.status === 'done') return { label: '• Generated', color: '#e0e7ff' }
  return { label: '⏳ Pending', color: '#f1f5f9' }
}

export default function WorkbenchPanel({ onQidChange, activeQid }: Props) {
  const [items, setItems] = useState<QItem[]>([])
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const ref = useRef<HTMLInputElement>(null)

  const loadAnswers = async (qid: string) => {
    const r = await getAnswers(qid)
    setItems(r.data)
  }

  const handleParse = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    try {
      const r = await parseQuestionnaire(file)
      const qid: string = r.data.id
      onQidChange(qid)
      await loadAnswers(qid)
    } finally {
      setLoading(false)
      if (ref.current) ref.current.value = ''
    }
  }

  const handleAnswerAll = async () => {
    if (!activeQid) return
    setRunning(true)
    try {
      await answerAll(activeQid)
      await loadAnswers(activeQid)
    } finally {
      setRunning(false)
    }
  }

  const handleEdit = async (item: QItem, val: string) => {
    await patchAnswer(item.answer_id, { human_edit: val })
    setItems((prev) =>
      prev.map((x) =>
        x.answer_id === item.answer_id ? { ...x, human_edit: val, status: 'approved' } : x
      )
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <input
          ref={ref}
          type="file"
          accept=".xlsx,.txt"
          style={{ display: 'none' }}
          onChange={handleParse}
        />
        <button
          onClick={() => ref.current?.click()}
          disabled={loading}
          style={{ padding: '8px 16px', borderRadius: 6, cursor: 'pointer' }}
        >
          {loading ? 'Parsing…' : 'Upload Questionnaire'}
        </button>

        {activeQid && (
          <>
            <button
              onClick={handleAnswerAll}
              disabled={running}
              style={{
                padding: '8px 16px',
                background: running ? '#93c5fd' : '#3b82f6',
                color: '#fff',
                border: 'none',
                borderRadius: 6,
                cursor: running ? 'not-allowed' : 'pointer',
              }}
            >
              {running ? 'Answering…' : '⚡ Auto-Answer All'}
            </button>
            <a
              href={exportUrl(activeQid)}
              download
              style={{
                padding: '8px 16px',
                background: '#10b981',
                color: '#fff',
                borderRadius: 6,
                textDecoration: 'none',
                fontSize: 14,
              }}
            >
              ↓ Export Excel
            </a>
          </>
        )}
      </div>

      {items.length === 0 && !loading && (
        <div style={{ color: '#94a3b8', fontSize: 13, textAlign: 'center', marginTop: 40 }}>
          Upload a questionnaire (.xlsx or .txt) to get started
        </div>
      )}

      {items.map((item) => {
        const b = badge(item)
        const displayAnswer = item.human_edit ?? item.draft ?? ''
        return (
          <div
            key={item.answer_id}
            style={{
              marginBottom: 16,
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              overflow: 'hidden',
              background: '#fff',
            }}
          >
            <div
              style={{
                background: '#f8fafc',
                padding: '10px 14px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                gap: 8,
              }}
            >
              <span style={{ fontWeight: 600, fontSize: 13, color: '#1e293b', flex: 1 }}>
                {item.seq + 1}. {item.question}
              </span>
              <span
                style={{
                  background: b.color,
                  padding: '2px 8px',
                  borderRadius: 12,
                  fontSize: 11,
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                }}
              >
                {b.label}
              </span>
            </div>
            <div style={{ padding: 12 }}>
              <textarea
                defaultValue={displayAnswer}
                onBlur={(e) => handleEdit(item, e.target.value)}
                rows={3}
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  border: '1px solid #e2e8f0',
                  borderRadius: 6,
                  padding: 8,
                  fontSize: 13,
                  resize: 'vertical',
                  fontFamily: 'inherit',
                }}
                placeholder={item.status === 'pending' ? 'Click "Auto-Answer All" to generate…' : ''}
              />
              {item.citations && item.citations.length > 0 && (
                <details style={{ marginTop: 6, fontSize: 12, color: '#64748b' }}>
                  <summary style={{ cursor: 'pointer', userSelect: 'none' }}>
                    📎 {item.citations.length} source(s) — confidence{' '}
                    {Math.round((item.confidence ?? 0) * 100)}%
                  </summary>
                  {item.citations.map((c, i) => (
                    <div
                      key={i}
                      style={{
                        marginTop: 6,
                        padding: '6px 10px',
                        background: '#f1f5f9',
                        borderRadius: 4,
                        fontSize: 12,
                      }}
                    >
                      <strong style={{ color: '#475569' }}>
                        {c.source} p.{c.page}
                      </strong>
                      <div style={{ marginTop: 2, color: '#64748b' }}>{c.excerpt}</div>
                    </div>
                  ))}
                </details>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
