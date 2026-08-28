from core.settings_loader import load_settings
from unittest.mock import patch


def test_default_llm_timeout_allows_cold_start_generation():
    settings = load_settings()

    assert settings["llm"]["timeout"] >= 120


def test_gemini_is_primary_and_ollama_is_fallback():
    settings = load_settings()
    llm = settings["llm"]

    assert llm["provider"] == "gemini"
    assert llm["model_name"] == "gemini-3.5-flash-lite"
    assert llm["gemini_api_key_env"] == "GEMINI_API_KEY"
    assert llm["fallback"]["provider"] == "ollama"
    assert llm["fallback"]["model_name"] == "qwen2.5:3b"


def test_environment_can_override_gemini_and_fallback_settings():
    env = {
        "LLM_PROVIDER": "gemini",
        "LLM_MODEL_NAME": "gemini-test-model",
        "LLM_FALLBACK_MODEL_NAME": "qwen-test-model",
        "OLLAMA_BASE_URL": "http://ollama.test:11434",
    }
    with patch.dict("os.environ", env):
        settings = load_settings()

    assert settings["llm"]["provider"] == "gemini"
    assert settings["llm"]["model_name"] == "gemini-test-model"
    assert settings["llm"]["fallback"]["model_name"] == "qwen-test-model"
    assert settings["llm"]["fallback"]["base_url"] == "http://ollama.test:11434"
