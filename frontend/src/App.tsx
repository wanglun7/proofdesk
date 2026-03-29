import { useEffect, useState, useRef } from 'react'
import KBPanel from './components/KBPanel'
import WorkbenchPanel from './components/WorkbenchPanel'
import LoginPage from './components/LoginPage'
import Modal, { useModalState } from './components/Modal'
import LibraryPanel from './components/LibraryPanel'
import { createProject, listProjects, deleteProject, listDocs, listQuestionnaires, deleteQuestionnaire, setUnauthHandler } from './api'
import { FolderOpen, FileText, Database, BookOpen, Plus, Trash2, ChevronRight, LogOut, Layers } from 'lucide-react'

interface Project {
  id: string
  name: string
  created_at: string
}

interface QuestionnaireItem {
  id: string
  filename: string
  created_at: string
  question_count: number
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 mb-2 text-[11px] font-semibold tracking-widest text-slate-400 uppercase select-none">
      {children}
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(() => !!localStorage.getItem('token'))
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const { modal, showAlert, showConfirm } = useModalState()

  const [questionnaires, setQuestionnaires] = useState<QuestionnaireItem[]>([])
  const [activeQid, setActiveQid] = useState<string | null>(null)

  const [docCount, setDocCount] = useState(0)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [libraryKey, setLibraryKey] = useState(0)
  const [activeSection, setActiveSection] = useState<'workbench' | 'kb' | 'library'>('workbench')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setUnauthHandler(() => setAuthed(false))
  }, [])

  useEffect(() => {
    if (!authed) return
    const loadProjects = async () => {
      try {
        const r = await listProjects()
        setProjects(r.data)
      } catch (err: any) {
        if (err?.response?.status === 403) {
          localStorage.removeItem('token')
          setAuthed(false)
        }
      }
    }
    loadProjects()
  }, [authed])

  useEffect(() => {
    setActiveQid(null)
    setQuestionnaires([])
    if (!activeProject) { setDocCount(0); return }
    listDocs(activeProject.id).then((r) => setDocCount(r.data.length)).catch(() => {})
    listQuestionnaires(activeProject.id).then((r) => setQuestionnaires(r.data)).catch(() => {})
  }, [activeProject])

  const handleCreate = async () => {
    const name = newName.trim()
    if (!name) return
    try {
      const r = await createProject(name)
      const p = r.data
      setProjects((prev) => [p, ...prev])
      setActiveProject(p)
      setNewName('')
      setCreating(false)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      await showAlert('Create Project Failed', typeof detail === 'string' ? detail : 'Unable to create project.')
    }
  }

  const handleDeleteProject = async (p: Project, e: React.MouseEvent) => {
    e.stopPropagation()
    const ok = await showConfirm('Delete Project', `Delete project "${p.name}" and all its questionnaires?`)
    if (!ok) return
    await deleteProject(p.id)
    setProjects((prev) => prev.filter((x) => x.id !== p.id))
    if (activeProject?.id === p.id) setActiveProject(null)
  }

  const handleDeleteQuestionnaire = async (qid: string, e: React.MouseEvent) => {
    e.stopPropagation()
    const ok = await showConfirm('Delete Questionnaire', 'Delete this questionnaire and all its answers?')
    if (!ok) return
    await deleteQuestionnaire(qid)
    const updated = questionnaires.filter((x) => x.id !== qid)
    setQuestionnaires(updated)
    if (activeQid === qid) setActiveQid(null)
  }

  const handleQidChange = (qid: string, filename: string, questionCount: number) => {
    setActiveQid(qid)
    setQuestionnaires((prev) => {
      const exists = prev.find((q) => q.id === qid)
      if (exists) return prev
      return [{ id: qid, filename, created_at: new Date().toISOString(), question_count: questionCount }, ...prev]
    })
  }

  const activeQItem = questionnaires.find((q) => q.id === activeQid)

  const handleSignOut = () => {
    localStorage.removeItem('token')
    setAuthed(false)
  }

  if (!authed) return <LoginPage onLogin={() => setAuthed(true)} />

  return (
    <div className="flex flex-col w-full h-screen bg-slate-50 overflow-hidden">
      <Modal modal={modal} />

      {/* ── Top Header ── */}
      <header className="flex items-center justify-between px-4 h-13 bg-white border-b border-slate-200 shrink-0" style={{ height: 52 }}>
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-7 h-7 bg-brand-600 rounded-md">
            <Layers size={15} className="text-white" />
          </div>
          <span className="font-semibold text-slate-900 text-[15px] tracking-tight">Proofdesk</span>
        </div>
        <button
          onClick={handleSignOut}
          className="flex items-center gap-1.5 text-slate-400 hover:text-slate-600 text-xs transition-colors px-2 py-1 rounded hover:bg-slate-100"
        >
          <LogOut size={13} />
          Sign out
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Sidebar ── */}
        <aside className="w-60 border-r border-slate-200 bg-white flex flex-col shrink-0 overflow-hidden">

          {/* Projects */}
          <div className="px-3 pt-4 pb-3 border-b border-slate-100 shrink-0">
            <div className="flex items-center justify-between mb-2">
              <SectionLabel>Projects</SectionLabel>
              <button
                onClick={() => { setCreating(true); setTimeout(() => inputRef.current?.focus(), 50) }}
                className="flex items-center gap-1 text-slate-500 hover:text-brand-600 hover:bg-brand-50 px-1.5 py-0.5 rounded text-xs transition-colors"
                title="New project"
              >
                <Plus size={12} />
                New
              </button>
            </div>

            {creating && (
              <div className="flex gap-1.5 mb-2">
                <input
                  ref={inputRef}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setCreating(false) }}
                  placeholder="Project name…"
                  className="flex-1 px-2.5 py-1.5 text-xs border border-brand-300 rounded-md outline-none focus:ring-2 focus:ring-brand-600/20 focus:border-brand-500 bg-white"
                />
                <button onClick={handleCreate} className="px-2.5 py-1.5 bg-brand-600 text-white rounded-md text-xs font-medium hover:bg-brand-700 transition-colors">✓</button>
              </div>
            )}

            <div className="max-h-36 overflow-y-auto space-y-0.5">
              {projects.map((p) => (
                <div
                  key={p.id}
                  onClick={() => setActiveProject(p)}
                  className={`group flex items-center justify-between px-2.5 py-1.5 rounded-md cursor-pointer text-[13px] transition-colors ${
                    activeProject?.id === p.id
                      ? 'bg-brand-50 text-brand-700 font-medium'
                      : 'text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <FolderOpen size={13} className={activeProject?.id === p.id ? 'text-brand-500 shrink-0' : 'text-slate-400 shrink-0'} />
                    <span className="truncate">{p.name}</span>
                  </div>
                  <button
                    onClick={(e) => handleDeleteProject(p, e)}
                    className="opacity-0 group-hover:opacity-100 p-0.5 text-slate-400 hover:text-red-500 transition-all rounded"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
              {projects.length === 0 && !creating && (
                <div className="text-slate-400 text-xs text-center py-3">No projects yet</div>
              )}
            </div>
          </div>

          {/* Questionnaires */}
          <div className="px-3 py-3 border-b border-slate-100 shrink-0">
            <SectionLabel>Questionnaires</SectionLabel>
            {!activeProject ? (
              <div className="text-slate-400 text-xs text-center py-2">Select a project first</div>
            ) : questionnaires.length === 0 ? (
              <div className="text-slate-400 text-xs text-center py-2">Upload a questionnaire →</div>
            ) : (
              <div className="max-h-40 overflow-y-auto space-y-0.5">
                {questionnaires.map((q) => (
                  <div
                    key={q.id}
                    onClick={() => { setActiveQid(q.id); setActiveSection('workbench') }}
                    className={`group flex items-start justify-between px-2.5 py-2 rounded-md cursor-pointer text-xs transition-colors gap-1.5 ${
                      activeQid === q.id
                        ? 'bg-brand-50 text-brand-700'
                        : 'text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-start gap-1.5 min-w-0 flex-1">
                      {activeQid === q.id
                        ? <ChevronRight size={12} className="text-brand-500 shrink-0 mt-0.5" />
                        : <FileText size={12} className="text-slate-400 shrink-0 mt-0.5" />
                      }
                      <div className="min-w-0">
                        <div className={`truncate ${activeQid === q.id ? 'font-medium' : ''}`}>
                          {q.filename.replace(/\.[^.]+$/, '')}
                        </div>
                        <div className="text-slate-400 text-[10px] mt-0.5">
                          {q.question_count} questions
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={(e) => handleDeleteQuestionnaire(q.id, e)}
                      className="opacity-0 group-hover:opacity-100 p-0.5 text-slate-400 hover:text-red-500 transition-all rounded shrink-0 mt-0.5"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Nav buttons: KB + Library */}
          <div className="px-3 py-3 space-y-0.5 shrink-0">
            <button
              onClick={() => setActiveSection('kb')}
              className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-[13px] transition-colors ${
                activeSection === 'kb'
                  ? 'bg-brand-50 text-brand-700 font-medium'
                  : 'text-slate-700 hover:bg-slate-50'
              }`}
            >
              <Database size={14} className={activeSection === 'kb' ? 'text-brand-500' : 'text-slate-400'} />
              Knowledge Base
              {docCount > 0 && (
                <span className="ml-auto text-[11px] text-slate-400 font-normal">{docCount}</span>
              )}
            </button>
            <button
              onClick={() => setActiveSection('library')}
              className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-[13px] transition-colors ${
                activeSection === 'library'
                  ? 'bg-brand-50 text-brand-700 font-medium'
                  : 'text-slate-700 hover:bg-slate-50'
              }`}
            >
              <BookOpen size={14} className={activeSection === 'library' ? 'text-brand-500' : 'text-slate-400'} />
              Answer Library
            </button>
          </div>
        </aside>

        {/* ── Main panel ── */}
        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
          {/* Breadcrumb / title bar */}
          <div className="flex items-center gap-2 px-6 py-3.5 border-b border-slate-200 bg-white shrink-0">
            {activeSection === 'workbench' && (
              <>
                <span className="text-[15px] font-semibold text-slate-900 truncate">
                  {activeProject
                    ? activeQItem
                      ? activeProject.name
                      : activeProject.name
                    : 'Workbench'}
                </span>
                {activeQItem && (
                  <>
                    <ChevronRight size={14} className="text-slate-400 shrink-0" />
                    <span className="text-[15px] font-semibold text-slate-900 truncate">
                      {activeQItem.filename.replace(/\.[^.]+$/, '')}
                    </span>
                  </>
                )}
                {activeProject && (
                  <span className="ml-2 text-xs text-slate-400">
                    {docCount} doc{docCount !== 1 ? 's' : ''}
                    {activeQItem && ` · ${activeQItem.question_count} questions`}
                  </span>
                )}
              </>
            )}
            {activeSection === 'kb' && (
              <span className="text-[15px] font-semibold text-slate-900">Knowledge Base</span>
            )}
            {activeSection === 'library' && (
              <span className="text-[15px] font-semibold text-slate-900">Answer Library</span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            {activeSection === 'workbench' && (
              <WorkbenchPanel
                onQidChange={handleQidChange}
                activeQid={activeQid}
                activeProjectId={activeProject?.id ?? null}
                docCount={docCount}
                showAlert={showAlert}
                onLibrarySave={() => setLibraryKey(k => k + 1)}
              />
            )}
            {activeSection === 'kb' && (
              <KBPanel activeProjectId={activeProject?.id ?? null} onDocCountChange={setDocCount} showConfirm={showConfirm} />
            )}
            {activeSection === 'library' && (
              <LibraryPanel showConfirm={showConfirm} refreshKey={libraryKey} />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
