# Chat Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Stream Gemini answers into the chat UI while keeping the JSON chat API and Ollama fallback working.

**Architecture:** Add a provider-neutral synchronous `stream_answer` iterator, an authenticated FastAPI SSE endpoint, and a browser `fetch` stream consumer. Existing retrieval, prompt construction, persistence, and `/api/chat` JSON behavior remain compatible.

**Tech Stack:** Python 3.12, FastAPI `StreamingResponse`, Gemini `google-genai`, Ollama SDK, React 19, Next.js 15, browser Fetch Streams, pytest.

## Global Constraints

- Preserve `POST /api/chat` and its JSON response contract.
- Use `gemini-3.5-flash-lite` without `temperature`, `top_p`, or `top_k` parameters.
- Fall back to Ollama only before the first generated chunk.
- Never expose API keys or provider exception details in SSE output.
- Keep embedding, Qdrant, BM25, reranking, authentication, and existing session ownership checks unchanged.
- Do not read or modify `DA08-VSF-AI`.

### Task 1: Streaming provider contract tests

**Files:**
- Modify: `tests/test_generator.py`

- [ ] **Step 1: Add a failing Gemini streaming test**

Patch `genai.Client`, return two fake response chunks with `.text`, call `list(generator.stream_answer('context', 'question'))`, and assert the list is `['Hello ', 'world']` and the request uses the configured model.

- [ ] **Step 2: Add a failing fallback streaming test**

Make Gemini's stream iterator raise before yielding, make Ollama's `chat(..., stream=True)` return two chunks, and assert the combined output is the Ollama chunks.

- [ ] **Step 3: Run focused tests and verify RED**

Run `PYTHONPATH=. pytest tests/test_generator.py -q`; expected failure because `stream_answer` does not exist.

### Task 2: Implement provider streaming

**Files:**
- Modify: `llm/generator.py`

- [ ] **Step 1: Implement Gemini stream helper**

Create `_stream_with_gemini(prompt: str)` that validates `GEMINI_API_KEY`, creates `genai.Client` with the configured timeout, calls `client.models.generate_content_stream(model=MODEL_NAME, contents=prompt, config=GenerateContentConfig(max_output_tokens=MODEL_MAX_TOKENS))`, yields non-empty `.text` chunks, and closes the client in `finally`.

- [ ] **Step 2: Implement Ollama stream helper**

Create `_stream_with_ollama(prompt: str, config: dict)` that calls `client.chat(..., stream=True)` and yields non-empty `chunk['message']['content']` values.

- [ ] **Step 3: Implement `stream_answer` with pre-first-chunk fallback**

Build the existing prompt, try the primary provider, track whether a chunk has been yielded, and if the primary fails before yielding use the fallback provider. Re-raise after partial output so the API can emit a safe stream error without concatenating a second answer.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run `PYTHONPATH=. pytest tests/test_generator.py -q`; expected all generator tests pass.

### Task 3: Add the SSE API endpoint

**Files:**
- Modify: `api/routes/chat.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Add stream event serialization tests**

Test the event formatter produces `event: meta`, JSON `data`, and a blank-line terminator. Test the endpoint's stream generator with mocked retrieval and streaming answer chunks, asserting ordered `meta`, `token`, and `done` events and a persisted assistant message.

- [ ] **Step 2: Implement the endpoint using existing auth/session/retrieval flow**

Add `@router.post('/chat/stream')` with the same `ChatRequest`, auth dependency, rate limiting, session ownership, retrieval, reranking, and context construction as `/api/chat`. Return `StreamingResponse` with `media_type='text/event-stream'`, `Cache-Control: no-cache`, and `X-Accel-Buffering: no`. Send `meta`, yield token events, persist the completed answer, then send `done`.

- [ ] **Step 3: Add safe stream errors and fallback behavior**

If retrieval or setup fails before streaming, return an SSE `error` event. If generation fails after partial output, emit only the safe error event and do not include exception text or secrets.

- [ ] **Step 4: Run backend tests**

Run `PYTHONPATH=. pytest -q tests`; expected all existing and new tests pass.

### Task 4: Connect the frontend stream

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/ChatInterface.tsx`

- [ ] **Step 1: Add typed stream event parsing**

Add `chatService.streamMessage(request, onEvent)` using `fetch`, the bearer token interceptor equivalent, `response.body.getReader()`, UTF-8 decoding, SSE frame buffering, and JSON parsing. Dispatch `meta`, `token`, `done`, and `error` events.

- [ ] **Step 2: Update ChatInterface to render incrementally**

Append the user message immediately, create an empty assistant placeholder, update its content on each token, attach sources on meta, and remove the placeholder or show a safe error on failure. Keep the input disabled until `done`.

- [ ] **Step 3: Build frontend**

Run `node node_modules/next/dist/bin/next build`; expected a successful production build.

### Task 5: Full verification

- [ ] **Step 1: Run backend regression and compile checks**

Run `PYTHONPATH=. pytest -q tests` and `python -m compileall -q api llm tests`.

- [ ] **Step 2: Run live SSE E2E**

With Qdrant, backend, Gemini key, and frontend running, register a temporary user, call `/api/chat/stream`, verify at least one `token` event and a final `done`, then verify the saved message through the history endpoint.

- [ ] **Step 3: Smoke-test frontend routes**

Start the production frontend and request `/`, `/login`, `/register`, `/chat`, `/admin`, `/admin/documents`, and `/admin/users`; expect HTTP `200` for each.
