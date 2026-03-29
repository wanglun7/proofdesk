import { useRef, useState, useEffect } from 'react'
import { Upload, Zap, Check, Download, RotateCcw, Flag, BookOpen, Paperclip, Library } from 'lucide-react'
import { parseQuestionnaire, getAnswers, patchAnswer, approveAll, exportFilledUrl, answerAllStreamUrl, regenerateStreamUrl, saveToLibrary } from '../api'
import { markAnsweringItemsAsErrored, reduceAnswerAllEvent } from '../lib/workbenchStream'

interface Citation {
  source: string
  page: number
  excerpt: string
}

function highlightTerms(text: string, question: string): string {
  const terms = question
    .split(/\s+/)
    .map(w => w.replace(/[^\w\u4e00-\u9fa5]/g, ''))
    .filter(w => w.length >= 4)
  if (terms.length === 0) return text
  const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const re = new RegExp(`(${escaped.join('|')})`, 'gi')
  return text.replace(re, '<mark style="background:#fef9c3;padding:0 1px;border-radius:2px">$1</mark>')
}

function CitationList({ citations, question }: { citations: Citation[]; question: string }) {
  const [open, setOpen] = useState<number | null>(null)
  if (!citations || citations.length === 0) return null

  const active = open !== null ? citations[open] : null

  return (
    <div className="mt-2">
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c, i) => (
          <button
            key={i}
            onClick={() => setOpen(open === i ? null : i)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] rounded-full border transition-colors ${
              open === i
                ? 'bg-blue-50 border-blue-200 text-blue-700'
                : 'bg-slate-50 border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-700'
            }`}
          >
            <Paperclip size={10} />
            {c.source} p.{c.page}
          </button>
        ))}
      </div>
      {active && (
        <div className="mt-2 p-3 bg-amber-50 border border-amber-200 rounded-md">
          <div className="text-[11px] font-semibold text-slate-500 mb-1.5">
            {active.source} · page {active.page}
          </div>
          <div
            className="text-xs text-slate-700 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: highlightTerms(active.excerpt, question) }}
          />
        </div>
      )}
    </div>
  )
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
  flag_reason: string | null
  from_library?: boolean
}

interface Props {
  onQidChange: (id: string, filename: string, questionCount: number) => void
  activeQid: string | null
  activeProjectId: string | null
  docCount: number
  showAlert: (title: string, message: string) => Promise<void>
  onLibrarySave?: () => void
}

function StatusBadge({ item }: { item: QItem }) {
  if (item.from_library) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] bg-violet-100 text-violet-700 font-medium whitespace-nowrap">
      <Library size={10} />
      From Library
    </span>
  )
  if (item.status === 'approved') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] bg-emerald-100 text-emerald-700 font-medium whitespace-nowrap">
      <Check size={10} />
      Approved
    </span>
  )
  if (item.status === 'flagged') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] bg-red-100 text-red-600 font-medium whitespace-nowrap">
      <Flag size={10} />
      Flagged
    </span>
  )
  if (item.status === 'error') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] bg-red-100 text-red-600 font-medium whitespace-nowrap">
      <Flag size={10} />
      Error
    </span>
  )
  if (item.status === 'pending') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-500 font-medium whitespace-nowrap">
      Pending
    </span>
  )
  if (item.status === 'answering') return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] bg-blue-100 text-blue-600 font-medium whitespace-nowrap">
      <span className="kb-spinner" />
      Answering…
    </span>
  )
  // done
  const conf = item.confidence ?? 0
  if (conf >= 0.75) return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] bg-emerald-50 text-emerald-700 font-medium whitespace-nowrap">
      {Math.round(conf * 100)}% confident
    </span>
  )
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] bg-amber-100 text-amber-700 font-medium whitespace-nowrap">
      Review — {Math.round(conf * 100)}%
    </span>
  )
}

function ActionBar({ item, onApprove, onFlag, onUnflag }: {
  item: QItem
  onApprove: (item: QItem) => void
  onFlag: (item: QItem, reason: string) => void
  onUnflag: (item: QItem) => void
}) {
  const [flagging, setFlagging] = useState(false)
  const [reason, setReason] = useState('')

  if (item.status === 'flagged') {
    return (
      <div className="flex gap-2 mt-3 justify-end">
        <button
          onClick={() => onUnflag(item)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-red-200 rounded-md text-red-600 hover:bg-red-50 transition-colors"
        >
          Unflag
        </button>
        <button
          onClick={() => onApprove(item)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-600 text-white rounded-md hover:bg-emerald-700 font-medium transition-colors"
        >
          <Check size={12} />
          Approve anyway
        </button>
      </div>
    )
  }

  if (flagging) {
    return (
      <div className="flex gap-2 mt-3 items-center">
        <input
          autoFocus
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Reason for flagging…"
          onKeyDown={e => {
            if (e.key === 'Enter' && reason.trim()) { onFlag(item, reason.trim()); setFlagging(false); setReason('') }
            if (e.key === 'Escape') { setFlagging(false); setReason('') }
          }}
          className="flex-1 px-2.5 py-1.5 text-xs border border-red-200 rounded-md outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-400"
        />
        <button
          disabled={!reason.trim()}
          onClick={() => { onFlag(item, reason.trim()); setFlagging(false); setReason('') }}
          className={`px-3 py-1.5 text-xs rounded-md text-white font-medium transition-colors ${reason.trim() ? 'bg-red-500 hover:bg-red-600' : 'bg-red-200 cursor-not-allowed'}`}
        >
          Flag
        </button>
        <button
          onClick={() => { setFlagging(false); setReason('') }}
          className="px-3 py-1.5 text-xs border border-slate-200 rounded-md text-slate-500 hover:bg-slate-50 transition-colors"
        >
          Cancel
        </button>
      </div>
    )
  }

  return (
    <div className="flex gap-2 mt-3 justify-end">
      <button
        onClick={() => setFlagging(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
      >
        <Flag size={12} />
        Flag
      </button>
      <button
        onClick={() => onApprove(item)}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-600 text-white rounded-md hover:bg-emerald-700 font-medium transition-colors"
      >
        <Check size={12} />
        Approve
      </button>
    </div>
  )
}

export default function WorkbenchPanel({ onQidChange, activeQid, activeProjectId, docCount, showAlert, onLibrarySave }: Props) {
  const [items, setItems] = useState<QItem[]>([])
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null)
  const [filter, setFilter] = useState<'all' | 'flagged' | 'review' | 'approved'>('all')
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())
  const [streamAlert, setStreamAlert] = useState<string | null>(null)
  const ref = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setItems([])
    setFilter('all')
  }, [activeProjectId])

  useEffect(() => {
    if (activeQid) loadAnswers(activeQid)
    else setItems([])
  }, [activeQid])

  const loadAnswers = async (qid: string) => {
    const r = await getAnswers(qid)
    setItems(r.data)
  }

  const handleParse = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!activeProjectId) {
      await showAlert('No Project Selected', 'Select or create a project first.')
      return
    }
    setLoading(true)
    try {
      const r = await parseQuestionnaire(file, activeProjectId)
      const qid: string = r.data.id
      onQidChange(qid, file.name, r.data.questions.length)
      await loadAnswers(qid)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      await showAlert('Upload Failed', `Upload failed: ${msg}`)
    } finally {
      setLoading(false)
      if (ref.current) ref.current.value = ''
    }
  }

  const handleAnswerAll = async () => {
    if (!activeQid || running) return
    if (docCount === 0) {
      await showAlert('No Documents', 'This project has no documents in the Knowledge Base. Upload documents first so the AI has content to answer from.')
      return
    }
    setRunning(true)
    setProgress({ current: 0, total: 0 })
    setStreamAlert(null)

    const es = new EventSource(answerAllStreamUrl(activeQid))

    es.onmessage = (event) => {
      const data = JSON.parse(event.data)
      let nextProgress: { current: number; total: number } | null | undefined
      let finished = false
      let alertMessage: string | null = null

      setItems((prev) => {
        const result = reduceAnswerAllEvent(prev, data)
        nextProgress = result.progress
        finished = result.finished
        alertMessage = result.alertMessage
        return result.items
      })

      if (nextProgress !== undefined) setProgress(nextProgress)
      if (alertMessage) setStreamAlert(alertMessage)
      if (finished) {
        es.close()
        setRunning(false)
        setProgress(null)
      }
    }

    es.onerror = () => {
      es.close()
      setItems((prev) => markAnsweringItemsAsErrored(prev, 'Connection lost during auto-answer.'))
      setStreamAlert('Auto-answer connection was interrupted. Retry the failed questions with Regen.')
      setRunning(false)
      setProgress(null)
    }
  }

  const handleApproveAll = async () => {
    if (!activeQid) return
    await approveAll(activeQid)
    setItems((prev) => prev.map((x) => (x.status === 'done' ? { ...x, status: 'approved' } : x)))
  }

  const handleEdit = async (item: QItem, val: string) => {
    await patchAnswer(item.answer_id, { human_edit: val })
    setItems((prev) =>
      prev.map((x) => x.answer_id === item.answer_id ? { ...x, human_edit: val } : x)
    )
  }

  const handleApprove = async (item: QItem) => {
    await patchAnswer(item.answer_id, { status: 'approved' })
    setItems((prev) =>
      prev.map((x) => x.answer_id === item.answer_id ? { ...x, status: 'approved' } : x)
    )
  }

  const handleFlag = async (item: QItem, reason: string) => {
    await patchAnswer(item.answer_id, { status: 'flagged', flag_reason: reason })
    setItems((prev) =>
      prev.map((x) => x.answer_id === item.answer_id ? { ...x, status: 'flagged', flag_reason: reason } : x)
    )
  }

  const handleUnflag = async (item: QItem) => {
    await patchAnswer(item.answer_id, { status: 'done' })
    setItems((prev) =>
      prev.map((x) => x.answer_id === item.answer_id ? { ...x, status: 'done', flag_reason: null } : x)
    )
  }

  const handleRevoke = async (item: QItem) => {
    await patchAnswer(item.answer_id, { status: 'done' })
    setItems((prev) =>
      prev.map((x) => x.answer_id === item.answer_id ? { ...x, status: 'done' } : x)
    )
  }

  const handleRegenerate = (item: QItem) => {
    setStreamAlert(null)
    setItems((prev) => prev.map((x) => x.answer_id === item.answer_id ? { ...x, status: 'answering' } : x))
    const es = new EventSource(regenerateStreamUrl(item.question_id))
    es.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'answer') {
        setItems((prev) => prev.map((x) =>
          x.answer_id === item.answer_id
            ? { ...x, draft: data.draft, human_edit: null, citations: data.citations, confidence: data.confidence, needs_review: data.needs_review, status: data.status, from_library: data.from_library ?? false }
            : x
        ))
      } else if (data.type === 'error') {
        setItems((prev) => prev.map((x) =>
          x.answer_id === item.answer_id
            ? { ...x, status: 'error', flag_reason: data.error }
            : x
        ))
        setStreamAlert(`Question ${item.seq + 1} failed: ${data.error}`)
        es.close()
      } else if (data.type === 'done') {
        es.close()
      }
    }
    es.onerror = () => {
      es.close()
      setItems((prev) => prev.map((x) =>
        x.answer_id === item.answer_id
          ? { ...x, status: 'error', flag_reason: 'Connection lost during regenerate.' }
          : x
      ))
      setStreamAlert(`Question ${item.seq + 1} failed: connection lost during regenerate.`)
    }
  }

  const handleSaveToLibrary = async (item: QItem) => {
    if (!activeQid) return
    const answerText = item.human_edit || item.draft || ''
    await saveToLibrary(item.question, answerText, activeQid)
    setSavedIds((prev) => new Set([...prev, item.answer_id]))
    onLibrarySave?.()
  }

  const doneCount = items.filter((x) => x.status === 'done').length
  const flaggedCount = items.filter((x) => x.status === 'flagged').length
  const reviewCount = items.filter((x) => x.needs_review && x.status === 'done').length
  const approvedCount = items.filter((x) => x.status === 'approved').length
  const allApproved = items.length > 0 && items.every(x => x.status === 'approved')

  const visible = items.filter((x) => {
    if (filter === 'flagged') return x.status === 'flagged'
    if (filter === 'review') return x.needs_review && x.status === 'done'
    if (filter === 'approved') return x.status === 'approved'
    return true
  })

  return (
    <div>
      {/* Toolbar */}
      <div className="flex gap-2 mb-5 flex-wrap items-center">
        <input
          ref={ref}
          type="file"
          accept=".xlsx,.txt"
          className="hidden"
          onChange={handleParse}
        />
        <button
          onClick={() => { if (activeProjectId) ref.current?.click() }}
          disabled={!activeProjectId || loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-slate-200 rounded-md bg-white text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          title={!activeProjectId ? 'Select a project first' : ''}
        >
          <Upload size={14} />
          {loading ? 'Parsing…' : 'Upload Questionnaire'}
        </button>

        {activeQid && (
          <>
            <button
              onClick={handleAnswerAll}
              disabled={running}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-brand-600 text-white rounded-md hover:bg-brand-700 font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <Zap size={14} />
              {running
                ? progress
                  ? `Answering ${progress.current}/${progress.total}…`
                  : 'Answering…'
                : 'Auto-Answer All'}
            </button>

            {doneCount > 0 && (
              <button
                onClick={handleApproveAll}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-emerald-600 text-white rounded-md hover:bg-emerald-700 font-medium transition-colors"
              >
                <Check size={14} />
                Approve All ({doneCount})
              </button>
            )}

            {items.length > 0 && (
              allApproved ? (
                <a
                  href={exportFilledUrl(activeQid)}
                  download
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-cyan-600 text-white rounded-md hover:bg-cyan-700 transition-colors ml-auto"
                >
                  <Download size={14} />
                  Export Questionnaire
                </a>
              ) : (
                <span
                  title={`${approvedCount}/${items.length} approved — approve all to export`}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-100 text-slate-400 rounded-md cursor-not-allowed ml-auto"
                >
                  <Download size={14} />
                  Export Questionnaire ({approvedCount}/{items.length})
                </span>
              )
            )}
          </>
        )}
      </div>

      {streamAlert && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {streamAlert}
        </div>
      )}

      {/* Filter tabs */}
      {items.length > 0 && (
        <div className="flex border-b border-slate-200 mb-5 gap-0">
          {(
            [
              { key: 'all', label: `All`, count: items.length },
              { key: 'flagged', label: 'Flagged', count: flaggedCount },
              { key: 'review', label: 'Needs Review', count: reviewCount },
              { key: 'approved', label: 'Approved', count: approvedCount },
            ] as const
          ).map(({ key, label, count }) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
                filter === key
                  ? 'border-brand-600 text-brand-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
              }`}
            >
              {label}
              {count > 0 && (
                <span className={`ml-1.5 px-1.5 py-0.5 rounded text-[10px] ${
                  filter === key ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-500'
                }`}>
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {items.length === 0 && !loading && (
        <div className="text-slate-400 text-sm text-center mt-16">
          {activeProjectId
            ? 'Upload a questionnaire (.xlsx or .txt) to get started'
            : 'Create or select a project to get started'}
        </div>
      )}

      <div className="space-y-3">
        {visible.map((item) => {
          const displayAnswer = item.human_edit || item.draft || ''
          const isAnswering = item.status === 'answering'
          const isErrored = item.status === 'error'
          const isFlagged = item.status === 'flagged'
          const isApproved = item.status === 'approved'
          const isDone = item.status === 'done'
          const canAct = isDone || isFlagged
          const canRegenerate = isDone || isFlagged || isErrored
          const isLocked = isApproved || isAnswering

          // Left status bar color
          const barColor = isFlagged
            ? 'bg-red-400'
            : isErrored
              ? 'bg-red-400'
            : isApproved
              ? 'bg-emerald-400'
              : item.needs_review && isDone
                ? 'bg-amber-400'
                : isAnswering
                  ? 'bg-blue-400'
                  : 'bg-slate-200'

          return (
            <div
              key={item.answer_id}
              className={`flex rounded-lg bg-white shadow-sm border border-slate-200 overflow-hidden transition-opacity ${isAnswering ? 'opacity-70' : 'opacity-100'}`}
            >
              {/* Left status bar */}
              <div className={`w-1 shrink-0 ${barColor}`} />

              {/* Card content */}
              <div className="flex-1 p-4 min-w-0">
                {/* Card header */}
                <div className="flex justify-between items-start gap-3 mb-3">
                  <div className="flex items-start gap-2.5 min-w-0 flex-1">
                    <span className="shrink-0 min-w-[22px] h-[22px] flex items-center justify-center bg-slate-100 text-slate-600 rounded text-[11px] font-semibold mt-0.5">
                      {item.seq + 1}
                    </span>
                    <span className="text-[13px] font-medium text-slate-800 leading-snug">
                      {item.question}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {isApproved && (
                      <>
                        <button
                          onClick={() => handleSaveToLibrary(item)}
                          disabled={savedIds.has(item.answer_id)}
                          className={`flex items-center gap-1 px-2 py-0.5 text-[11px] border rounded transition-colors ${
                            savedIds.has(item.answer_id)
                              ? 'bg-violet-50 border-violet-200 text-violet-600 cursor-default'
                              : 'bg-white border-violet-200 text-violet-500 hover:bg-violet-50 hover:text-violet-700'
                          }`}
                        >
                          <BookOpen size={10} />
                          {savedIds.has(item.answer_id) ? 'Saved' : 'Save'}
                        </button>
                        <button
                          onClick={() => handleRevoke(item)}
                          className="px-2 py-0.5 text-[11px] border border-slate-200 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors"
                        >
                          Revoke
                        </button>
                      </>
                    )}
                    {canRegenerate && (
                      <button
                        onClick={() => handleRegenerate(item)}
                        className="flex items-center gap-1 px-2 py-0.5 text-[11px] border border-slate-200 rounded text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition-colors"
                      >
                        <RotateCcw size={10} />
                        Regen
                      </button>
                    )}
                    <StatusBadge item={item} />
                  </div>
                </div>

                {/* Answer textarea */}
                <textarea
                  key={`${item.answer_id}-${item.status}`}
                  defaultValue={displayAnswer}
                  disabled={isLocked}
                  onBlur={(e) => {
                    if (isLocked) return
                    const val = e.target.value
                    if (val === displayAnswer || (!val && displayAnswer)) return
                    handleEdit(item, val)
                  }}
                  rows={3}
                  className={`w-full text-[13px] rounded-md px-3 py-2 border-0 outline-none resize-y leading-relaxed transition-colors ${
                    isApproved
                      ? 'bg-emerald-50 text-slate-700 resize-none cursor-default'
                      : isAnswering
                        ? 'bg-slate-50 text-slate-500 resize-none cursor-default'
                        : 'bg-slate-50 text-slate-800 focus:bg-white focus:ring-2 focus:ring-brand-600/20'
                  }`}
                  placeholder={
                    isAnswering ? 'Generating answer…'
                      : isErrored ? 'Answer generation failed. Click "Regen" to retry.'
                      : item.status === 'pending' ? 'Click "Auto-Answer All" to generate…' : ''
                  }
                />

                {/* Flag reason */}
                {(isFlagged || isErrored) && item.flag_reason && (
                  <div className="mt-2 px-3 py-2 bg-red-50 border border-red-100 rounded-md text-xs text-red-600">
                    <span className="font-semibold">{isErrored ? 'Error:' : 'Flag reason:'}</span> {item.flag_reason}
                  </div>
                )}

                {/* Citations */}
                {item.citations && item.citations.length > 0 && (
                  <CitationList citations={item.citations} question={item.question} />
                )}

                {/* Action bar */}
                {canAct && (
                  <ActionBar item={item} onApprove={handleApprove} onFlag={handleFlag} onUnflag={handleUnflag} />
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
