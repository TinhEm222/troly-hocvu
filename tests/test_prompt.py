import unittest

from llm.prompt import build_general_prompt, build_out_of_scope_prompt, build_prompt


class TestPromptContract(unittest.TestCase):
    def test_prompt_allows_natural_basic_conversation(self):
        prompt = build_prompt("Thông tin học vụ mẫu", "Hello")

        self.assertIn("HỘI THOẠI CƠ BẢN", prompt)
        self.assertIn("trả lời tự nhiên", prompt)
        self.assertNotIn("PHẢI trả lời chính xác câu sau", prompt)

    def test_prompt_keeps_school_answers_grounded(self):
        prompt = build_prompt("Thông tin học vụ mẫu", "Điều kiện tốt nghiệp là gì?")

        self.assertIn("không được tự suy diễn", prompt)
        self.assertIn("CTUT", prompt)
        self.assertIn("CONTEXT", prompt)

    def test_general_prompt_requires_a_closed_response(self):
        prompt = build_general_prompt("Tôi muốn đi chơi")

        normalized_prompt = prompt.casefold()
        self.assertIn("không hỏi lại", normalized_prompt)
        self.assertIn("không kết thúc bằng câu hỏi", normalized_prompt)
        self.assertIn("Bạn có muốn", prompt)

    def test_general_prompt_supports_markdown_and_latex_format(self):
        prompt = build_general_prompt("Giải phương trình bậc hai bằng Python").casefold()

        self.assertIn("markdown", prompt)
        self.assertIn("backtick", prompt)
        self.assertIn("latex", prompt)

    def test_general_prompt_allows_controlled_playful_tone(self):
        prompt = build_general_prompt("Tôi muốn đi chơi").casefold()

        self.assertIn("hài hước", prompt)
        self.assertIn("bựa nhẹ", prompt)
        self.assertIn("không tục", prompt)
        self.assertIn("trợ lý sinh viên ctut", prompt)

    def test_out_of_scope_prompt_requires_playful_closed_refusal(self):
        prompt = build_out_of_scope_prompt("Viết phương trình bậc 2 bằng Python").casefold()

        self.assertIn("không giải thích", prompt)
        self.assertIn("không hỏi lại", prompt)
        self.assertIn("bựa nhẹ", prompt)
        self.assertIn("không viết code", prompt)


if __name__ == "__main__":
    unittest.main()
