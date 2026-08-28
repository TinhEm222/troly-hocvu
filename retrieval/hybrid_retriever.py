import logging
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import ScoredPoint, SparseVector
from qdrant_client.http.exceptions import ResponseHandlingException

from core.settings_loader import load_settings
from core.schema import RetrievedDocument
from vectorstore.qdrant import get_qdrant_client
from embedding.embedder import embed_texts
from scoring.bm25 import BM25

settings = load_settings()
logger = logging.getLogger("retrieval")

COLLECTION_NAME = settings["vector_database"]["collection_name"]
RETRIEVAL_CONFIG = settings["retrieval"]
TOP_K = RETRIEVAL_CONFIG.get("top_k", 10)
SCORE_THRESHOLD = RETRIEVAL_CONFIG.get("score_threshold", 0.0)
DENSE_WEIGHT = RETRIEVAL_CONFIG.get("dense_weight", 0.6)
BM25_WEIGHT = RETRIEVAL_CONFIG.get("bm25_weight", 0.4)

def hybrid_retrieve(query: str, bm25: BM25) -> List[RetrievedDocument]:
    if not query or not query.strip():
        logger.warning("Empty query received for hybrid retrieval.")
        return []

    try:
        client: QdrantClient = get_qdrant_client()
        dense_vectors = embed_texts([query], is_query=True)
        if not dense_vectors:
            logger.error("Failed to embed query.")
            return []

        query_vector = dense_vectors[0]
        fetch_limit = TOP_K * 3  # lấy dư để rerank

        dense_response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            using="dense",  # specify named vector for hybrid search
            limit=fetch_limit,
            with_payload=True,
            score_threshold=SCORE_THRESHOLD,
        )
        dense_points: list[ScoredPoint] = dense_response.points

        # Truy van THEM tap ung vien tu chinh sparse index trong Qdrant (tu khoa),
        # khong chi dua vao top-k cua dense search. Neu bo qua buoc nay, nhung chunk
        # khop tu khoa/so lieu chinh xac (vd "Điều 15", ten quy dinh cu the) nhung
        # khong nam trong top dense-similarity se KHONG BAO GIO duoc xet toi, du BM25
        # rescoring o duoi co tot den dau - day la nguyen nhan chinh khien chatbot
        # tra loi "khong tim thay" du noi dung thuc su co trong tai lieu.
        sparse_points: list[ScoredPoint] = []
        sparse_query = bm25.sparse_embedder.encode(query)
        if sparse_query["indices"]:
            sparse_response = client.query_points(
                collection_name=COLLECTION_NAME,
                query=SparseVector(
                    indices=sparse_query["indices"],
                    values=sparse_query["values"],
                ),
                using="sparse",
                limit=fetch_limit,
                with_payload=True,
            )
            sparse_points = sparse_response.points

        # Gop 2 tap ung vien (dense + sparse) theo id, khong trung lap.
        merged_points: dict[str, ScoredPoint] = {}
        dense_scores: dict[str, float] = {}
        for point in dense_points:
            pid = str(point.id)
            merged_points[pid] = point
            dense_scores[pid] = point.score
        for point in sparse_points:
            pid = str(point.id)
            merged_points.setdefault(pid, point)

        texts: dict[str, str] = {}
        for pid, point in merged_points.items():
            payload = point.payload or {}
            text = payload.get("text", "")
            if text:
                texts[pid] = text

        raw_bm25_scores: dict[str, float] = {
            pid: bm25.score(query, text) for pid, text in texts.items()
        }

        # Dense score (cosine, thuong ~0-1) va BM25 score (khong gioi han, co the
        # >10) o hai thang do khac nhau hoan toan. Cong truc tiep theo trong so
        # DENSE_WEIGHT/BM25_WEIGHT ma khong chuan hoa se khien mot ben lan at ben
        # kia tuy tung truy van (vd BM25=8 >> dense=0.9), lam ket qua hybrid KHONG
        # phan anh dung ty le trong so cau hinh va co the day chunk sai keyword
        # len top, day la mot nguyen nhan chinh khien chatbot tra loi sai/lac de.
        def _min_max_normalize(scores: dict[str, float]) -> dict[str, float]:
            if not scores:
                return {}
            values = list(scores.values())
            lo, hi = min(values), max(values)
            if hi - lo < 1e-9:
                return {pid: (1.0 if hi > 0 else 0.0) for pid in scores}
            return {pid: (v - lo) / (hi - lo) for pid, v in scores.items()}

        norm_dense_scores = _min_max_normalize(dense_scores)
        norm_bm25_scores = _min_max_normalize(raw_bm25_scores)

        documents: list[RetrievedDocument] = []

        for pid, text in texts.items():
            point = merged_points[pid]
            payload = point.payload or {}

            dense_score = dense_scores.get(pid, 0.0)
            bm25_score = raw_bm25_scores.get(pid, 0.0)
            hybrid_score = (
                DENSE_WEIGHT * norm_dense_scores.get(pid, 0.0)
                + BM25_WEIGHT * norm_bm25_scores.get(pid, 0.0)
            )

            documents.append(
                RetrievedDocument(
                    id=pid,
                    score=hybrid_score,
                    text=text,
                    metadata={
                        **{k: v for k, v in payload.items() if k != "text"},
                        "dense_score": dense_score,
                        "bm25_score": bm25_score,
                    },
                )
            )

        documents.sort(key=lambda d: d.score, reverse=True)
        return documents[:TOP_K]
    
    except ResponseHandlingException as e:
        logger.error(f"Qdrant connection error: {e}")
        raise ConnectionError("Cannot connect to vector database")
    except Exception as e:
        logger.error(f"Error during retrieval: {e}", exc_info=True)
        return []