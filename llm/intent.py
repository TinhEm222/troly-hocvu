"""Small, deterministic intent helpers used before RAG retrieval."""

import re


GREETING_RESPONSE = (
    "Hello bạn sinh viên! Mình là trợ lý học vụ CTUT, chuyên trị các câu hỏi học hành "
    "để bạn đỡ phải solo với đống quy chế dài như sớ. Mình hỗ trợ quy chế đào tạo, học phí, "
    "chuẩn đầu ra, điều kiện tốt nghiệp và các tài liệu chính thức của nhà trường."
)
THANKS_RESPONSE = (
    "Không có gì, bạn sinh viên. Nhiệm vụ của mình là giúp chuyện học hành bớt đau đầu, "
    "chứ không để bạn vật lộn một mình với những văn bản dài hơn danh sách deadline."
)
CAPABILITIES_RESPONSE = (
    "Mình hỗ trợ tra cứu thông tin học vụ cho sinh viên CTUT: quy chế đào tạo, học phí, "
    "chuẩn đầu ra, điều kiện tốt nghiệp và các quy định trong tài liệu chính thức. "
    "Nói ngắn gọn là giúp bạn né cảnh đọc 50 trang văn bản chỉ để tìm đúng một dòng."
)


def _normalize(question: str) -> str:
    normalized = (question or "").casefold().strip()
    normalized = re.sub(r"[^\w\sÀ-ỹ]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def get_basic_response(question: str) -> str | None:
    """Return a direct response for safe small-talk intents, otherwise None."""
    normalized = _normalize(question)
    if not normalized:
        return None

    if re.fullmatch(
        r"(?:hello|hi|hey|xin chào|chào)(?: bạn| cậu| chatbot| trợ lý| bạn ơi)?",
        normalized,
    ):
        return GREETING_RESPONSE

    if normalized.startswith(("cảm ơn", "cam on", "thanks", "thank you")):
        return THANKS_RESPONSE

    if normalized in {
        "bạn có thể giúp gì",
        "ban co the giup gi",
        "bạn hỗ trợ gì",
        "ban ho tro gi",
        "bạn làm được gì",
        "ban lam duoc gi",
        "bạn có thể hỗ trợ gì",
        "ban co the ho tro gi",
        "chức năng của bạn là gì",
        "chuc nang cua ban la gi",
    }:
        return CAPABILITIES_RESPONSE

    return None
