import test from 'node:test'
import assert from 'node:assert/strict'

import {
  markAnsweringItemsAsErrored,
  reduceAnswerAllEvent,
  type StreamQuestionItem,
} from '../src/lib/workbenchStream.ts'

function makeItem(overrides: Partial<StreamQuestionItem> = {}): StreamQuestionItem {
  return {
    answer_id: 'answer-1',
    seq: 0,
    status: 'pending',
    draft: null,
    citations: null,
    confidence: null,
    needs_review: false,
    flag_reason: null,
    from_library: false,
    ...overrides,
  }
}

test('error event marks the affected row as error and produces a user-visible message', () => {
  const result = reduceAnswerAllEvent(
    [makeItem({ status: 'answering' })],
    { type: 'error', seq: 0, error: 'AI answer failed. Check your AI provider configuration and try again.' },
  )

  assert.equal(result.items[0].status, 'error')
  assert.equal(result.items[0].flag_reason, 'AI answer failed. Check your AI provider configuration and try again.')
  assert.equal(result.alertMessage, 'AI answer failed. Check your AI provider configuration and try again.')
})

test('transport failure clears any answering rows into an error state', () => {
  const items = [
    makeItem({ answer_id: 'answer-1', seq: 0, status: 'answering' }),
    makeItem({ answer_id: 'answer-2', seq: 1, status: 'done' }),
  ]

  const result = markAnsweringItemsAsErrored(items, 'Connection lost during auto-answer.')

  assert.equal(result[0].status, 'error')
  assert.equal(result[0].flag_reason, 'Connection lost during auto-answer.')
  assert.equal(result[1].status, 'done')
})
