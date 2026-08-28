import logging

logger = logging.getLogger("ingestion")

def split_paragraphs(text, max_len=400):
    if not text:
        logger.warning("Empty text provided to split_paragraphs")
        return []

    sentences = text.split(". ")
    out = []
    buf = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Trường hợp 1: câu dài hơn max_len → cắt thông minh
        while len(sentence) > max_len:
            # tìm dấu chấm gần nhất trước max_len
            cut = sentence.rfind(". ", 0, max_len)

            if cut == -1:
                # fallback: không có dấu chấm → cắt cứng
                cut = max_len

            chunk = sentence[:cut].strip()
            if chunk:
                out.append(chunk)

            sentence = sentence[cut:].strip()

        # Trường hợp 2: ghép câu vào buffer
        if len(buf) + len(sentence) + 2 <= max_len:
            buf += sentence + ". "
        else:
            out.append(buf.strip())
            buf = sentence + ". "

    # flush buffer cuối
    if buf:
        out.append(buf.strip())

    return out


def split_with_overlap(text: str, max_tokens: int = 450, overlap_tokens: int = 90) -> list[str]:
    """
    Chia 1 doan text (thuong la 1 muc/dieu/khoan da qua dai) thanh nhieu chunk nho hon
    theo so luong token, co overlap giua cac chunk lien tiep de duy tri tinh lien tuc
    cua ngu canh (tranh cat dut y giua chung khi mot dieu/khoan qua dai).

    "Token" o day duoc xap xi bang so tu (tach theo khoang trang) de khong phu thuoc
    vao 1 thu vien tokenizer rieng (du dung du de kiem soat kich thuoc chunk dua vao LLM).

    Neu text ngan hon max_tokens thi tra ve nguyen ban (chi 1 chunk duy nhat).
    """
    if not text or not text.strip():
        return []

    words = text.split()
    if len(words) <= max_tokens:
        return [text.strip()]

    if overlap_tokens >= max_tokens:
        overlap_tokens = max_tokens // 2

    step = max(max_tokens - overlap_tokens, 1)
    chunks = []
    start = 0

    while start < len(words):
        end = start + max_tokens
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start += step

    return chunks
