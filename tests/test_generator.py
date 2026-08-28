import unittest
from unittest.mock import Mock, patch

import llm.generator as generator


class TestGenerator(unittest.TestCase):

    def test_general_response_preserves_markdown_and_latex(self):
        raw = "Dùng `cmath` với $a$, $b$, $c$ và \\(x\\)."

        answer = generator.prepare_general_response(raw)

        self.assertEqual(answer, raw)

    def test_empty_context(self):
        result = generator.generate_answer("", "test question")
        self.assertIn("ngữ cảnh", result)

    def test_empty_question(self):
        result = generator.generate_answer("test context", "")
        self.assertIn("Câu hỏi", result)

    @patch("llm.generator.build_general_prompt", return_value="General prompt")
    @patch("llm.generator.genai.Client")
    def test_general_answer_uses_question_without_rag_context(
        self, mock_client_class, mock_prompt
    ):
        mock_client = Mock()
        mock_client.models.generate_content.return_value.text = "Dùng `cmath` với $a$ là xong."
        mock_client_class.return_value = mock_client

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            result = generator.generate_general_answer("Tôi muốn đi chơi")

        self.assertEqual(result, "Dùng `cmath` với $a$ là xong.")
        mock_prompt.assert_called_once_with("Tôi muốn đi chơi")
        self.assertEqual(
            mock_client.models.generate_content.call_args.kwargs["contents"],
            "General prompt",
        )

    @patch("llm.generator.build_general_prompt", return_value="General prompt")
    @patch("llm.generator.genai.Client")
    def test_general_stream_yields_provider_response(
        self, mock_client_class, mock_prompt
    ):
        mock_client = Mock()
        mock_client.models.generate_content_stream.return_value = [
            Mock(text="Dùng `cmath` với "),
            Mock(text="$a$ là xong."),
        ]
        mock_client_class.return_value = mock_client

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            chunks = list(generator.stream_general_answer("Tôi muốn đi chơi"))

        self.assertEqual(chunks, ["Dùng `cmath` với ", "$a$ là xong."])
        mock_prompt.assert_called_once_with("Tôi muốn đi chơi")

    def test_general_fallback_is_a_closed_response_without_follow_up_question(self):
        with patch.object(generator, "GEMINI_API_KEY", ""), patch.object(
            generator, "FALLBACK_PROVIDER", "ollama"
        ), patch.object(
            generator, "_generate_with_provider", side_effect=RuntimeError("provider down")
        ):
            answer = generator.generate_general_answer("Tôi muốn đi chơi")

        self.assertNotIn("?", answer)
        self.assertNotIn("Bạn có muốn", answer)

    @patch("llm.generator.build_out_of_scope_prompt", return_value="Out-of-scope prompt")
    @patch("llm.generator.genai.Client")
    def test_out_of_scope_generator_preserves_safe_playful_response(
        self, mock_client_class, mock_prompt
    ):
        mock_client = Mock()
        mock_client.models.generate_content.return_value.text = (
            "Python để các cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi."
        )
        mock_client_class.return_value = mock_client

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            result = generator.generate_out_of_scope_answer(
                "Viết phương trình bậc 2 bằng Python"
            )

        self.assertEqual(
            result,
            "Python để các cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi.",
        )
        mock_prompt.assert_called_once_with("Viết phương trình bậc 2 bằng Python")

    @patch("llm.generator.build_out_of_scope_prompt", return_value="Out-of-scope prompt")
    @patch("llm.generator.genai.Client")
    def test_out_of_scope_generator_replaces_code_leak_with_witty_fallback(
        self, mock_client_class, mock_prompt
    ):
        mock_client = Mock()
        mock_client.models.generate_content.return_value.text = "import cmath\nprint('code')"
        mock_client_class.return_value = mock_client

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            result = generator.generate_out_of_scope_answer(
                "Viết phương trình bậc 2 bằng Python"
            )

        self.assertNotIn("import cmath", result)
        self.assertNotIn("print(", result)
        self.assertNotIn("?", result)

    @patch("llm.generator.build_out_of_scope_prompt", return_value="Out-of-scope prompt")
    @patch("llm.generator.genai.Client")
    def test_out_of_scope_stream_withholds_unsafe_provider_output(
        self, mock_client_class, mock_prompt
    ):
        mock_client = Mock()
        mock_client.models.generate_content_stream.return_value = [
            Mock(text="import cmath"),
            Mock(text="\nprint('code')"),
        ]
        mock_client_class.return_value = mock_client

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            chunks = list(
                generator.stream_out_of_scope_answer(
                    "Viết phương trình bậc 2 bằng Python"
                )
            )

        streamed_answer = "".join(chunks)
        self.assertNotIn("import cmath", streamed_answer)
        self.assertNotIn("print(", streamed_answer)

    @patch("llm.generator.build_out_of_scope_prompt", return_value="Out-of-scope prompt")
    @patch("llm.generator.genai.Client")
    def test_out_of_scope_stream_reveals_safe_response_in_multiple_chunks(
        self, mock_client_class, mock_prompt
    ):
        safe_response = (
            "Python để các cao nhân xử lý nhé; mình chuyên học vụ CTUT thôi, "
            "không nhận vai lập trình viên bất đắc dĩ."
        )
        mock_client = Mock()
        mock_client.models.generate_content_stream.return_value = [Mock(text=safe_response)]
        mock_client_class.return_value = mock_client

        with patch.object(generator, "GEMINI_API_KEY", "test-key"), patch.object(
            generator.time, "sleep"
        ) as mock_sleep:
            chunks = list(
                generator.stream_out_of_scope_answer(
                    "Viết phương trình bậc 2 bằng Python"
                )
            )

        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), safe_response)
        mock_sleep.assert_called()

    @patch("llm.generator.build_out_of_scope_prompt", return_value="Out-of-scope prompt")
    @patch("llm.generator.genai.Client")
    def test_out_of_scope_generator_replaces_follow_up_invitation_with_fallback(
        self, mock_client_class, mock_prompt
    ):
        mock_client = Mock()
        mock_client.models.generate_content.return_value.text = (
            "Mình chỉ lo học vụ CTUT thôi, cần gì cứ hú mình nhé."
        )
        mock_client_class.return_value = mock_client

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            result = generator.generate_out_of_scope_answer("Tôi muốn đi chơi")

        self.assertNotIn("cứ hú", result.casefold())
        self.assertNotIn("cần gì", result.casefold())

    @patch("llm.generator.build_prompt", return_value="Test prompt")
    @patch("llm.generator.genai.Client")
    def test_gemini_success_does_not_send_temperature(
        self, mock_client_class, mock_prompt
    ):
        mock_client = Mock()
        mock_client.models.generate_content.return_value.text = "Gemini answer"
        mock_client_class.return_value = mock_client

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            result = generator.generate_answer("test context", "test question")

        self.assertEqual(result, "Gemini answer")
        call = mock_client.models.generate_content.call_args
        self.assertEqual(call.kwargs["model"], generator.MODEL_NAME)
        self.assertEqual(call.kwargs["contents"], "Test prompt")
        config = call.kwargs["config"]
        self.assertIsNone(config.temperature)
        self.assertIsNone(config.top_p)
        self.assertIsNone(config.top_k)

    @patch("llm.generator.build_prompt", return_value="Test prompt")
    @patch("llm.generator.ollama.Client")
    @patch("llm.generator.genai.Client")
    def test_gemini_failure_falls_back_to_ollama(
        self, mock_gemini_class, mock_ollama_class, mock_prompt
    ):
        mock_gemini = Mock()
        mock_gemini.models.generate_content.side_effect = RuntimeError("Gemini down")
        mock_gemini_class.return_value = mock_gemini

        mock_ollama = Mock()
        mock_ollama.chat.return_value = {"message": {"content": "Ollama answer"}}
        mock_ollama_class.return_value = mock_ollama

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            result = generator.generate_answer("test context", "test question")

        self.assertEqual(result, "Ollama answer")
        mock_ollama.chat.assert_called_once()

    @patch("llm.generator.build_prompt", return_value="Test prompt")
    @patch("llm.generator.ollama.Client")
    def test_missing_gemini_key_falls_back_to_ollama(self, mock_ollama_class, mock_prompt):
        mock_ollama = Mock()
        mock_ollama.chat.return_value = {"message": {"content": "Fallback answer"}}
        mock_ollama_class.return_value = mock_ollama

        with patch.object(generator, "GEMINI_API_KEY", ""):
            result = generator.generate_answer("test context", "test question")

        self.assertEqual(result, "Fallback answer")

    @patch("llm.generator.build_prompt", return_value="Test prompt")
    @patch("llm.generator.ollama.Client")
    @patch("llm.generator.genai.Client")
    def test_both_providers_failing_returns_safe_error(
        self, mock_gemini_class, mock_ollama_class, mock_prompt
    ):
        mock_gemini = Mock()
        mock_gemini.models.generate_content.side_effect = RuntimeError("Gemini down")
        mock_gemini_class.return_value = mock_gemini

        mock_ollama = Mock()
        mock_ollama.chat.side_effect = RuntimeError("Ollama down")
        mock_ollama_class.return_value = mock_ollama

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            result = generator.generate_answer("test context", "test question")

        self.assertIn("lỗi trong quá trình tạo câu trả lời", result)
        self.assertNotIn("Gemini down", result)
        self.assertNotIn("Ollama down", result)

    @patch("llm.generator.build_prompt", return_value="Test prompt")
    @patch("llm.generator.genai.Client")
    def test_gemini_stream_yields_chunks_in_order(self, mock_client_class, mock_prompt):
        mock_client = Mock()
        mock_client.models.generate_content_stream.return_value = [
            Mock(text="Hello "),
            Mock(text="world"),
        ]
        mock_client_class.return_value = mock_client

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            chunks = list(generator.stream_answer("test context", "test question"))

        self.assertEqual(chunks, ["Hello ", "world"])
        call = mock_client.models.generate_content_stream.call_args
        self.assertEqual(call.kwargs["model"], generator.MODEL_NAME)
        self.assertEqual(call.kwargs["contents"], "Test prompt")
        config = call.kwargs["config"]
        self.assertIsNone(config.temperature)
        self.assertIsNone(config.top_p)
        self.assertIsNone(config.top_k)

    @patch("llm.generator.build_prompt", return_value="Test prompt")
    @patch("llm.generator.ollama.Client")
    @patch("llm.generator.genai.Client")
    def test_gemini_stream_failure_falls_back_to_ollama(
        self, mock_gemini_class, mock_ollama_class, mock_prompt
    ):
        mock_gemini = Mock()
        mock_gemini.models.generate_content_stream.side_effect = RuntimeError("Gemini down")
        mock_gemini_class.return_value = mock_gemini

        mock_ollama = Mock()
        mock_ollama.chat.return_value = [
            {"message": {"content": "Fallback "}},
            {"message": {"content": "answer"}},
        ]
        mock_ollama_class.return_value = mock_ollama

        with patch.object(generator, "GEMINI_API_KEY", "test-key"):
            chunks = list(generator.stream_answer("test context", "test question"))

        self.assertEqual(chunks, ["Fallback ", "answer"])
        mock_ollama.chat.assert_called_once()
        self.assertTrue(mock_ollama.chat.call_args.kwargs["stream"])


if __name__ == "__main__":
    unittest.main()
