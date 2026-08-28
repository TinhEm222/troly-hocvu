import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import assert from 'node:assert/strict';

test('basic stream metadata clears retrieval stages in the chat UI', async () => {
  const api = await readFile(new URL('./api.ts', import.meta.url), 'utf8');
  const chat = await readFile(new URL('../components/ChatInterface.tsx', import.meta.url), 'utf8');

  assert.match(api, /intent\?: 'basic' \| 'rag'/);
  assert.match(chat, /payload\.intent === 'basic'/);
  assert.match(chat, /stageQueueRef\.current = \[\]/);
  assert.match(chat, /streamingIntent !== 'basic'/);
});
