import assert from 'node:assert/strict';
import test from 'node:test';
import { buildStageViews, STREAM_STAGES } from './streamStages.ts';

test('timeline marks previous stages done and current stage active', () => {
  const views = buildStageViews('reranking');

  assert.deepEqual(views.map((stage) => stage.id), STREAM_STAGES.map((stage) => stage.id));
  assert.deepEqual(views.map((stage) => stage.state), ['done', 'active', 'pending']);
});

test('timeline is pending before the first status event', () => {
  const views = buildStageViews(null);

  assert.deepEqual(views.map((stage) => stage.state), ['pending', 'pending', 'pending']);
});
