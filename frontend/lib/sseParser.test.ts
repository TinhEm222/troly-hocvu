import assert from 'node:assert/strict';
import test from 'node:test';

import { parseSseFrame } from './sseParser.ts';

test('parses a token SSE frame into an object payload', () => {
  const result = parseSseFrame('event: token\ndata: {"text":"Xin chào"}');

  assert.deepEqual(result, { eventName: 'token', payload: { text: 'Xin chào' } });
});

test('unwraps a double-encoded token payload instead of exposing JSON text', () => {
  const result = parseSseFrame(
    'event: token\ndata: "{\\"text\\":\\"Xin chào\\"}"',
  );

  assert.deepEqual(result, { eventName: 'token', payload: { text: 'Xin chào' } });
});
