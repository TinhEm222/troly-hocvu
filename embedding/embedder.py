import logging
from sentence_transformers import SentenceTransformer

from core.settings_loader import load_settings

settings = load_settings()
logger = logging.getLogger("embedding")

EMBEDDING_CONFIG = settings["embedding"]
EMBEDDING_MODEL = EMBEDDING_CONFIG["model"]

_model = None

def get_model() -> SentenceTransformer:
    global _model # ghi vao bien toan cuc
    if _model is None: # neu chua co model thi load, chi load 1 lan
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_CONFIG.get("device", "cpu"))
    return _model

def embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]]:
    """
    Cac model ho E5 (vd intfloat/multilingual-e5-small) BAT BUOC phai them tien to
    "query: " cho cau hoi va "passage: " cho van ban duoc luu tru/tim kiem, neu khong
    embedding se lech khong gian vector va do chinh xac retrieval giam manh (day la
    yeu cau chinh thuc tu model card cua E5, khong phai tuy chon).
    is_query=True  -> dung khi embed cau hoi cua nguoi dung (retrieval).
    is_query=False -> dung khi embed chunk/tai lieu de luu vao Qdrant (ingestion).
    """
    if not texts:
        logger.warning("No texts provided for embedding.")
        return []

    prefix = "query: " if is_query else "passage: "
    prefixed_texts = [f"{prefix}{text}" for text in texts]

    model = get_model()
    embeddings = model.encode(prefixed_texts, normalize_embeddings=True, convert_to_tensor=False).tolist() # chuyen thanh list de luu vao qdrant BAT BUOC
    logger.info(f"Completed embedding texts {len(texts)} (is_query={is_query}).")
    return embeddings
    