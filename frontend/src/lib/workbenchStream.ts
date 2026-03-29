export interface StreamCitation {
  source: string
  page: number
  excerpt: string
}

export interface StreamQuestionItem {
  answer_id: string
  seq: number
  status: string
  draft: string | null
  citations: StreamCitation[] | null
  confidence: number | null
  needs_review: boolean
  flag_reason: string | null
  from_library?: boolean
}

export type AnswerAllEvent =
  | { type: 'answering'; seq: number; total: number }
  | {
      type: 'answer'
      answer_id: string
      draft: string | null
      citations: StreamCitation[] | null
      confidence: number | null
      needs_review: boolean
      status: string
      from_library?: boolean
    }
  | { type: 'done' }
  | { type: 'error'; seq: number; error: string }

export interface AnswerAllEventResult {
  items: StreamQuestionItem[]
  progress?: { current: number; total: number } | null
  finished: boolean
  alertMessage: string | null
}

export function reduceAnswerAllEvent<T extends StreamQuestionItem>(
  items: T[],
  event: AnswerAllEvent,
): AnswerAllEventResult & { items: T[] } {
  if (event.type === 'answering') {
    return {
      items: items.map((item) => (
        item.seq === event.seq ? { ...item, status: 'answering', flag_reason: null } : item
      )),
      progress: { current: event.seq + 1, total: event.total },
      finished: false,
      alertMessage: null,
    }
  }

  if (event.type === 'answer') {
    return {
      items: items.map((item) => (
        item.answer_id === event.answer_id
          ? {
              ...item,
              draft: event.draft,
              citations: event.citations,
              confidence: event.confidence,
              needs_review: event.needs_review,
              status: event.status,
              from_library: event.from_library ?? false,
              flag_reason: null,
            }
          : item
      )),
      finished: false,
      alertMessage: null,
    }
  }

  if (event.type === 'error') {
    return {
      items: items.map((item) => (
        item.seq === event.seq
          ? { ...item, status: 'error', flag_reason: event.error }
          : item
      )),
      finished: false,
      alertMessage: `Question ${event.seq + 1} failed: ${event.error}`,
    }
  }

  return {
    items,
    progress: null,
    finished: true,
    alertMessage: null,
  }
}

export function markAnsweringItemsAsErrored<T extends StreamQuestionItem>(
  items: T[],
  message: string,
): T[] {
  return items.map((item) => (
    item.status === 'answering'
      ? { ...item, status: 'error', flag_reason: message }
      : item
  )) as T[]
}
