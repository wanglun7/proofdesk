import { useState, useEffect } from 'react'
import { BookOpen, Trash2 } from 'lucide-react'
import { listLibrary, deleteLibraryEntry } from '../api'

interface LibraryEntry {
  id: string
  question_text: string
  answer_text: string
  created_at: string
}

interface Props {
  showConfirm: (title: string, message: string) => Promise<boolean>
  refreshKey?: number
}

export default function LibraryPanel({ showConfirm, refreshKey }: Props) {
  const [entries, setEntries] = useState<LibraryEntry[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const r = await listLibrary()
      setEntries(r.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [refreshKey])

  const handleDelete = async (id: string) => {
    const ok = await showConfirm('Remove from Library', 'Remove this entry from the answer library?')
    if (!ok) return
    await deleteLibraryEntry(id)
    setEntries((prev) => prev.filter((e) => e.id !== id))
  }

  if (loading) return (
    <div className="text-slate-400 text-sm text-center mt-16">Loading…</div>
  )

  if (entries.length === 0) return (
    <div className="flex flex-col items-center justify-center mt-16 text-center">
      <BookOpen size={32} className="text-slate-300 mb-3" />
      <p className="text-slate-500 text-sm font-medium">No saved answers yet</p>
      <p className="text-slate-400 text-xs mt-1 max-w-xs">
        Approve answers in the Workbench and save them to reuse across projects.
      </p>
    </div>
  )

  return (
    <div className="space-y-3">
      {entries.map((e) => (
        <div
          key={e.id}
          className="group relative bg-white border border-slate-200 rounded-lg p-4 hover:border-slate-300 transition-colors"
        >
          <div className="pr-6">
            <p className="text-[13px] font-semibold text-slate-900 leading-snug">
              {e.question_text}
            </p>
            <p className="text-[13px] text-slate-600 mt-2 leading-relaxed line-clamp-3">
              {e.answer_text}
            </p>
            <p className="text-[11px] text-slate-400 mt-2">
              {new Date(e.created_at).toLocaleDateString()}
            </p>
          </div>
          <button
            onClick={() => handleDelete(e.id)}
            title="Remove"
            className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-500 transition-all rounded"
          >
            <Trash2 size={13} />
          </button>
        </div>
      ))}
    </div>
  )
}
