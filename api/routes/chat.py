import json
import logging
import os
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from retrieval.hybrid_retriever import hybrid_retrieve
from core.startup import get_bm25, get_reranker
from llm.generator import (
    generate_answer,
    generate_out_of_scope_answer,
    stream_answer,
    stream_out_of_scope_answer,
)
from core.settings_loader import load_settings
from core.db import get_db
from core.deps import get_current_user
from core.models import ChatMessage, ChatSession, User
from llm.intent import get_basic_response

settings = load_settings()
logger = logging.getLogger("chat")
router = APIRouter()

MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "500"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RERRANKING_TOP_K = settings.get("reranking", {}).get("top_k", 5)
MIN_RELEVANCE_SCORE = settings.get("reranking", {}).get("min_relevance_score", 0.0)

NO_ANSWER_MESSAGE = (
    "Xin lỗi, tôi không tìm thấy thông tin này trong tài liệu hiện có của nhà trường. "
    "Bạn vui lòng liên hệ Phòng Đào tạo hoặc bộ phận liên quan để được hỗ trợ chính xác hơn."
)
def _is_relevant(documents) -> bool:
    """Kiểm tra tài liệu truy xuất có đủ liên quan không.

    Chỉ dùng để quyết định có đính kèm "nguồn tham khảo" trong response hay không,
    KHÔNG dùng để chặn LLM trả lời (câu hỏi giao tiếp thông thường vẫn cần được trả lời bình thường).
    """
    if not documents:
        return False
    return documents[0].score >= MIN_RELEVANCE_SCORE

sessions = {}

# Simple in-memory rate limiting
rate_limit_storage = {}  # {ip: [timestamps]}

def check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit"""
    current_time = time.time()
    minute_ago = current_time - 60

    if client_ip not in rate_limit_storage:
        rate_limit_storage[client_ip] = []

    # Remove timestamps older than 1 minute
    rate_limit_storage[client_ip] = [
        ts for ts in rate_limit_storage[client_ip] if ts > minute_ago
    ]

    # Check if exceeded limit
    if len(rate_limit_storage[client_ip]) >= RATE_LIMIT_PER_MINUTE:
        return False

    # Add current request
    rate_limit_storage[client_ip].append(current_time)
    return True

class ChatRequest(BaseModel):
    """Chat request model"""
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_LENGTH, description="User's question")
    session_id: Optional[str] = Field(None, description="Session ID for conversation tracking")

class ChatResponse(BaseModel):
    """Chat response model"""
    answer: str = Field(..., description="Bot's answer")
    sources: list = Field(default_factory=list, description="Source documents")
    session_id: str = Field(..., description="Session ID")


def format_sse_event(event: str, payload: dict) -> str:
    """Serialize one JSON Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class ChatSessionOut(BaseModel):
    """A chat session summary (for the chat history sidebar)"""
    id: str
    title: str
    created_at: str
    updated_at: str


class ChatMessageOut(BaseModel):
    """A single persisted chat message"""
    role: str
    content: str
    sources: list = Field(default_factory=list)
    stage_history: list = Field(default_factory=list)
    created_at: str


def _truncate_title(text: str, max_len: int = 60) -> str:
    text = text.strip()
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    req: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Rate limiting check
    client_ip = req.client.host if req.client else "unknown"
    if not check_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(
            status_code=429,
            detail=f"Tốc độ request quá nhanh. Vui lòng thử lại sau. (Max {RATE_LIMIT_PER_MINUTE} requests/minute)"
        )

    question = request.query.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Vui lòng nhập câu hỏi.")

    # Resolve existing session (must belong to the current user) or create a new one
    if request.session_id:
        chat_session = db.query(ChatSession).filter(
            ChatSession.id == request.session_id,
            ChatSession.user_id == current_user.id,
        ).first()
        if chat_session is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện.")
    else:
        chat_session = ChatSession(user_id=current_user.id, title=_truncate_title(question))
        db.add(chat_session)
        db.commit()
        db.refresh(chat_session)

    session_id = chat_session.id

    logger.info(f"Session {session_id}: Received question: {question}")

    try:
        basic_answer = get_basic_response(question)
        if basic_answer:
            db.add(ChatMessage(session_id=session_id, role="user", content=question))
            db.add(ChatMessage(
                session_id=session_id,
                role="assistant",
                content=basic_answer,
                sources="[]",
            ))
            chat_session.updated_at = datetime.utcnow()
            db.commit()
            return ChatResponse(answer=basic_answer, sources=[], session_id=session_id)

        # Get BM25 and Reranker from startup
        bm25 = get_bm25()
        reranker = get_reranker()

        if bm25 is None:
            logger.error(f"Session {session_id}: BM25 not initialized!")
            raise HTTPException(
                status_code=503,
                detail="Hệ thống chưa sẵn sàng. Vui lòng thử lại sau."
            )

        # Step 1: Hybrid retrieval (Dense + BM25)
        logger.info(f"Session {session_id}: Running hybrid retrieval...")
        documents = hybrid_retrieve(question, bm25)

        if not documents:
            logger.warning(f"Session {session_id}: No documents retrieved")
            db.add(ChatMessage(session_id=session_id, role="user", content=question))
            answer = NO_ANSWER_MESSAGE
            db.add(ChatMessage(session_id=session_id, role="assistant", content=answer, sources="[]"))
            chat_session.updated_at = datetime.utcnow()
            db.commit()
            return ChatResponse(
                answer=answer,
                sources=[],
                session_id=session_id
            )

        logger.info(f"Session {session_id}: Retrieved {len(documents)} documents from hybrid search")

        # Step 2: Reranking (if available)
        if reranker is not None:
            logger.info(f"Session {session_id}: Reranking documents...")
            documents = reranker.rerank(question, documents, top_k=RERRANKING_TOP_K)
            logger.info(f"Session {session_id}: After reranking: {len(documents)} documents")
        else:
            logger.warning(f"Session {session_id}: Reranker not available, using hybrid scores only")
            if RERRANKING_TOP_K is not None:
                documents = documents[:RERRANKING_TOP_K]

        relevant_documents = _is_relevant(documents)
        if relevant_documents:
            context = "\n\n".join(
                f"[{i+1}] {doc.text}\n(Nguồn: {doc.metadata})"
                for i, doc in enumerate(documents)
            )
            logger.info(f"Session {session_id}: Retrieved {len(documents)} relevant documents")
            answer = generate_answer(context, question)
            logger.info(f"Session {session_id}: Generated answer successfully")
            sources = [
                {
                    "text": doc.text[:200] + "..." if len(doc.text) > 200 else doc.text,
                    "metadata": doc.metadata,
                    "score": doc.score
                }
                for doc in documents
            ]
        else:
            logger.info(f"Session {session_id}: Documents are outside the supported scope")
            answer = generate_out_of_scope_answer(question)
            sources = []

        db.add(ChatMessage(session_id=session_id, role="user", content=question))
        db.add(ChatMessage(
            session_id=session_id,
            role="assistant",
            content=answer,
            sources=json.dumps(sources, ensure_ascii=False),
        ))
        chat_session.updated_at = datetime.utcnow()
        db.commit()

        return ChatResponse(
            answer=answer,
            sources=sources,
            session_id=session_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session {session_id}: Error in chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn. Vui lòng thử lại sau."
        )


@router.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    req: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream a RAG answer as SSE while preserving the JSON chat endpoint."""
    client_ip = req.client.host if req.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Tốc độ request quá nhanh. Vui lòng thử lại sau. (Max {RATE_LIMIT_PER_MINUTE} requests/minute)",
        )

    question = request.query.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Vui lòng nhập câu hỏi.")

    if request.session_id:
        chat_session = db.query(ChatSession).filter(
            ChatSession.id == request.session_id,
            ChatSession.user_id == current_user.id,
        ).first()
        if chat_session is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện.")
    else:
        chat_session = ChatSession(user_id=current_user.id, title=_truncate_title(question))
        db.add(chat_session)
        db.commit()
        db.refresh(chat_session)

    session_id = chat_session.id
    db.add(ChatMessage(session_id=session_id, role="user", content=question))
    db.commit()

    def event_stream():
        chunks = []
        stage_history = []

        def start_stage(stage: str) -> None:
            stage_history.append({"id": stage, "status": "done"})

        try:
            basic_answer = get_basic_response(question)
            if basic_answer:
                start_stage("generating")
                yield format_sse_event(
                    "status",
                    {
                        "stage": "generating",
                        "message": "Đang chuẩn bị câu trả lời cơ bản…",
                        "session_id": session_id,
                    },
                )
                yield format_sse_event(
                    "meta",
                    {"session_id": session_id, "sources": [], "intent": "basic"},
                )
                chunks.append(basic_answer)
                yield format_sse_event("token", {"text": basic_answer})
                db.add(ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=basic_answer,
                    sources="[]",
                    message_metadata=json.dumps({"stage_history": stage_history}, ensure_ascii=False),
                ))
                chat_session.updated_at = datetime.utcnow()
                db.commit()
                yield format_sse_event(
                    "done",
                    {"session_id": session_id, "sources": [], "stages": stage_history},
                )
                return

            # Gửi trạng thái trước embedding/Qdrant/reranking để UI không bị đứng im.
            start_stage("retrieving")
            yield format_sse_event(
                "status",
                {
                    "stage": "retrieving",
                    "message": "Đang tìm tài liệu liên quan…",
                    "session_id": session_id,
                },
            )

            bm25 = get_bm25()
            reranker = get_reranker()
            if bm25 is None:
                raise RuntimeError("BM25 is not initialized")

            documents = hybrid_retrieve(question, bm25)
            start_stage("reranking")
            yield format_sse_event(
                "status",
                {
                    "stage": "reranking",
                    "message": "Đang kiểm tra độ phù hợp của tài liệu…",
                    "session_id": session_id,
                },
            )

            if documents:
                if reranker is not None:
                    documents = reranker.rerank(question, documents, top_k=RERRANKING_TOP_K)
                elif RERRANKING_TOP_K is not None:
                    documents = documents[:RERRANKING_TOP_K]

            sources = []
            context = ""
            relevant_documents = bool(documents) and _is_relevant(documents)
            if relevant_documents:
                context = "\n\n".join(
                    f"[{i+1}] {doc.text}\n(Nguồn: {doc.metadata})"
                    for i, doc in enumerate(documents)
                )
                sources = [
                    {
                        "text": doc.text[:200] + "..." if len(doc.text) > 200 else doc.text,
                        "metadata": doc.metadata,
                        "score": doc.score,
                    }
                    for doc in documents
                ]

            yield format_sse_event("meta", {"session_id": session_id, "sources": sources})
            start_stage("generating")
            yield format_sse_event(
                "status",
                {
                    "stage": "generating",
                    "message": "Đang soạn câu trả lời…",
                    "session_id": session_id,
                },
            )

            if relevant_documents:
                for chunk in stream_answer(context, question):
                    chunks.append(chunk)
                    yield format_sse_event("token", {"text": chunk})
            else:
                if documents:
                    for chunk in stream_out_of_scope_answer(question):
                        chunks.append(chunk)
                        yield format_sse_event("token", {"text": chunk})
                else:
                    chunks.append(NO_ANSWER_MESSAGE)
                    yield format_sse_event("token", {"text": NO_ANSWER_MESSAGE})

            answer = "".join(chunks).strip()
            if not answer:
                raise RuntimeError("empty streamed answer")

            db.add(ChatMessage(
                session_id=session_id,
                role="assistant",
                content=answer,
                sources=json.dumps(sources, ensure_ascii=False),
                message_metadata=json.dumps({"stage_history": stage_history}, ensure_ascii=False),
            ))
            chat_session.updated_at = datetime.utcnow()
            db.commit()
            yield format_sse_event(
                "done",
                {
                    "session_id": session_id,
                    "sources": sources,
                    "stages": stage_history,
                },
            )
        except Exception as error:
            db.rollback()
            logger.error("Stream processing failed. error_type=%s", type(error).__name__, exc_info=True)
            yield format_sse_event(
                "error",
                {"message": "Xin lỗi, đã xảy ra lỗi khi tạo câu trả lời. Vui lòng thử lại sau."},
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/sessions", response_model=list[ChatSessionOut])
async def list_chat_sessions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lịch sử chat của người dùng hiện tại, mới nhất trước."""
    chat_sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [
        ChatSessionOut(
            id=s.id,
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in chat_sessions
    ]


@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def get_chat_session_messages(
    session_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Lấy toàn bộ tin nhắn của 1 cuộc trò chuyện cũ để tiếp tục chat."""
    chat_session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == current_user.id
    ).first()
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện.")

    result = []
    for message in chat_session.messages:
        try:
            parsed_sources = json.loads(message.sources) if message.sources else []
        except (TypeError, ValueError):
            parsed_sources = []
        try:
            parsed_metadata = json.loads(message.message_metadata) if message.message_metadata else {}
        except (TypeError, ValueError):
            parsed_metadata = {}
        result.append(
            ChatMessageOut(
                role=message.role,
                content=message.content,
                sources=parsed_sources,
                stage_history=parsed_metadata.get("stage_history", []),
                created_at=message.created_at.isoformat(),
            )
        )
    return result


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Xóa 1 cuộc trò chuyện (và toàn bộ tin nhắn liên quan) của người dùng hiện tại."""
    chat_session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == current_user.id
    ).first()
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện.")

    db.delete(chat_session)
    db.commit()
    return {"message": "Đã xóa cuộc trò chuyện."}


def chat(question: str) -> str:
    """Legacy CLI chat function - now uses hybrid retrieval"""
    if not question or not question.strip():
        logger.warning("Empty question received")
        return "Vui lòng nhập câu hỏi."

    if len(question) > MAX_QUERY_LENGTH:
        logger.warning(f"Query too long: {len(question)} characters")
        return f"Câu hỏi quá dài. Vui lòng giới hạn dưới {MAX_QUERY_LENGTH} ký tự."

    basic_answer = get_basic_response(question)
    if basic_answer:
        return basic_answer

    logger.info(f"Received question: {question}")

    try:
        bm25 = get_bm25()
        reranker = get_reranker()

        if bm25 is None:
            return "Hệ thống chưa sẵn sàng. Vui lòng thử lại sau."

        # Hybrid retrieval
        documents = hybrid_retrieve(question, bm25)

        if not documents:
            logger.warning("No documents retrieved for the question")
            return NO_ANSWER_MESSAGE

        # Reranking
        if reranker is not None:
            documents = reranker.rerank(question, documents, top_k=RERRANKING_TOP_K)
        elif RERRANKING_TOP_K is not None:
            documents = documents[:RERRANKING_TOP_K]

        context = "\n\n".join(f"[{i+1}] {doc.text}\n(Nguồn: {doc.metadata})" for i, doc in enumerate(documents))
        logger.info(f"Retrieved {len(documents)} documents for the question")

        if not _is_relevant(documents):
            logger.info("Retrieved documents are outside the supported scope")
            return generate_out_of_scope_answer(question)

        answer = generate_answer(context, question)
        logger.info("Generated answer successfully")
        return answer

    except Exception as e:
        logger.error(f"Error in chat function: {e}", exc_info=True)
        return "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn. Vui lòng thử lại sau."
