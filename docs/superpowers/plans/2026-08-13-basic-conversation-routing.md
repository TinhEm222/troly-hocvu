# Basic Conversation Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép chatbot trả lời tự nhiên các câu basic, từ chối mềm câu hỏi ngoài phạm vi và vẫn giữ RAG có nguồn cho câu hỏi học vụ.

**Architecture:** Một module pure-function `llm/intent.py` nhận diện greeting, thanks và capabilities trước retrieval. Hai route chat dùng module này để trả lời trực tiếp và lưu lịch sử; câu không có tài liệu đủ liên quan dùng thông báo ngoài phạm vi thay vì đưa context không liên quan cho LLM. Prompt RAG được nới văn phong nhưng vẫn yêu cầu bám CONTEXT.

**Tech Stack:** Python 3.12, FastAPI, unittest/pytest, Gemini streaming, Qdrant/RAG hiện có.

## Global Constraints

- Không đọc hoặc thay đổi `DA08-VSF-AI/**`.
- Basic không gọi Qdrant, embedding, reranker hoặc Gemini/Ollama.
- Basic và ngoài phạm vi không hiển thị nguồn tham khảo.
- Câu hỏi học vụ vẫn dùng context và metadata nguồn hiện tại.
- Không đưa API key hoặc dữ liệu bí mật vào mã nguồn, test hoặc commit.

---

### Task 1: Add deterministic basic-intent responses

**Files:**
- Create: `llm/intent.py`
- Test: `tests/test_intent.py`

**Interfaces:**
- Produces `get_basic_response(question: str) -> str | None`.
- Returns a fixed Vietnamese response for greetings, thanks and capability questions; returns `None` for school questions and unrelated questions.

- [ ] **Step 1: Write failing tests**

```python
def test_greeting_returns_basic_response():
    assert "Hello" in get_basic_response("Hello")

def test_capability_question_returns_basic_response():
    assert "học vụ" in get_basic_response("Bạn có thể giúp gì?").lower()

def test_school_question_is_not_basic():
    assert get_basic_response("Điều kiện xét tốt nghiệp là gì?") is None
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_intent.py`

Expected: FAIL because `llm.intent` and `get_basic_response` do not exist.

- [ ] **Step 3: Implement the minimal pure classifier**

Normalize case and punctuation, match only bounded greeting/thanks/capability phrases, and return `None` for all other input. Keep responses deterministic so basic chat does not depend on an LLM provider.

- [ ] **Step 4: Run the tests and confirm GREEN**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_intent.py`

Expected: all intent tests pass.

- [ ] **Step 5: Commit**

```bash
git add chatbot/llm/intent.py chatbot/tests/test_intent.py
git commit -m "feat: add basic conversation intent responses"
```

### Task 2: Route basic and out-of-scope questions in the API

**Files:**
- Modify: `api/routes/chat.py`
- Test: `tests/test_chat.py`

**Interfaces:**
- `/api/chat` and `/api/chat/stream` call `get_basic_response` before retrieval.
- Both routes persist the user message and deterministic assistant response with `sources=[]`.
- When reranked documents fail `_is_relevant`, both routes use `OUT_OF_SCOPE_MESSAGE` and do not call RAG generation.

- [ ] **Step 1: Add failing API tests**

```python
@patch("api.routes.chat.get_basic_response", return_value="Hello bạn sinh viên!")
@patch("api.routes.chat.hybrid_retrieve")
def test_basic_chat_skips_retrieval(self, mock_retrieve, mock_basic):
    response = asyncio.run(chat_endpoint(request, http_request, user, db))
    assert response.sources == []
    mock_retrieve.assert_not_called()
```

Add the equivalent streaming assertion for `sources=[]`, the deterministic token, and no retrieval call; add an out-of-scope assertion that `generate_answer`/`stream_answer` is not called when relevance fails.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_chat.py`

Expected: the new tests fail before route integration.

- [ ] **Step 3: Implement route branches**

Add `OUT_OF_SCOPE_MESSAGE`, persist direct responses, emit valid `meta`, `token`, and `done` SSE events for basic, and use the soft refusal for non-relevant retrieved documents. Preserve existing stage persistence and source metadata for relevant RAG answers.

- [ ] **Step 4: Run focused backend tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_chat.py tests/test_intent.py`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```bash
git add chatbot/api/routes/chat.py chatbot/tests/test_chat.py
git commit -m "feat: route basic and out-of-scope chat safely"
```

### Task 3: Relax the RAG prompt without allowing unsupported school facts

**Files:**
- Modify: `llm/prompt.py`
- Test: `tests/test_prompt.py`

**Interfaces:**
- `build_prompt(context: str, question: str)` keeps the existing signature.
- Prompt allows natural greetings only when they reach the LLM accidentally, but requires factual school answers to use CONTEXT.

- [ ] **Step 1: Write prompt contract tests**

Assert the generated prompt contains natural-conversation guidance, CTUT student scope, and the requirement not to invent school facts.

- [ ] **Step 2: Run the tests and confirm RED**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_prompt.py`

Expected: the new natural-conversation assertion fails against the current rigid prompt.

- [ ] **Step 3: Update only the prompt wording**

Remove the mandatory exact refusal for every no-context conversation, retain strict grounding for school-policy answers, and direct out-of-scope behavior to the route-level soft refusal.

- [ ] **Step 4: Run the complete project test set**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. ./.venv/bin/pytest -q tests/test_chat.py tests/test_generator.py tests/test_llm_config.py tests/test_retriever.py tests/test_intent.py tests/test_prompt.py`

Expected: all project tests pass.

- [ ] **Step 5: Commit**

```bash
git add chatbot/llm/prompt.py chatbot/tests/test_prompt.py
git commit -m "feat: relax assistant prompt for natural conversation"
```

### Task 4: Verify live behavior and frontend compatibility

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/ChatInterface.tsx`
- Test: `frontend/lib/basicConversationStream.test.ts`

- [ ] **Step 1: Add `intent?: 'basic' | 'rag'` to the SSE meta contract and hide the processing timeline for basic responses.**
- [ ] **Step 2: Run frontend stream tests and `next build`.**
- [ ] **Step 3: Restart backend if needed and check `/health`.**
- [ ] **Step 4: Live-test `Hello` and verify no sources/retrieval.**
- [ ] **Step 5: Live-test `Giá vàng hôm nay` and verify soft refusal with no sources.**
- [ ] **Step 6: Live-test a school question and verify source filename/page/snippet mapping.**

Expected: backend healthy, direct basic response, soft out-of-scope response, relevant RAG response with correct sources, frontend tests/build pass.
