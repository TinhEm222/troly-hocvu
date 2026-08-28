import logging
import os
import re
import shutil
from pathlib import Path
from datetime import datetime

from pypdf import PdfReader

from core.settings_loader import load_settings
from ingestion.helpers.make_metadata import make_metadata
from ingestion.helpers.split_paragraphs import split_with_overlap

settings = load_settings()
logger = logging.getLogger("ingestion")


try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

OCR_CONFIG = settings.get("ocr", {})
OCR_ENABLED = OCR_CONFIG.get("enabled", True) and fitz is not None and pytesseract is not None
OCR_LANG = OCR_CONFIG.get("lang", "vie+eng")
OCR_DPI = OCR_CONFIG.get("dpi", 300)
OCR_MIN_TEXT_LENGTH = OCR_CONFIG.get("min_text_length", 20)


def _resolve_tesseract_cmd() -> str | None:
    cmd_from_env = os.getenv("TESSERACT_CMD")
    if cmd_from_env and Path(cmd_from_env).is_file():
        return cmd_from_env

    from_path = shutil.which("tesseract")
    if from_path:
        return from_path

    windows_candidates = [
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ]
    for candidate in windows_candidates:
        if candidate.is_file():
            return str(candidate)

    return None


if pytesseract is not None:
    resolved_cmd = _resolve_tesseract_cmd()
    if resolved_cmd:
        pytesseract.pytesseract.tesseract_cmd = resolved_cmd

if OCR_CONFIG.get("enabled", True) and not OCR_ENABLED:
    logger.warning(
        "OCR fallback is disabled: missing 'pymupdf' and/or 'pytesseract' package. "
        "Install them (pip install pymupdf pytesseract) to enable scanned-PDF support."
    )
elif OCR_CONFIG.get("enabled", True) and pytesseract is not None:
    if not shutil.which(pytesseract.pytesseract.tesseract_cmd) and not Path(pytesseract.pytesseract.tesseract_cmd).is_file():
        logger.warning(
            "Tesseract binary was not found. Set TESSERACT_CMD or install Tesseract and add it to PATH."
        )


_ocr_binary_missing = False


def _ocr_page_text(fitz_doc, page_index: int) -> str:
    """Render 1 trang PDF thanh anh va chay Tesseract OCR (dung cho trang scan)."""
    global _ocr_binary_missing
    if fitz_doc is None or not OCR_ENABLED or _ocr_binary_missing:
        return ""
    try:
        page = fitz_doc[page_index]
        zoom = OCR_DPI / 72  # PyMuPDF render mac dinh o 72 DPI
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return pytesseract.image_to_string(img, lang=OCR_LANG)
    except pytesseract.TesseractNotFoundError:
        _ocr_binary_missing = True
        logger.warning(
            "Tesseract OCR binary not found on this machine. Scanned pages will be "
            "skipped. Install it from https://github.com/UB-Mannheim/tesseract."
        )
        return ""
    except Exception as e:
        logger.warning(f"OCR failed on page {page_index + 1}: {e}")
        return ""


CHUNK_SIZE_TOKENS = settings.get("chunking", {}).get("chunk_size", 450)
CHUNK_OVERLAP_TOKENS = settings.get("chunking", {}).get("chunk_overlap", 90)


TOC_LEADER_PATTERN = re.compile(r"\.{4,}\s*\d*")


SPECIAL_CHARS_PATTERN = re.compile(r"[\uf000-\uf8ff\u2022\u25cf\u25aa\u00b7]")


def _loose(*char_groups: str) -> str:
    """
    Noi cac nhom ky tu (hoac lop ky tu thay the) lai voi \\s* xen giua, cho phep
    khoang trang bi chen giua tung ky tu cua 1 tu khoa. Dieu nay giup regex
    chiu duoc loi OCR/dan trang pho bien, vd "Ä i á» u" hoac "ÄIá»€U" (dinh sat
    vao so, khong co khoang trang) van duoc coi la cung 1 tu khoa "Äiá»u".
    """
    return r"\s*".join(char_groups)


# Cac pattern duoi day duoc xay dung "long leo" (loose) ve khoang trang giua
# tung ky tu cua tu khoa, va khong bat buoc co khoang trang truoc so thu tu
# (vd "Äiá»u 15", "Ä i á» u 15", "ÄIá»€U15" deu khop).
PHAN_RE = re.compile(
    rf"^\s*{_loose('P', 'H', '[áº¦A]', 'N')}\s*\.?\s*([IVXLCDM]+|\d+)\b\.?\s*(.*)$",
    re.IGNORECASE,
)
CHUONG_RE = re.compile(
    rf"^\s*{_loose('C', 'H', '[Æ¯U]', 'Æ ', 'N', 'G')}\s*\.?\s*([IVXLCDM]+|\d+)\b\.?\s*(.*)$",
    re.IGNORECASE,
)
MUC_RE = re.compile(
    rf"^\s*{_loose('M', '[á»¤U]', 'C')}\s*\.?\s*([IVXLCDM]+|\d+)\b\.?\s*(.*)$",
    re.IGNORECASE,
)
# Muc dang so La Ma tong quat (vd: "VI. QUY CHáº¾ ÄĂ€O Táº O Äáº I Há»ŒC") - chi coi la
# heading neu phan tieu de chu yeu la CHU HOA (giam nguy co bat nham cau van thuong).
ROMAN_SECTION_RE = re.compile(r"^\s*([IVXLCDM]{1,6})\s*\.\s*(.{2,100})$")
DIEU_RE = re.compile(
    rf"^\s*{_loose('[ÄD]', 'I', '[á»Ăª]', 'U')}\s*\.?\s*(\d+)\s*\.?\s*(.*)$",
    re.IGNORECASE,
)
# Khoan: dong so dau muc truc tiep ben duoi 1 Dieu, vd "1. Quy che nay ap dung..."
KHOAN_RE = re.compile(r"^\s*(\d{1,2})\s*\.\s*(\S.*)$")


def _looks_like_heading(title: str) -> bool:
    letters = [c for c in title if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio > 0.6


def _is_toc_page(text: str, min_matches: int = 4) -> bool:
    """Phat hien trang muc luc dua tren mat do cac dong co leader dots."""
    return len(TOC_LEADER_PATTERN.findall(text)) >= min_matches


def _is_page_number_line(line: str, page_number: int) -> bool:
    """Nhan dien dong header/footer chi chua so trang (vd: '72')."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped == str(page_number):
        return True
    return bool(re.fullmatch(r"\d{1,4}", stripped))


def _clean_line(line: str) -> str:
    """Tien xu ly 1 dong text: bo ky tu dac biet, chuan hoa khoang trang du thua."""
    line = SPECIAL_CHARS_PATTERN.sub("-", line)
    line = TOC_LEADER_PATTERN.sub(" ", line)
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def extract_lines_from_pdf(file_path: Path) -> list[tuple[int, str]]:
    
    lines_out: list[tuple[int, str]] = []

    try:
        reader = PdfReader(str(file_path))
    except Exception as e:
        logger.error(f"Failed to open PDF {file_path}: {e}")
        return []

    fitz_doc = None
    if OCR_ENABLED:
        try:
            fitz_doc = fitz.open(str(file_path))
        except Exception as e:
            logger.warning(f"Could not open {file_path} with PyMuPDF for OCR fallback: {e}")

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            raw_text = page.extract_text() or ""
        except Exception as e:
            logger.warning(f"Failed to extract text from page {page_number} of {file_path}: {e}")
            continue

        if len(raw_text.strip()) < OCR_MIN_TEXT_LENGTH:
            ocr_text = _ocr_page_text(fitz_doc, page_number - 1)
            if ocr_text.strip():
                logger.info(
                    f"Page {page_number} of {file_path.name} has little/no text layer "
                    f"({len(raw_text.strip())} chars) - used OCR fallback ({len(ocr_text.strip())} chars)."
                )
                raw_text = ocr_text

        if not raw_text.strip():
            continue

        if _is_toc_page(raw_text):
            logger.info(f"Skipping table-of-contents-like page {page_number} of {file_path.name}")
            continue

        for idx, raw_line in enumerate(raw_text.split("\n")):
            # Header/footer: dong dau tien cua trang thuong chi la so trang
            if idx == 0 and _is_page_number_line(raw_line, page_number):
                continue

            cleaned = _clean_line(raw_line)
            if not cleaned:
                continue

            # Bo cac dong chi con lai la so (footer/so trang lac cho o cuoi trang)
            if re.fullmatch(r"\d{1,4}", cleaned):
                continue

            lines_out.append((page_number, cleaned))

    if fitz_doc is not None:
        fitz_doc.close()

    return lines_out


def _build_structured_chunks(lines: list[tuple[int, str]], source_name: str) -> list[dict]:
    
    created_at = datetime.utcnow().isoformat()
    chunks: list[dict] = []

    state = {"phan": None, "chuong": None, "muc": None, "dieu": None, "khoan": None}
    buffer: list[str] = []
    buffer_start_page: int | None = None
    # Neu buffer hien tai chi chua dong tieu de (Phan/Chuong/Muc/Dieu/Khoan) va
    # chua co noi dung ben duoi, khong tao chunk rieng chi co tieu de (tranh phan
    # manh du lieu) ma giu lai lam "pending_prefix" de gop vao chunk ke tiep.
    is_heading_only = False
    pending_prefix: str | None = None

    def flush():
        nonlocal buffer, buffer_start_page, is_heading_only, pending_prefix
        text = " ".join(buffer).strip()
        buffer = []
        heading_only = is_heading_only
        is_heading_only = False

        if not text:
            buffer_start_page = None
            return

        if heading_only:
            pending_prefix = f"{pending_prefix} {text}".strip() if pending_prefix else text
            buffer_start_page = None
            return

        if pending_prefix:
            text = f"{pending_prefix} {text}".strip()
            pending_prefix = None

        parts = split_with_overlap(
            text,
            max_tokens=CHUNK_SIZE_TOKENS,
            overlap_tokens=CHUNK_OVERLAP_TOKENS,
        )
        total_parts = len(parts)

        for part_idx, part_text in enumerate(parts, start=1):
            metadata_extra = {
                "type": "pdf_document",
                "source": source_name,
                "created_at": created_at,
                "language": "vi",
                "page": buffer_start_page,
                "phan": state["phan"],
                "chuong": state["chuong"],
                "muc": state["muc"],
                "dieu": state["dieu"],
                "khoan": state["khoan"],
            }
            if total_parts > 1:
                metadata_extra["chunk_part"] = f"{part_idx}/{total_parts}"

            chunks.append({
                "text": part_text,
                "metadata": make_metadata(metadata_extra, chunk_type="pdf_structured"),
            })

        buffer_start_page = None

    for page_number, line in lines:
        m_phan = PHAN_RE.match(line)
        m_chuong = CHUONG_RE.match(line)
        m_muc = MUC_RE.match(line)
        m_roman = None
        if not m_muc:
            rm = ROMAN_SECTION_RE.match(line)
            if rm and _looks_like_heading(rm.group(2)):
                m_roman = rm
        m_dieu = DIEU_RE.match(line)
        m_khoan = KHOAN_RE.match(line) if state["dieu"] else None

        if m_phan:
            flush()
            label, title = m_phan.group(1), m_phan.group(2).strip()
            state["phan"] = f"Pháº§n {label}" + (f" - {title}" if title else "")
            state["chuong"] = None
            state["muc"] = None
            state["dieu"] = None
            state["khoan"] = None
            buffer = [line]
            buffer_start_page = page_number
            is_heading_only = True
            continue

        if m_chuong:
            flush()
            label, title = m_chuong.group(1), m_chuong.group(2).strip()
            state["chuong"] = f"ChÆ°Æ¡ng {label}" + (f" - {title}" if title else "")
            state["muc"] = None
            state["dieu"] = None
            state["khoan"] = None
            buffer = [line]
            buffer_start_page = page_number
            is_heading_only = True
            continue

        if m_muc or m_roman:
            flush()
            match = m_muc or m_roman
            label, title = match.group(1), match.group(2).strip()
            state["muc"] = f"Má»¥c {label}" + (f" - {title}" if title else "")
            state["dieu"] = None
            state["khoan"] = None
            buffer = [line]
            buffer_start_page = page_number
            is_heading_only = True
            continue

        if m_dieu:
            flush()
            number, title = m_dieu.group(1), m_dieu.group(2).strip()
            state["dieu"] = f"Äiá»u {number}" + (f" - {title}" if title else "")
            state["khoan"] = None
            buffer = [line]
            buffer_start_page = page_number
            is_heading_only = True
            continue

        if m_khoan:
            flush()
            number = m_khoan.group(1)
            state["khoan"] = f"Khoáº£n {number}"
            buffer = [line]
            buffer_start_page = page_number
            is_heading_only = True
            continue

        # Dong noi dung thuong: gop vao buffer cua don vi (dieu/khoan/muc) hien tai
        buffer.append(line)
        is_heading_only = False
        if buffer_start_page is None:
            buffer_start_page = page_number

    flush()  # flush phan noi dung con lai cuoi tai lieu

    return chunks


def chunk_pdf_documents(document_paths: list[Path]):
    pdf_files = sorted(Path(path) for path in document_paths)

    if not pdf_files:
        logger.warning("No managed PDF files found for ingestion.")
        return []

    all_chunks: list[dict] = []

    for pdf_path in pdf_files:
        logger.info(f"Processing PDF: {pdf_path.name}")
        lines = extract_lines_from_pdf(pdf_path)

        if not lines:
            logger.warning(f"No extractable text found in {pdf_path.name}")
            continue

        chunks = _build_structured_chunks(lines, pdf_path.name)
        logger.info(f"Created {len(chunks)} structured chunks from {pdf_path.name}")
        all_chunks.extend(chunks)

    logger.info(f"Total PDF chunks created: {len(all_chunks)}")
    return all_chunks


if __name__ == "__main__":
    from ingestion.pipeline import _get_managed_document_paths

    result = chunk_pdf_documents(_get_managed_document_paths())
    print(f"Created {len(result)} chunks from PDF documents.")