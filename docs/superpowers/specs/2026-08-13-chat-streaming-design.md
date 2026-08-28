# Chat Streaming Design

## Goal

Improve perceived response time by streaming answer text to the chat UI as soon as Gemini produces it, while preserving the existing JSON chat endpoint and Ollama fallback.

## Contract

Add `POST /api/chat/stream` with the same authenticated request body as `/api/chat`:

```json
{"query":"...","session_id":null}
```

The response uses `text/event-stream` and emits JSON SSE events:

- `meta`: `{ "session_id": string, "sources": Source[] }`, emitted after retrieval/reranking and before generation.
- `token`: `{ "text": string }`, emitted for each generated text chunk.
- `done`: `{ "session_id": string }`, emitted after the complete answer is persisted.
- `error`: `{ "message": string }`, emitted only when the stream cannot produce a usable answer.

The existing `POST /api/chat` JSON contract remains unchanged for backward compatibility.

## Architecture

The LLM module exposes `stream_answer(context, question)` as a synchronous iterator of text chunks. Gemini uses `generate_content_stream` without deprecated sampling parameters. If Gemini fails before producing any chunk, the iterator switches to Ollama's streaming chat API. Once output has started, provider errors terminate the stream with a safe error event rather than mixing two partial answers.

The stream route performs authentication, session creation, retrieval, reranking, and context construction before returning `StreamingResponse`. It sends metadata first, accumulates chunks, persists the complete assistant message after successful generation, and emits `done`. The frontend consumes the stream with `fetch()` and `ReadableStream`, because browser Axios does not expose incremental response chunks consistently.

## UX behavior

The user message appears immediately. The assistant placeholder shows a clear generation state, then replaces it incrementally with streamed text. Sources appear when the `meta` event arrives. The input remains disabled while streaming, and provider/API errors become a visible assistant error message.

## Testing and acceptance criteria

- Gemini streaming emits all text chunks in order.
- Gemini failure before the first chunk falls back to Ollama streaming.
- Existing JSON `/api/chat` behavior and tests remain passing.
- Stream endpoint emits valid ordered `meta`, `token*`, `done` events and persists history.
- Frontend build passes and uses the streaming endpoint for new messages.
- Live E2E receives at least one token event from Gemini and a final `done` event.
