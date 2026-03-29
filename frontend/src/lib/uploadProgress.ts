export interface UploadFileProgress {
  filename: string
  status: 'queued' | 'extracting' | 'chunking' | 'embedding' | 'done' | 'error'
  current?: number
  total?: number
  chunks?: number
  error?: string
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function getFileProgressFraction(file: UploadFileProgress): number {
  if (file.status === 'done' || file.status === 'error') return 1
  if (file.status === 'queued') return 0
  if (file.status === 'extracting') return 0.05
  if (file.status === 'chunking') {
    if (!file.total || file.total <= 0) return 0.15
    return 0.05 + 0.15 * clamp((file.current ?? 0) / file.total, 0, 1)
  }
  if (!file.total || file.total <= 0) return 0.2
  return 0.2 + 0.8 * clamp((file.current ?? 0) / file.total, 0, 1)
}

export function getAggregateUploadProgress(queue: UploadFileProgress[]) {
  const totalCount = queue.length
  if (totalCount === 0) {
    return { completedCount: 0, totalCount: 0, percent: 0 }
  }

  const completedCount = queue.filter((file) => file.status === 'done' || file.status === 'error').length
  const percent = Math.round(
    queue.reduce((sum, file) => sum + getFileProgressFraction(file), 0) / totalCount * 100,
  )

  return { completedCount, totalCount, percent }
}
