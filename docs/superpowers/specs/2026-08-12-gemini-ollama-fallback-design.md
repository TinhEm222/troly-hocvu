# Gemini Primary with Ollama Fallback

## Goal

Use `gemini-3.5-flash-lite` as the primary answer-generation provider while preserving the existing Ollama `qwen2.5:3b` provider as an automatic fallback. Embedding, retrieval, reranking, prompts, authentication, and chat persistence remain unchanged.

## Design

`llm.generator.generate_answer(context, question)` remains the stable application interface. It builds the existing RAG prompt once, then dispatches it to the configured primary provider. Gemini is called through the official `google-genai` Python SDK with an API key read only from `GEMINI_API_KEY`. Because the selected Gemini model deprecates sampling parameters, only the output-token limit is sent for Gemini. Ollama keeps its current temperature, token, timeout, and keep-alive behavior.

When the primary Gemini request fails due to missing configuration, authentication/API failure, network failure, or timeout, the generator logs only the provider and error category and attempts Ollama. If both providers fail, it returns the existing user-safe generic error message. Empty context/question validation remains before any provider call.

Configuration defaults to Gemini primary and contains a nested Ollama fallback configuration. Environment variables can override provider/model/base URL, Gemini API key, and timeout without storing secrets in YAML or source. Docker Compose passes `GEMINI_API_KEY` through `.env`; Ollama remains reachable through its existing host URL.

## Testing and acceptance criteria

- Gemini success returns the text from the SDK response.
- Gemini failure invokes Ollama and returns the Ollama answer.
- Missing Gemini key does not crash module import and falls back to Ollama.
- Failure of both providers returns a safe Vietnamese error without exposing credentials.
- Existing generator/chat tests and full backend test suite pass.
- Configuration examples, README, and dependency list describe the new provider order.
- A runtime smoke test confirms a real Gemini response when a valid key is supplied out-of-band.

## Official references

- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
- https://ai.google.dev/gemini-api/docs/generate-content/text-generation
- https://ai.google.dev/gemini-api/docs/latest-model
