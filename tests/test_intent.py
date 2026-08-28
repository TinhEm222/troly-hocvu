import unittest

from llm.intent import get_basic_response


class TestBasicIntent(unittest.TestCase):
    def test_greeting_returns_basic_response(self):
        answer = get_basic_response("Hello")

        self.assertIsNotNone(answer)
        self.assertIn("Hello", answer)
        self.assertIn("sinh viên", answer)

    def test_thanks_returns_basic_response(self):
        answer = get_basic_response("Cảm ơn bạn nhé!")

        self.assertIsNotNone(answer)
        self.assertIn("Không có gì", answer)

    def test_capability_question_returns_basic_response(self):
        answer = get_basic_response("Bạn có thể giúp gì?")

        self.assertIsNotNone(answer)
        self.assertIn("học vụ", answer.lower())

    def test_school_question_is_not_basic(self):
        self.assertIsNone(get_basic_response("Điều kiện xét tốt nghiệp là gì?"))

    def test_unrelated_question_is_not_basic(self):
        self.assertIsNone(get_basic_response("Giá vàng hôm nay là bao nhiêu?"))


if __name__ == "__main__":
    unittest.main()
