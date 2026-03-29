import axios from 'axios'

export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api'
const api = axios.create({ baseURL: API_BASE })

// Callback invoked when a 401 is received — set by App on mount
let _onUnauth: (() => void) | null = null
export const setUnauthHandler = (fn: () => void) => { _onUnauth = fn }

// Attach token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers['Authorization'] = `Bearer ${token}`
  return config
})

// On 401, clear token and notify App via callback (no reload)
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      _onUnauth?.()
    }
    return Promise.reject(err)
  }
)

// Auth
export const login = (username: string, password: string) =>
  api.post('/auth/login', { username, password })

// Projects
export const createProject = (name: string) => api.post('/projects', { name })
export const listProjects = () => api.get('/projects')
export const deleteProject = (pid: string) => api.delete(`/projects/${pid}`)

// KB
export const uploadDoc = (file: File, projectId: string) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('project_id', projectId)
  return api.post('/kb/upload', fd)
}
export const uploadDocStream = (file: File, projectId: string): Promise<Response> => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('project_id', projectId)
  const token = localStorage.getItem('token') ?? ''
  return fetch(`${API_BASE}/kb/upload-stream`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  })
}
export const listDocs = (projectId?: string) =>
  api.get('/kb/documents', { params: projectId ? { project_id: projectId } : {} })
export const deleteDoc = (id: string) => api.delete(`/kb/documents/${id}`)

// Questionnaire
export const parseQuestionnaire = (file: File, projectId: string) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('project_id', projectId)
  return api.post('/questionnaire/parse', fd)
}

export const listQuestionnaires = (projectId: string) =>
  api.get(`/questionnaire/by-project/${projectId}`)

export const deleteQuestionnaire = (qid: string) =>
  api.delete(`/questionnaire/${qid}`)

export const getAnswers = (qid: string) => api.get(`/questionnaire/${qid}/answers`)

export const approveAll = (qid: string) => api.post(`/questionnaire/${qid}/approve-all`)

export const patchAnswer = (
  aid: string,
  data: { human_edit?: string; status?: string; flag_reason?: string }
) => api.patch(`/questionnaire/answers/${aid}`, data)

export const exportUrl = (qid: string) => {
  const token = localStorage.getItem('token') ?? ''
  return `${API_BASE}/questionnaire/${qid}/export?token=${token}`
}

export const exportFilledUrl = (qid: string) => {
  const token = localStorage.getItem('token') ?? ''
  return `${API_BASE}/questionnaire/${qid}/export-filled?token=${token}`
}

export const answerAllStreamUrl = (qid: string) => {
  const token = localStorage.getItem('token') ?? ''
  return `${API_BASE}/questionnaire/${qid}/answer-all-stream?token=${token}`
}

export const regenerateStreamUrl = (questionId: string) => {
  const token = localStorage.getItem('token') ?? ''
  return `${API_BASE}/questionnaire/questions/${questionId}/regenerate?token=${token}`
}

// Answer Library
export const saveToLibrary = (questionText: string, answerText: string, questionnaireId: string) =>
  api.post('/library/entries', { question_text: questionText, answer_text: answerText, source_questionnaire_id: questionnaireId })
export const listLibrary = () => api.get('/library/entries')
export const deleteLibraryEntry = (id: string) => api.delete(`/library/entries/${id}`)
