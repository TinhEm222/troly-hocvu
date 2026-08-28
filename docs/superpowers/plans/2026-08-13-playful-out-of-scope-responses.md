# Playful Out-of-Scope Responses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make out-of-scope answers varied, playful, and closed-ended while preventing Gemini from answering the unrelated question or generating code.

**Architecture:** Keep retrieval as the scope gate. When a query is classified as out of scope, send it to a dedicated constrained prompt rather than the general conversation prompt. Validate the completed model response for code/question leakage and use deterministic witty fallback variants when the provider fails or violates the contract; the streaming route emits the validated response and never exposes an unsafe partial answer.

**Tech Stack:** Python, Google Gemini API, existing FastAPI SSE streaming route, `unittest`/`pytest`.

## Global Constraints

- Keep `config/settings.yaml` `llm.max_tokens` and fallback `max_tokens` at `512`.
- Do not read or modify `DA08-VSF-AI/**`.
- Out-of-scope responses must not answer the unrelated topic, provide code/instructions, ask a follow-up question, or create sources.
- Preserve existing RAG behavior for relevant CTUT academic questions.
- Preserve Markdown/LaTeX output behavior for in-scope Gemini answers.

---

### Task 1: Add a constrained playful out-of-scope generator

**Files:**
- Modify: `llm/prompt.py`
- Modify: `llm/generator.py`
- Test: `tests/test_prompt.py`
- Test: `tests/test_generator.py`

**Interfaces:**
- Produces `build_out_of_scope_prompt(question: str) -> str`.
- Produces `generate_out_of_scope_answer(question: str) -> str`.
- Produces `stream_out_of_scope_answer(question: str) -> Iterator[str]`.

- [ ] **Step 1: Write failing prompt and generator tests**

Add tests that require the dedicated prompt to contain the closed-response rules, and mock Gemini with both a safe playful answer and an unsafe code answer:

```python
def test_out_of_scope_prompt_forbids_answering_or_follow_up(self):
    prompt = build_out_of_scope_prompt("Viết phương trình bậc 2 bằng Python").casefold()
    self.assertIn("không giải thích", prompt)
    self.assertIn("không hỏi lại", prompt)
    self.assertIn("bựa nhẹ", prompt)

def test_out_of_scope_generator_preserves_safe_playful_response(self):
    client = Mock()
    client.models.generate_content.return_value.text = (
        "Python để các cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi."
    )
    mock_client_class.return_value = client
    with patch.object(generator, "GEMINI_API_KEY", "test-key"):
        result = generator.generate_out_of_scope_answer("Viết phương trình bậc 2 bằng Python")
    self.assertIn("mình chuyên học vụ CTUT", result)
    mock_prompt.assert_called_once()

def test_out_of_scope_generator_replaces_code_leak_with_witty_fallback(self):
    client = Mock()
    client.models.generate_content.return_value.text = "import cmath\nprint('code')"
    mock_client_class.return_value = client
    with patch.object(generator, "GEMINI_API_KEY", "test-key"):
        result = generator.generate_out_of_scope_answer("Viết phương trình bậc 2 bằng Python")
    self.assertNotIn("import cmath", result)
    self.assertNotIn("print(", result)
```

The stream test must assert that an unsafe streamed response is withheld and replaced by a fallback rather than being sent chunk-by-chunk.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_prompt.py tests/test_generator.py -k out_of_scope
```

Expected: FAIL because the dedicated prompt and generator functions do not exist yet.

- [ ] **Step 3: Implement the dedicated prompt**

Add `OUT_OF_SCOPE_PROMPT` and `build_out_of_scope_prompt()` in `llm/prompt.py`. The prompt must require 1–2 Vietnamese sentences, light humor, no profanity, no answer to the requested unrelated topic, no code/steps, no question mark, no invitation to continue, and a natural reminder that the assistant handles CTUT academic matters.

- [ ] **Step 4: Implement safe generation and deterministic fallback variants**

In `llm/generator.py`, add:

```python
def generate_out_of_scope_answer(question: str) -> str:
    """Generate a playful closed response without answering an out-of-scope query."""

def stream_out_of_scope_answer(question: str):
    """Yield only a validated playful out-of-scope response."""
```

Use the existing Gemini/fallback provider functions with `build_out_of_scope_prompt()`. Collect the streamed provider chunks before yielding them so unsafe text cannot reach the browser. Reject empty text, question marks, code fences, and obvious code markers such as `import `, `def `, `print(`, and `return `. On rejection or provider failure, select one of several fixed witty closed responses using a stable hash of the question, so the fallback is varied without randomness.

- [ ] **Step 5: Run focused tests and verify they pass**

Run the command from Step 2. Expected: all out-of-scope prompt and generator tests pass.

- [ ] **Step 6: Commit the generator slice**

```bash
git add chatbot/llm/prompt.py chatbot/llm/generator.py chatbot/tests/test_prompt.py chatbot/tests/test_generator.py
git commit -m "feat: add playful safe out-of-scope generator"
```

### Task 2: Route out-of-scope API and SSE responses through the safe generator

**Files:**
- Modify: `api/routes/chat.py`
- Test: `tests/test_chat.py`

**Interfaces:**
- Consumes `generate_out_of_scope_answer(question)` for the non-streaming route.
- Consumes `stream_out_of_scope_answer(question)` for the streaming route.
- Continues returning `sources=[]` for out-of-scope responses.

- [ ] **Step 1: Write failing route tests**

Update the existing out-of-scope tests to mock the new functions. Assert that the endpoint returns the humorous generated response, does not call `generate_answer`, and still returns no sources. For SSE, assert the token contains the safe response and does not contain a mocked unsafe code response.

```python
def test_out_of_scope_chat_uses_playful_generator_without_sources(self):
    playful = "Python để cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi."
    with patch("api.routes.chat.generate_out_of_scope_answer", return_value=playful) as mock_answer:
        response = asyncio.run(chat_endpoint(request, req, user, db))
    self.assertEqual(response.answer, playful)
    self.assertEqual(response.sources, [])
    mock_answer.assert_called_once_with(request.query)

def test_out_of_scope_stream_uses_validated_playful_generator(self):
    playful = "Python để cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi."
    with patch("api.routes.chat.stream_out_of_scope_answer", return_value=iter([playful])) as mock_answer:
        response = asyncio.run(chat_stream_endpoint(request, req, user, db))
    body = "".join(asyncio.run(collect_body(response)))
    self.assertIn(playful, body)
    self.assertIn('"sources": []', body)
    mock_answer.assert_called_once_with(request.query)
```

- [ ] **Step 2: Run route tests to verify the old hard-coded behavior fails**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_chat.py -k out_of_scope
```

Expected: FAIL because the route currently returns `OUT_OF_SCOPE_MESSAGE` directly.

- [ ] **Step 3: Change both routes to use the dedicated generator**

Replace only the `documents`-present-but-not-relevant branch with `generate_out_of_scope_answer(question)` and the corresponding SSE branch with `stream_out_of_scope_answer(question)`. Keep the no-documents branch on `NO_ANSWER_MESSAGE`, keep `sources=[]`, and leave relevant-document RAG generation unchanged.

- [ ] **Step 4: Run route tests and the full scoped backend suite**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_chat.py -k out_of_scope
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_chat.py tests/test_generator.py tests/test_llm_config.py tests/test_retriever.py tests/test_intent.py tests/test_prompt.py
```

Expected: the focused tests and the complete scoped suite pass; no command may include `DA08-VSF-AI/**`.

- [ ] **Step 5: Restart and verify the live backend**

Restart the existing Uvicorn process, then run:

```bash
curl -sS http://127.0.0.1:8000/health | jq -c '{status, qdrant:.services.qdrant.status, embedding:.services.embedding.status, llm:.services.llm.status, rag:.services.rag_components.initialized}'
```

Expected: `status` is `healthy`, with Qdrant, embedding, LLM, and RAG initialized.

- [ ] **Step 6: Commit the routing slice**

```bash
git add chatbot/api/routes/chat.py chatbot/tests/test_chat.py
git commit -m "feat: use playful responses for out-of-scope queries"
```
