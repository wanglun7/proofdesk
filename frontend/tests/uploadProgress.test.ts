import test from 'node:test'
import assert from 'node:assert/strict'

import { getAggregateUploadProgress } from '../src/lib/uploadProgress.ts'

test('aggregate upload progress includes partial embedding work', () => {
  const progress = getAggregateUploadProgress([
    { filename: 'manual.docx', status: 'embedding', current: 20, total: 126 },
  ])

  assert.equal(progress.completedCount, 0)
  assert.equal(progress.totalCount, 1)
  assert.ok(progress.percent > 0)
  assert.ok(progress.percent < 100)
})

test('aggregate upload progress averages completed and in-flight files', () => {
  const progress = getAggregateUploadProgress([
    { filename: 'manual.docx', status: 'done', chunks: 126 },
    { filename: 'policy.docx', status: 'embedding', current: 50, total: 100 },
  ])

  assert.equal(progress.completedCount, 1)
  assert.equal(progress.totalCount, 2)
  assert.ok(progress.percent > 50)
  assert.ok(progress.percent < 100)
})
