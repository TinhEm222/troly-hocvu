# Gemini Primary with Ollama Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Route RAG answer generation through Gemini 3.5 Flash-Lite first and transparently fall back to Ollama when Gemini is unavailable.

**Architecture:** Keep `generate_answer(context, question)` as the stable boundary. Add provider-specific private functions inside the existing LLM module, with Gemini configured from `GEMINI_API_KEY` and Ollama configured from a nested fallback block. Provider failures are caught at the dispatch boundary so the chat route and retrieval pipeline do not change.

**Tech Stack:** Python 3.12, FastAPI, `google-genai`, existing `ollama` SDK, YAML settings, pytest.

## Global Constraints

- Do not store or log the Gemini API key.
- Keep embedding (`intfloat/multilingual-e5-small`), Qdrant, BM25, reranking, and prompt construction unchanged.
- Use model ID `gemini-3.5-flash-lite`.
- Do not send deprecated `temperature`, `top_p`, or `top_k` sampling parameters to Gemini.
- Preserve a safe user-facing response when both providers fail.

### Task 1: Provider contract tests

**Files:**
- Modify: `tests/test_generator.py`

**Interfaces:**
- Tests target `llm.generator.generate_answer` and provider calls only through patched SDK clients.

- [ ] **Step 1: Replace Ollama-only tests with Gemini-primary scenarios**

Add tests for Gemini success, Gemini failure followed by Ollama success, missing Gemini key fallback, and both providers failing. Assert returned text and that Gemini receives the configured model and prompt without a temperature field.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_generator.py -q`

Expected: FAIL because the current generator imports only Ollama and has no Gemini dispatch.

### Task 2: Gemini adapter and fallback dispatch

**Files:**
- Modify: `llm/generator.py`

**Interfaces:**
- `generate_answer(context: str, question: str) -> str` remains unchanged for `api.routes.chat`.
- Private `_generate_with_gemini(prompt: str) -> str` and `_generate_with_ollama(prompt: str) -> str` each return stripped text or raise their provider exception.

- [ ] **Step 1: Add the official SDK import and provider-specific helpers**

Use `from google import genai` and `from google.genai import types`. Construct the client with the environment-provided API key and configured timeout. Call `client.models.generate_content(model=..., contents=prompt, config=types.GenerateContentConfig(max_output_tokens=...))`; read `response.text` and reject an empty result.

- [ ] **Step 2: Dispatch Gemini first and Ollama second**

Keep empty-input guards. On Gemini failure, log the provider and exception class, then invoke Ollama. On fallback failure, return the existing generic generation error. Do not include exception strings containing URLs or credential material in user output.

- [ ] **Step 3: Run focused tests and verify they pass**

Run: `pytest tests/test_generator.py -q`

Expected: all generator tests pass.

### Task 3: Configuration and dependency wiring

**Files:**
- Modify: `config/settings.yaml`
- Modify: `core/settings_loader.py`
- Modify: `.env.example`
- Modify: `requirements.txt`
- Modify: `docker-compose.yml`

**Interfaces:**
- YAML supplies safe non-secret defaults.
- `GEMINI_API_KEY` is read from the process environment only.

- [ ] **Step 1: Set Gemini primary and nested Ollama fallback defaults**

Set primary provider/model to Gemini and add fallback provider/model/base URL fields. Keep timeout and max-token settings explicit.

- [ ] **Step 2: Add environment overrides and SDK dependency**

Support `GEMINI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL_NAME`, `LLM_BASE_URL`, and fallback overrides without ever copying the key into logs or YAML. Add `google-genai` to `requirements.txt`.

- [ ] **Step 3: Pass the key through Compose and run configuration tests**

Add `GEMINI_API_KEY` to the service environment interpolation and run `pytest tests/test_llm_config.py -q` plus the focused generator tests.

### Task 4: Documentation and regression verification

**Files:**
- Modify: `README.md`
- Modify: `tests/test_llm_config.py`

- [ ] **Step 1: Document provider order and secret setup**

Explain that Gemini is primary, Ollama is fallback, and the key must be supplied through `.env`/deployment secrets. Do not paste a real key.

- [ ] **Step 2: Run the complete backend suite and compile check**

Run: `pytest -q` and `python -m compileall -q . -x 'DA08-VSF-AI'` from the chatbot directory.

- [ ] **Step 3: Run runtime smoke checks**

Start the backend with an out-of-band `GEMINI_API_KEY`, call `/health`, authenticate, and submit one basic RAG question. Verify the answer is non-empty and the logs do not contain the key. If the key is unavailable or invalid, verify the Ollama fallback path instead.
