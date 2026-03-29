import { useEffect, useState, useRef } from 'react'
import { Upload, FileText, Trash2 } from 'lucide-react'
import { listDocs, deleteDoc, uploadDocStream } from '../api'

interface Doc {
  id: string
  filename: string
  uploaded_at: string
}

interface FileProgress {
  filename: string
  status: 'queued' | 'extracting' | 'chunking' | 'embedding' | 'done' | 'error'
  current?: number
  total?: number
  chunks?: number
  error?: string
}

interface Props {
  activeProjectId: string | null
  onDocCountChange?: (n: number) => void
  showConfirm: (title: string, message: string) => Promise<boolean>
}

function StatusTag({ f }: { f: FileProgress }) {
  if (f.status === 'queued') return (
    <span className="text-[11px] text-slate-400 font-medium">Queued</span>
  )
  if (f.status === 'extracting') return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-500">
      <span className="kb-spinner" />
      Extracting…
    </span>
  )
  if (f.status === 'chunking') {
    const hasProgress = f.total != null && f.total > 1
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-500">
        <span className="kb-spinner" />
        {hasProgress ? `Chunking ${f.current}/${f.total}` : 'Chunking…'}
      </span>
    )
  }
  if (f.status === 'embedding') {
    const pct = f.total ? Math.round((f.current ?? 0) / f.total * 100) : 0
    return (
      <span className="inline-flex items-center gap-2 text-[11px] text-brand-600">
        <span className="kb-spinner" />
        {f.current}/{f.total}
        <span className="inline-block w-8 h-1 bg-slate-200 rounded-full overflow-hidden">
          <span
            className="block h-full bg-brand-600 rounded-full transition-all duration-200"
            style={{ width: `${pct}%` }}
          />
        </span>
      </span>
    )
  }
  if (f.status === 'done') return (
    <span className="text-[11px] text-emerald-600 font-medium">{f.chunks} chunks</span>
  )
  if (f.status === 'error') return (
    <span className="text-[11px] text-red-500 font-medium" title={f.error}>Error</span>
  )
  return null
}

export default function KBPanel({ activeProjectId, onDocCountChange, showConfirm }: Props) {
  const [docs, setDocs] = useState<Doc[]>([])
  const [queue, setQueue] = useState<FileProgress[]>([])
  const [uploading, setUploading] = useState(false)
  const ref = useRef<HTMLInputElement>(null)

  const load = async () => {
    try {
      const r = await listDocs(activeProjectId ?? undefined)
      setDocs(r.data)
      onDocCountChange?.(r.data.length)
    } catch {
      // backend not ready yet
    }
  }

  useEffect(() => {
    load()
  }, [activeProjectId])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (!files.length || !activeProjectId) return

    setUploading(true)
    setQueue(files.map(f => ({ filename: f.name, status: 'queued' })))

    let addedCount = 0
    for (let i = 0; i < files.length; i++) {
      setQueue(prev => prev.map((x, idx) => idx === i ? { ...x, status: 'extracting' } : x))
      try {
        const resp = await uploadDocStream(files[i], activeProjectId)
        if (!resp.body) continue
        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop()!
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const data = JSON.parse(line.slice(6))
            setQueue(prev => prev.map((x, idx) => {
              if (idx !== i) return x
              if (data.type === 'extracting') return { ...x, status: 'extracting' }
              if (data.type === 'chunking') return { ...x, status: 'chunking', current: data.current, total: data.total }
              if (data.type === 'chunking_done') return x
              if (data.type === 'embedding') return { ...x, status: 'embedding', current: data.current, total: data.total }
              if (data.type === 'done') return { ...x, status: 'done', chunks: data.chunks }
              if (data.type === 'error') return { ...x, status: 'error', error: data.error }
              return x
            }))
            if (data.type === 'done') {
              addedCount++
              setDocs(prev => [{
                id: data.doc_id,
                filename: data.filename,
                uploaded_at: data.uploaded_at,
              }, ...prev])
              onDocCountChange?.(docs.length + addedCount)
            }
          }
        }
      } catch {
        setQueue(prev => prev.map((x, idx) => idx === i ? { ...x, status: 'error', error: 'Network error' } : x))
      }
    }

    setUploading(false)
    if (ref.current) ref.current.value = ''
    setTimeout(() => setQueue([]), 3000)
  }

  const handleDelete = async (id: string) => {
    const ok = await showConfirm('Delete Document', 'Delete this document and all its chunks?')
    if (!ok) return
    await deleteDoc(id)
    const updated = docs.filter((d) => d.id !== id)
    setDocs(updated)
    onDocCountChange?.(updated.length)
  }

  if (!activeProjectId) {
    return (
      <div className="text-slate-400 text-sm text-center mt-16">
        Select a project to manage its documents
      </div>
    )
  }

  const doneCount = queue.filter(f => f.status === 'done').length
  const totalCount = queue.length

  return (
    <div>
      <input
        ref={ref}
        type="file"
        multiple
        accept=".pdf,.docx,.doc,.txt,.pptx,.html,.md"
        className="hidden"
        onChange={handleUpload}
      />

      {/* Upload area */}
      {!uploading && (
        <button
          onClick={() => ref.current?.click()}
          className="w-full mb-5 flex flex-col items-center justify-center gap-2 py-8 border-2 border-dashed border-slate-200 rounded-lg text-slate-400 hover:border-brand-300 hover:text-brand-500 hover:bg-brand-50/30 transition-colors cursor-pointer"
        >
          <Upload size={20} />
          <span className="text-sm font-medium">Drag files here or click to upload</span>
          <span className="text-xs text-slate-400">PDF, DOCX, TXT, PPTX, HTML, MD</span>
        </button>
      )}

      {/* Progress area */}
      {queue.length > 0 && (
        <div className="mb-5 p-4 bg-slate-50 border border-slate-200 rounded-lg">
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs font-semibold text-slate-600">
              {uploading ? 'Uploading' : 'Done'} {doneCount}/{totalCount}
            </span>
            <span className="text-[11px] text-slate-400">
              {Math.round(doneCount / totalCount * 100)}%
            </span>
          </div>
          <div className="h-1 bg-slate-200 rounded-full mb-3 overflow-hidden">
            <div
              className="h-full bg-brand-600 rounded-full transition-all duration-300"
              style={{ width: `${Math.round(doneCount / totalCount * 100)}%` }}
            />
          </div>
          <div className="space-y-1.5">
            {queue.map((f, i) => (
              <div key={i} className="flex justify-between items-center gap-3">
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  <FileText size={12} className="text-slate-400 shrink-0" />
                  <span className="text-xs text-slate-700 truncate" title={f.filename}>
                    {f.filename}
                  </span>
                </div>
                <div className="shrink-0"><StatusTag f={f} /></div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Doc list */}
      <div className="space-y-2">
        {docs.map((d) => (
          <div
            key={d.id}
            className="group flex items-start justify-between gap-3 p-3 bg-white border border-slate-200 rounded-lg hover:border-slate-300 transition-colors"
          >
            <div className="flex items-start gap-2.5 min-w-0 flex-1">
              <FileText size={14} className="text-slate-400 shrink-0 mt-0.5" />
              <div className="min-w-0">
                <div className="text-[13px] text-slate-800 font-medium truncate" title={d.filename}>
                  {d.filename}
                </div>
                <div className="text-[11px] text-slate-400 mt-0.5">
                  {new Date(d.uploaded_at).toLocaleString()}
                </div>
              </div>
            </div>
            <button
              onClick={() => handleDelete(d.id)}
              title="Delete"
              className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-500 transition-all rounded"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
        {docs.length === 0 && queue.length === 0 && (
          <div className="text-slate-400 text-sm text-center mt-8">
            No documents yet
          </div>
        )}
      </div>
    </div>
  )
}
