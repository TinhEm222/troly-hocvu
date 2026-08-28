import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('admin document actions expose re-index progress and confirm deletion', async () => {
  const source = await readFile(new URL('../app/admin/documents/page.tsx', import.meta.url), 'utf8');

  assert.match(source, /getReindexStatus/);
  assert.match(source, /window\.confirm/);
  assert.match(source, /role="status"/);
  assert.match(source, /multiple/);
  assert.match(source, /uploadFilesSequentially/);
  assert.match(source, /progressbar/);
  assert.match(source, /progress_percent/);
  assert.match(source, /visibilitychange/);
  assert.match(source, /setIsReindexing\(status\.running\)/);
  assert.match(source, /uploadMode/);
  assert.match(source, /replacesDocumentId/);
  assert.match(source, /lifecycle_status/);
  assert.match(source, /version_number/);
});

test('admin user deletion requires confirmation', async () => {
  const source = await readFile(new URL('../app/admin/users/page.tsx', import.meta.url), 'utf8');

  assert.match(source, /window\.confirm/);
});

test('admin dashboard exposes loading and retry states', async () => {
  const source = await readFile(new URL('../app/admin/page.tsx', import.meta.url), 'utf8');

  assert.match(source, /loadStats/);
  assert.match(source, /role="status"/);
  assert.match(source, /Thử lại/);
});

test('login inputs keep entered credentials readable on light fields', async () => {
  const source = await readFile(new URL('../app/login/page.tsx', import.meta.url), 'utf8');
  const styles = await readFile(new URL('../app/globals.css', import.meta.url), 'utf8');

  assert.match(source, /text-gray-900/);
  assert.match(source, /bg-white/);
  assert.match(source, /placeholder:text-gray-400/);
  assert.match(source, /login-input/);
  assert.match(styles, /\.login-input[\s\S]*-webkit-text-fill-color:\s*#111827\s*!important/);
});
