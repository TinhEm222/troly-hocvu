import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import api.routes.chat as chat_module
from api.routes.chat import (
    ChatRequest,
    chat,
    chat_endpoint,
    chat_stream_endpoint,
    format_sse_event,
)

class TestChatRoute(unittest.TestCase):

    def test_sse_event_is_valid_and_terminated(self):
        event = format_sse_event("token", {"text": "Xin chào"})

        self.assertTrue(event.startswith("event: token\n"))
        self.assertTrue(event.endswith("\n\n"))
        payload = json.loads(event.split("data: ", 1)[1].strip())
        self.assertEqual(payload, {"text": "Xin chào"})

    def test_sse_status_event_has_safe_stage_and_message(self):
        event = format_sse_event(
            "status",
            {"stage": "retrieving", "message": "Đang tìm tài liệu liên quan…"},
        )

        self.assertIn("event: status\n", event)
        self.assertIn('"stage": "retrieving"', event)
        self.assertIn("Đang tìm tài liệu", event)

    def test_empty_question(self):
        """Test xử lý câu hỏi rỗng"""
        result = chat("")
        self.assertEqual(result, "Vui lòng nhập câu hỏi.")

    def test_whitespace_question(self):
        """Test xử lý câu hỏi chỉ có khoảng trắng"""
        result = chat("   ")
        self.assertEqual(result, "Vui lòng nhập câu hỏi.")

    def test_query_too_long(self):
        """Test xử lý câu hỏi quá dài"""
        long_query = "a" * 600  # > 500 chars
        result = chat(long_query)
        self.assertIn("quá dài", result)

    @patch('api.routes.chat.get_bm25')
    @patch('api.routes.chat.hybrid_retrieve')
    def test_no_documents_retrieved(self, mock_retrieve, mock_get_bm25):
        """Test khi không tìm thấy documents"""
        mock_get_bm25.return_value = Mock()
        mock_retrieve.return_value = []
        result = chat("test question")
        self.assertIn("không tìm thấy", result)

    @patch('api.routes.chat.get_reranker')
    @patch('api.routes.chat.get_bm25')
    @patch('api.routes.chat.hybrid_retrieve')
    @patch('api.routes.chat.generate_answer')
    def test_successful_chat(self, mock_generate, mock_retrieve, mock_get_bm25, mock_get_reranker):
        """Test flow thành công"""
        mock_get_bm25.return_value = Mock()
        mock_get_reranker.return_value = None

        # Mock retrieved documents
        mock_doc = Mock()
        mock_doc.text = "Test content"
        mock_doc.metadata = {"source": "test"}
        mock_doc.score = 5.0
        mock_retrieve.return_value = [mock_doc]

        # Mock generated answer
        mock_generate.return_value = "Test answer"

        result = chat("test question")
        self.assertEqual(result, "Test answer")
        mock_retrieve.assert_called_once()
        mock_generate.assert_called_once()

    @patch('api.routes.chat.get_reranker')
    @patch('api.routes.chat.get_bm25')
    @patch('api.routes.chat.hybrid_retrieve')
    @patch('api.routes.chat.generate_answer', return_value='Test answer')
    def test_reranking_keeps_all_retrieved_documents(
        self, mock_generate, mock_retrieve, mock_get_bm25, mock_get_reranker
    ):
        mock_get_bm25.return_value = Mock()
        mock_reranker = Mock()
        mock_get_reranker.return_value = mock_reranker
        documents = [
            SimpleNamespace(text=f'Content {index}', metadata={'source': f'test-{index}'}, score=1.0)
            for index in range(6)
        ]
        mock_retrieve.return_value = documents
        mock_reranker.rerank.return_value = documents

        chat('test question')

        mock_reranker.rerank.assert_called_once_with('test question', documents, top_k=5)

    @patch('api.routes.chat.get_bm25')
    @patch('api.routes.chat.hybrid_retrieve')
    def test_exception_handling(self, mock_retrieve, mock_get_bm25):
        """Test xử lý exception"""
        mock_get_bm25.return_value = Mock()
        mock_retrieve.side_effect = Exception("Test error")
        result = chat("test question")
        self.assertIn("lỗi", result.lower())

    @patch("api.routes.chat.get_basic_response", return_value="Hello bạn sinh viên!")
    @patch("api.routes.chat.hybrid_retrieve")
    @patch("api.routes.chat.get_bm25")
    def test_basic_chat_skips_retrieval(
        self, mock_get_bm25, mock_retrieve, mock_basic
    ):
        db = Mock()
        db.refresh.side_effect = lambda session: setattr(session, "id", "basic-session")
        request = SimpleNamespace(client=SimpleNamespace(host="test-client"))
        user = SimpleNamespace(id=1)

        response = asyncio.run(
            chat_endpoint(ChatRequest(query="Hello"), request, user, db)
        )

        self.assertEqual(response.answer, "Hello bạn sinh viên!")
        self.assertEqual(response.sources, [])
        mock_get_bm25.assert_not_called()
        mock_retrieve.assert_not_called()

    @patch("api.routes.chat.get_basic_response", return_value="Hello bạn sinh viên!")
    @patch("api.routes.chat.hybrid_retrieve")
    def test_basic_stream_skips_retrieval_and_has_no_sources(
        self, mock_retrieve, mock_basic
    ):
        db = Mock()
        db.refresh.side_effect = lambda session: setattr(session, "id", "basic-session")
        request = SimpleNamespace(client=SimpleNamespace(host="test-client"))
        user = SimpleNamespace(id=1)

        response = asyncio.run(
            chat_stream_endpoint(ChatRequest(query="Hello"), request, user, db)
        )

        async def collect_body():
            return [chunk async for chunk in response.body_iterator]

        body = "".join(asyncio.run(collect_body()))

        self.assertIn('"text": "Hello bạn sinh viên!"', body)
        self.assertIn('"sources": []', body)
        self.assertIn('"id": "generating"', body)
        mock_retrieve.assert_not_called()

    @patch("api.routes.chat._is_relevant", return_value=False)
    @patch(
        "api.routes.chat.generate_out_of_scope_answer",
        return_value="Python để cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi.",
    )
    @patch("api.routes.chat.get_reranker", return_value=None)
    @patch("api.routes.chat.get_bm25")
    @patch("api.routes.chat.hybrid_retrieve")
    def test_out_of_scope_chat_uses_playful_generator_without_sources(
        self,
        mock_retrieve,
        mock_get_bm25,
        mock_get_reranker,
        mock_generate,
        mock_is_relevant,
    ):
        mock_get_bm25.return_value = Mock()
        mock_retrieve.return_value = [
            SimpleNamespace(
                text="Unrelated context",
                metadata={"source": "test"},
                score=-1.0,
            )
        ]
        db = Mock()
        db.refresh.side_effect = lambda session: setattr(session, "id", "scope-session")
        request = SimpleNamespace(client=SimpleNamespace(host="test-client"))
        user = SimpleNamespace(id=1)

        response = asyncio.run(
            chat_endpoint(
                ChatRequest(query="Viết phương trình bậc 2 bằng Python"),
                request,
                user,
                db,
            )
        )

        self.assertEqual(
            response.answer,
            "Python để cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi.",
        )
        self.assertEqual(response.sources, [])
        mock_generate.assert_called_once_with("Viết phương trình bậc 2 bằng Python")

    def test_relevance_threshold_rejects_weak_reranker_score(self):
        weak_document = SimpleNamespace(score=0.53)
        strong_document = SimpleNamespace(score=5.0)

        self.assertFalse(chat_module._is_relevant([weak_document]))
        self.assertTrue(chat_module._is_relevant([strong_document]))

    @patch("api.routes.chat.get_reranker", return_value=None)
    @patch("api.routes.chat.get_bm25")
    @patch("api.routes.chat.hybrid_retrieve")
    def test_out_of_scope_stream_uses_playful_generator_without_sources(
        self, mock_retrieve, mock_get_bm25, mock_get_reranker
    ):
        mock_get_bm25.return_value = Mock()
        mock_retrieve.return_value = [
            SimpleNamespace(
                text="Unrelated context",
                metadata={"source": "test"},
                score=-1.0,
            )
        ]
        db = Mock()
        db.refresh.side_effect = lambda session: setattr(session, "id", "scope-stream")
        request = SimpleNamespace(client=SimpleNamespace(host="test-client"))
        user = SimpleNamespace(id=1)

        with patch("api.routes.chat._is_relevant", return_value=False), patch(
            "api.routes.chat.stream_out_of_scope_answer",
            return_value=iter(["Python để cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi."]),
        ) as mock_out_of_scope, patch("api.routes.chat.stream_answer") as mock_rag:
            response = asyncio.run(
                chat_stream_endpoint(
                    ChatRequest(query="Viết phương trình bậc 2 bằng Python"),
                    request,
                    user,
                    db,
                )
            )

            async def collect_body():
                return [chunk async for chunk in response.body_iterator]

            body = "".join(asyncio.run(collect_body()))

        self.assertIn("Python để cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi.", body)
        self.assertIn('"sources": []', body)
        mock_out_of_scope.assert_called_once_with("Viết phương trình bậc 2 bằng Python")
        mock_rag.assert_not_called()

    @patch("api.routes.chat.get_reranker", return_value=None)
    @patch("api.routes.chat.get_bm25")
    @patch("api.routes.chat.hybrid_retrieve")
    @patch("api.routes.chat.stream_answer", return_value=iter(["Hello ", "world"]))
    def test_stream_endpoint_emits_ordered_events_and_persists_answer(
        self, mock_stream, mock_retrieve, mock_get_bm25, mock_get_reranker
    ):
        mock_get_bm25.return_value = Mock()
        mock_doc = SimpleNamespace(
            text="Test content",
            metadata={"source": "test"},
            score=5.0,
        )
        mock_retrieve.return_value = [mock_doc]

        db = Mock()
        db.refresh.side_effect = lambda session: setattr(session, "id", "test-session")
        request = SimpleNamespace(client=SimpleNamespace(host="test-client"))
        user = SimpleNamespace(id=1)

        response = asyncio.run(
            chat_stream_endpoint(
                ChatRequest(query="test question"),
                request,
                user,
                db,
            )
        )

        async def collect_body():
            return [chunk async for chunk in response.body_iterator]

        body = "".join(asyncio.run(collect_body()))
        events = [line for line in body.splitlines() if line.startswith("event: ")]

        self.assertEqual(
            events,
            [
                "event: status",
                "event: status",
                "event: meta",
                "event: status",
                "event: token",
                "event: token",
                "event: done",
            ],
        )
        self.assertIn('"stage": "retrieving"', body)
        self.assertIn('"stage": "generating"', body)
        self.assertIn('"stages": [', body)
        self.assertIn('"id": "retrieving"', body)
        self.assertIn('"id": "reranking"', body)
        self.assertIn('"id": "generating"', body)
        self.assertNotIn('"duration_ms"', body)
        self.assertNotIn('"detail"', body)
        self.assertIn('"session_id": "test-session"', body)
        self.assertIn('"text": "Hello "', body)
        self.assertIn('"text": "world"', body)
        self.assertEqual(mock_stream.call_count, 1)
        persisted = [call.args[0] for call in db.add.call_args_list]
        self.assertTrue(
            any(
                getattr(message, "role", None) == "assistant"
                and message.content == "Hello world"
                for message in persisted
            )
        )

if __name__ == '__main__':
    unittest.main()
