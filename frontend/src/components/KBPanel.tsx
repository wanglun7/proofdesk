import { useEffect, useState, useRef } from 'react'
import { uploadDoc, listDocs } from '../api'

interface Doc {
  id: string
  filename: string
  uploaded_at: string
}

export default function KBPanel() {
  const [docs, setDocs] = useState<Doc[]>([])
  const [uploading, setUploading] = useState(false)
  const ref = useRef<HTMLInputElement>(null)

  const load = async () => {
    try {
      const r = await listDocs()
      setDocs(r.data)
    } catch {
      // backend not ready yet
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await uploadDoc(file)
      await load()
    } finally {
      setUploading(false)
      if (ref.current) ref.current.value = ''
    }
  }

  return (
    <div>
      <input
        ref={ref}
        type="file"
        accept=".pdf,.docx,.txt"
        style={{ display: 'none' }}
        onChange={handleUpload}
      />
      <button
        onClick={() => ref.current?.click()}
        disabled={uploading}
        style={{
          width: '100%',
          padding: '8px 0',
          marginBottom: 12,
          cursor: uploading ? 'not-allowed' : 'pointer',
          background: '#3b82f6',
          color: '#fff',
          border: 'none',
          borderRadius: 6,
          fontSize: 13,
        }}
      >
        {uploading ? 'Uploading…' : '+ Upload Document'}
      </button>
      {docs.map((d) => (
        <div
          key={d.id}
          style={{
            padding: '6px 10px',
            marginBottom: 4,
            background: '#f1f5f9',
            borderRadius: 6,
            fontSize: 13,
          }}
        >
          📄 {d.filename}
          <div style={{ color: '#94a3b8', fontSize: 11, marginTop: 2 }}>
            {new Date(d.uploaded_at).toLocaleString()}
          </div>
        </div>
      ))}
      {docs.length === 0 && (
        <div style={{ color: '#94a3b8', fontSize: 13, textAlign: 'center', marginTop: 24 }}>
          No documents yet
        </div>
      )}
    </div>
  )
}
