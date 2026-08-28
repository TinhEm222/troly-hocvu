import hashlib
import logging
import os
import re
import time

import ollama
from google import genai
from google.genai import types

from core.settings_loader import load_settings
from llm.prompt import build_general_prompt, build_out_of_scope_prompt, build_prompt

settings = load_settings()
logger = logging.getLogger("llm")

LLM_CONFIG = settings["llm"]
MODEL_PROVIDER = LLM_CONFIG.get("provider", "gemini")
MODEL_NAME = LLM_CONFIG.get("model_name", "gemini-3.5-flash-lite")
MODEL_BASE_URL = LLM_CONFIG.get("base_url", "http://localhost:11434")
MODEL_TEMPERATURE = LLM_CONFIG.get("temperature", 0.2)
MODEL_MAX_TOKENS = LLM_CONFIG.get("max_tokens", 512)
MODEL_TIMEOUT = LLM_CONFIG.get("timeout", 120)
GEMINI_API_KEY = os.getenv(LLM_CONFIG.get("gemini_api_key_env", "GEMINI_API_KEY"), "")

FALLBACK_CONFIG = LLM_CONFIG.get("fallback", {})
FALLBACK_PROVIDER = FALLBACK_CONFIG.get("provider", "ollama")
FALLBACK_MODEL_NAME = FALLBACK_CONFIG.get("model_name", "qwen2.5:3b")
FALLBACK_BASE_URL = FALLBACK_CONFIG.get("base_url", "http://localhost:11434")
FALLBACK_TEMPERATURE = FALLBACK_CONFIG.get("temperature", MODEL_TEMPERATURE)
FALLBACK_MAX_TOKENS = FALLBACK_CONFIG.get("max_tokens", MODEL_MAX_TOKENS)
FALLBACK_TIMEOUT = FALLBACK_CONFIG.get("timeout", MODEL_TIMEOUT)
GENERAL_FALLBACK_RESPONSE = (
    "Mình chưa thể trả lời câu này ngay lúc này. Bạn có thể thử lại sau, hoặc hỏi mình "
    "về thông tin học vụ dành cho sinh viên CTUT."
)
OUT_OF_SCOPE_FALLBACKS = (
    "Nội dung này nằm ngoài phạm vi hỗ trợ của trợ lý. Mình chỉ hỗ trợ thông tin học vụ và quy định chính thức dành cho sinh viên CTUT.",
    "Mình chưa thể hỗ trợ chủ đề này. Trợ lý hiện chỉ tập trung vào các câu hỏi học vụ, học phí và quy chế đào tạo của CTUT.",
    "Mình xin phép không trả lời nội dung ngoài chuyên môn. Phạm vi hỗ trợ hiện tại là thông tin học vụ chính thức dành cho sinh viên CTUT.",
    "Câu hỏi này không thuộc phạm vi tư vấn của trợ lý. Mình chỉ hỗ trợ tra cứu thông tin học vụ và quy định liên quan tại CTUT.",
)
OUT_OF_SCOPE_STREAM_CHUNK_SIZE = 28
OUT_OF_SCOPE_STREAM_DELAY_SECONDS = 0.04
_UNSAFE_OUT_OF_SCOPE_PATTERNS = (
    re.compile(r"```|<script\b", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*(?:import\s+\w+|from\s+\w+\s+import\s+|def\s+\w+\s*\(|class\s+\w+\s*[:(])", re.IGNORECASE),
    re.compile(r"\b(?:print|return|console\.log)\s*\(", re.IGNORECASE),
)
_FOLLOW_UP_MARKERS = (
    "bạn có muốn",
    "bạn có cần",
    "hãy cho mình biết",
    "cho mình biết",
    "nếu cần thêm",
    "mình có thể giúp",
    "cứ hú",
    "cứ hỏi",
    "cứ nhắn",
    "cứ gửi",
    "liên hệ mình",
)


def prepare_general_response(text: str) -> str:
    """Preserve the model response; formatting is rendered by the frontend."""
    return text or ""


def _out_of_scope_fallback(question: str) -> str:
    digest = hashlib.sha256((question or "").strip().encode("utf-8")).digest()
    return OUT_OF_SCOPE_FALLBACKS[digest[0] % len(OUT_OF_SCOPE_FALLBACKS)]


def _is_safe_out_of_scope_response(text: str) -> bool:
    candidate = (text or "").strip()
    if not candidate or "?" in candidate or "？" in candidate:
        return False
    if any(marker in candidate.casefold() for marker in _FOLLOW_UP_MARKERS):
        return False
    return not any(pattern.search(candidate) for pattern in _UNSAFE_OUT_OF_SCOPE_PATTERNS)


def _prepare_out_of_scope_response(text: str, question: str) -> str:
    candidate = (text or "").strip()
    if _is_safe_out_of_scope_response(candidate):
        return candidate
    logger.warning("Rejected unsafe out-of-scope response from provider")
    return _out_of_scope_fallback(question)


def _stream_text_in_chunks(text: str):
    for offset in range(0, len(text), OUT_OF_SCOPE_STREAM_CHUNK_SIZE):
        yield text[offset : offset + OUT_OF_SCOPE_STREAM_CHUNK_SIZE]
        if offset + OUT_OF_SCOPE_STREAM_CHUNK_SIZE < len(text):
            time.sleep(OUT_OF_SCOPE_STREAM_DELAY_SECONDS)


def generate_out_of_scope_answer(question: str) -> str:
    """Generate a playful closed response without answering an out-of-scope query."""
    if not question or not question.strip():
        return _out_of_scope_fallback(question)

    prompt = build_out_of_scope_prompt(question)
    try:
        answer = _generate_with_provider(MODEL_PROVIDER, prompt, LLM_CONFIG)
        return _prepare_out_of_scope_response(answer, question)
    except Exception as primary_error:
        logger.warning(
            "Primary out-of-scope provider failed. provider=%s error_type=%s",
            MODEL_PROVIDER,
            type(primary_error).__name__,
        )

    if FALLBACK_PROVIDER != MODEL_PROVIDER:
        try:
            answer = _generate_with_provider(FALLBACK_PROVIDER, prompt, FALLBACK_CONFIG)
            return _prepare_out_of_scope_response(answer, question)
        except Exception as fallback_error:
            logger.error(
                "Out-of-scope fallback provider failed. provider=%s error_type=%s",
                FALLBACK_PROVIDER,
                type(fallback_error).__name__,
            )

    return _out_of_scope_fallback(question)


def stream_out_of_scope_answer(question: str):
    """Yield only a validated playful out-of-scope response."""
    if not question or not question.strip():
        yield _out_of_scope_fallback(question)
        return

    prompt = build_out_of_scope_prompt(question)
    answer = ""
    try:
        answer = "".join(_stream_with_provider(MODEL_PROVIDER, prompt, LLM_CONFIG))
    except Exception as primary_error:
        logger.warning(
            "Primary out-of-scope stream failed. provider=%s error_type=%s",
            MODEL_PROVIDER,
            type(primary_error).__name__,
        )

    if not answer and FALLBACK_PROVIDER != MODEL_PROVIDER:
        try:
            answer = "".join(_stream_with_provider(FALLBACK_PROVIDER, prompt, FALLBACK_CONFIG))
        except Exception as fallback_error:
            logger.error(
                "Out-of-scope fallback stream failed. provider=%s error_type=%s",
                FALLBACK_PROVIDER,
                type(fallback_error).__name__,
            )

    validated_answer = _prepare_out_of_scope_response(answer, question)
    yield from _stream_text_in_chunks(validated_answer)


def _generate_with_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=MODEL_TIMEOUT * 1000),
    )
    try:
        # Gemini 3.5 Flash-Lite deprecates temperature/top_p/top_k. Only send
        # the output limit, as required by the current Gemini API.
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=MODEL_MAX_TOKENS),
        )
        answer = (response.text or "").strip()
        if not answer:
            raise RuntimeError("Gemini returned an empty response")
        return answer
    finally:
        client.close()


def _generate_with_ollama(prompt: str, config: dict) -> str:
    client = ollama.Client(
        host=config.get("base_url", MODEL_BASE_URL),
        timeout=config.get("timeout", MODEL_TIMEOUT),
    )
    response = client.chat(
        model=config.get("model_name", FALLBACK_MODEL_NAME),
        messages=[{"role": "system", "content": prompt}],
        options={
            "temperature": config.get("temperature", FALLBACK_TEMPERATURE),
            "num_predict": config.get("max_tokens", FALLBACK_MAX_TOKENS),
        },
        keep_alive="30m",
    )
    answer = (response["message"]["content"] or "").strip()
    if not answer:
        raise RuntimeError("Ollama returned an empty response")
    return answer


def _generate_with_provider(provider: str, prompt: str, config: dict) -> str:
    if provider == "gemini":
        return _generate_with_gemini(prompt)
    if provider == "ollama":
        return _generate_with_ollama(prompt, config)
    raise RuntimeError(f"Unsupported model provider: {provider}")


def _stream_with_gemini(prompt: str):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=MODEL_TIMEOUT * 1000),
    )
    try:
        response_stream = client.models.generate_content_stream(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=MODEL_MAX_TOKENS),
        )
        for response in response_stream:
            chunk = (response.text or "")
            if chunk:
                yield chunk
    finally:
        client.close()


def _stream_with_ollama(prompt: str, config: dict):
    client = ollama.Client(
        host=config.get("base_url", MODEL_BASE_URL),
        timeout=config.get("timeout", MODEL_TIMEOUT),
    )
    response_stream = client.chat(
        model=config.get("model_name", FALLBACK_MODEL_NAME),
        messages=[{"role": "system", "content": prompt}],
        options={
            "temperature": config.get("temperature", FALLBACK_TEMPERATURE),
            "num_predict": config.get("max_tokens", FALLBACK_MAX_TOKENS),
        },
        keep_alive="30m",
        stream=True,
    )
    for response in response_stream:
        chunk = (response.get("message", {}).get("content") or "")
        if chunk:
            yield chunk


def _stream_with_provider(provider: str, prompt: str, config: dict):
    if provider == "gemini":
        return _stream_with_gemini(prompt)
    if provider == "ollama":
        return _stream_with_ollama(prompt, config)
    raise RuntimeError(f"Unsupported model provider: {provider}")


def stream_answer(context: str, question: str):
    """Yield answer chunks, falling back only before primary output starts."""
    if not context or not context.strip():
        raise ValueError("Dữ liệu ngữ cảnh không được để trống.")
    if not question or not question.strip():
        raise ValueError("Câu hỏi không được để trống.")

    prompt = build_prompt(context, question)
    primary_started = False

    try:
        for chunk in _stream_with_provider(MODEL_PROVIDER, prompt, LLM_CONFIG):
            primary_started = True
            yield chunk
        return
    except Exception as primary_error:
        if primary_started:
            logger.error(
                "Primary LLM stream failed after output started. provider=%s error_type=%s",
                MODEL_PROVIDER,
                type(primary_error).__name__,
            )
            raise
        logger.warning(
            "Primary LLM stream failed before output; attempting fallback. provider=%s error_type=%s",
            MODEL_PROVIDER,
            type(primary_error).__name__,
        )

    if FALLBACK_PROVIDER == MODEL_PROVIDER:
        raise RuntimeError("Fallback provider is the same as the primary provider.")

    for chunk in _stream_with_provider(FALLBACK_PROVIDER, prompt, FALLBACK_CONFIG):
        yield chunk


def stream_general_answer(question: str):
    """Stream a natural response for non-RAG conversation without internal context."""
    if not question or not question.strip():
        raise ValueError("Câu hỏi không được để trống.")

    prompt = build_general_prompt(question)
    primary_started = False

    try:
        for chunk in _stream_with_provider(MODEL_PROVIDER, prompt, LLM_CONFIG):
            primary_started = True
            if chunk:
                yield chunk
        return
    except Exception as primary_error:
        if primary_started:
            logger.error(
                "General LLM stream failed after output started. provider=%s error_type=%s",
                MODEL_PROVIDER,
                type(primary_error).__name__,
            )
            raise
        logger.warning(
            "General LLM stream failed before output; attempting fallback. provider=%s error_type=%s",
            MODEL_PROVIDER,
            type(primary_error).__name__,
        )

    if FALLBACK_PROVIDER != MODEL_PROVIDER:
        try:
            for chunk in _stream_with_provider(FALLBACK_PROVIDER, prompt, FALLBACK_CONFIG):
                if chunk:
                    yield chunk
            return
        except Exception as fallback_error:
            logger.error(
                "General fallback stream failed. provider=%s error_type=%s",
                FALLBACK_PROVIDER,
                type(fallback_error).__name__,
            )

    yield GENERAL_FALLBACK_RESPONSE


def generate_general_answer(question: str) -> str:
    """Generate a natural non-RAG response without inventing school facts."""
    if not question or not question.strip():
        return "Câu hỏi không được để trống."

    prompt = build_general_prompt(question)
    start = time.time()
    logger.info("Generating general conversation answer using primary provider: %s", MODEL_PROVIDER)
    try:
        return prepare_general_response(
            _generate_with_provider(MODEL_PROVIDER, prompt, LLM_CONFIG)
        )
    except Exception as primary_error:
        logger.warning(
            "Primary general conversation provider failed. provider=%s error_type=%s",
            MODEL_PROVIDER,
            type(primary_error).__name__,
        )

    if FALLBACK_PROVIDER != MODEL_PROVIDER:
        try:
            return prepare_general_response(
                _generate_with_provider(FALLBACK_PROVIDER, prompt, FALLBACK_CONFIG)
            )
        except Exception as fallback_error:
            logger.error(
                "General conversation fallback failed. provider=%s error_type=%s elapsed=%.2fs",
                FALLBACK_PROVIDER,
                type(fallback_error).__name__,
                time.time() - start,
            )

    return GENERAL_FALLBACK_RESPONSE


def generate_answer(context: str, question: str) -> str:
    if not context or not context.strip():
        logger.warning("Received empty context for answer generation.")
        return "Dữ liệu ngữ cảnh không được để trống."

    if not question or not question.strip():
        logger.warning("Received empty question for answer generation.")
        return "Câu hỏi không được để trống."

    prompt = build_prompt(context, question)
    start = time.time()

    logger.info("Generating answer using primary model provider: %s", MODEL_PROVIDER)
    try:
        answer = _generate_with_provider(MODEL_PROVIDER, prompt, LLM_CONFIG)
        logger.info("Answer generated by primary provider successfully.")
        return answer
    except Exception as primary_error:
        logger.warning(
            "Primary LLM provider failed; attempting fallback. provider=%s error_type=%s",
            MODEL_PROVIDER,
            type(primary_error).__name__,
        )

    if FALLBACK_PROVIDER == MODEL_PROVIDER:
        logger.error("Fallback provider is the same as the primary provider.")
        return "Đã xảy ra lỗi trong quá trình tạo câu trả lời."

    try:
        answer = _generate_with_provider(FALLBACK_PROVIDER, prompt, FALLBACK_CONFIG)
        logger.info("Answer generated by fallback provider successfully.")
        return answer
    except Exception as fallback_error:
        logger.error(
            "Fallback LLM provider failed. provider=%s error_type=%s elapsed=%.2fs",
            FALLBACK_PROVIDER,
            type(fallback_error).__name__,
            time.time() - start,
        )
        return "Đã xảy ra lỗi trong quá trình tạo câu trả lời."
