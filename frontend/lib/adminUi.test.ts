import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getReindexStatusMessage,
  isReindexFinished,
  shouldStopReindexPolling,
  uploadFilesSequentially,
} from './adminUi.ts';

test('re-index status is unfinished while the background job is running', () => {
  assert.equal(isReindexFinished({ running: true, last_error: null }), false);
});

test('re-index status is finished when the background job stops', () => {
  assert.equal(isReindexFinished({ running: false, last_error: null }), true);
});

test('re-index status exposes backend errors to the admin', () => {
  assert.equal(
    getReindexStatusMessage({ running: false, last_error: 'Không đọc được file PDF.' }),
    'Re-index thất bại: Không đọc được file PDF.',
  );
});

test('re-index polling stops after its safety timeout', () => {
  assert.equal(shouldStopReindexPolling(1_000, 301_001), true);
  assert.equal(shouldStopReindexPolling(1_000, 300_999), false);
});

test('uploads selected files sequentially and continues after an individual failure', async () => {
  const events: string[] = [];
  const files = [{ name: 'one.pdf' }, { name: 'two.pdf' }, { name: 'three.pdf' }] as File[];

  const result = await uploadFilesSequentially(files, async (file) => {
    events.push(`start:${file.name}`);
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (file.name === 'two.pdf') throw new Error('duplicate');
    events.push(`done:${file.name}`);
    return file.name;
  });

  assert.deepEqual(events, [
    'start:one.pdf',
    'done:one.pdf',
    'start:two.pdf',
    'start:three.pdf',
    'done:three.pdf',
  ]);
  assert.deepEqual(result.uploaded, ['one.pdf', 'three.pdf']);
  assert.deepEqual(result.failed.map(({ file }) => file.name), ['two.pdf']);
});
