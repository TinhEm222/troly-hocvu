export interface ParsedSseFrame {
  eventName: string;
  payload: unknown;
}

function parsePayload(data: string): unknown {
  const parsed = JSON.parse(data);

  if (typeof parsed !== 'string') return parsed;

  try {
    return JSON.parse(parsed);
  } catch {
    return parsed;
  }
}

export function parseSseFrame(frame: string): ParsedSseFrame | null {
  let eventName = '';
  let data = '';

  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) eventName = line.slice(6).trim();
    if (line.startsWith('data:')) data += line.slice(5).trim();
  }

  if (!eventName || !data) return null;
  return { eventName, payload: parsePayload(data) };
}
