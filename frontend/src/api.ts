import axios from 'axios'

const BASE = 'http://localhost:8000/api'
const api = axios.create({ baseURL: BASE })

export const uploadDoc = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/kb/upload', fd)
}

export const listDocs = () => api.get('/kb/documents')

export const parseQuestionnaire = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/questionnaire/parse', fd)
}

export const answerAll = (qid: string) =>
  api.post(`/questionnaire/${qid}/answer-all`)

export const getAnswers = (qid: string) =>
  api.get(`/questionnaire/${qid}/answers`)

export const patchAnswer = (
  aid: string,
  data: { human_edit?: string; status?: string }
) => api.patch(`/questionnaire/answers/${aid}`, data)

export const exportUrl = (qid: string) =>
  `${BASE}/questionnaire/${qid}/export`
