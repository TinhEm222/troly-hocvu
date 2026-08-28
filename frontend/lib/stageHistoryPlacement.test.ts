import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('processing is collapsed by default and appears before the answer and sources', async () => {
  const source = await readFile(new URL('../components/ChatInterface.tsx', import.meta.url), 'utf8');
  const stageIndex = source.indexOf('message.role === \'assistant\' && message.stageHistory');
  const sourceGuardIndex = source.indexOf('!message.streaming && message.role === \'assistant\'');
  const sourcesIndex = source.indexOf('Nguồn tham khảo đang sử dụng:');
  const answerIndex = source.indexOf('className="whitespace-pre-wrap"');

  assert.ok(stageIndex >= 0, 'stage history block is missing');
  assert.ok(sourceGuardIndex >= 0, 'sources must wait until streaming finishes');
  assert.ok(sourcesIndex >= 0, 'streaming sources block is missing');
  assert.ok(answerIndex >= 0, 'answer block is missing');
  assert.ok(stageIndex < answerIndex, 'stage history must appear before the answer');
  assert.ok(sourcesIndex > answerIndex, 'sources must appear after the answer');
  assert.ok(sourceGuardIndex < sourcesIndex, 'streaming guard must wrap the sources block');
  assert.doesNotMatch(source.slice(stageIndex, answerIndex), /<details open/);
  assert.doesNotMatch(source.slice(stageIndex, answerIndex), /stage\.detail|formatStageDuration|duration_ms/);
  assert.doesNotMatch(source.slice(stageIndex, answerIndex), /streamingStatus/);
});
