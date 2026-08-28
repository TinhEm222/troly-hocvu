import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import assert from 'node:assert/strict';

test('assistant messages use Markdown and KaTeX rendering', async () => {
  const component = await readFile(
    new URL('../components/MarkdownMessage.tsx', import.meta.url),
    'utf8',
  );

  assert.match(component, /ReactMarkdown/);
  assert.match(component, /remarkGfm/);
  assert.match(component, /rehypeKatex/);
  assert.match(component, /skipHtml/);
});
