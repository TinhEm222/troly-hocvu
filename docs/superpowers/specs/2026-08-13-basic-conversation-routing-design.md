# Basic Conversation Routing Design

## Goal

Nới lỏng trợ lý học vụ để các câu giao tiếp cơ bản được trả lời tự nhiên, trong khi câu hỏi học vụ vẫn được trả lời dựa trên tài liệu chính thức và câu hỏi ngoài phạm vi được từ chối mềm, không hiển thị nguồn nội bộ không liên quan.

## Behavior

- Lời chào, cảm ơn và câu hỏi về khả năng của chatbot được xử lý trực tiếp trước bước retrieval.
- Các câu basic không gọi Qdrant, không gọi embedding/reranker, không hiển thị nguồn tham khảo.
- Câu hỏi học vụ tiếp tục đi qua hybrid retrieval, reranking và Gemini; nguồn chỉ hiển thị khi tài liệu đủ liên quan.
- Câu hỏi ngoài phạm vi, ví dụ “Giá vàng hôm nay”, nhận câu trả lời thân thiện giải thích chatbot chỉ hỗ trợ tư vấn học vụ cho sinh viên CTUT; không hiển thị nguồn nội bộ.
- Luồng thường và luồng streaming dùng cùng một quy tắc phân loại.
- Basic và ngoài phạm vi vẫn được lưu trong lịch sử chat; streaming vẫn phát đủ `meta`, token và `done` để frontend hoạt động ổn định.

## Architecture

Thêm một module phân loại pure-function tại `llm/intent.py`, trả về loại câu hỏi và câu trả lời dựng sẵn cho các intent basic. API route gọi module này trước retrieval. Với câu hỏi đã retrieval nhưng không đạt relevance, route dùng thông báo ngoài phạm vi thay vì đưa context không liên quan cho LLM. `llm/prompt.py` được nới văn phong để cho phép hội thoại tự nhiên, nhưng câu hỏi học vụ vẫn bị giới hạn bởi CONTEXT.

## Error handling

- Nếu câu basic nhận diện được, hệ thống không phụ thuộc Gemini/Ollama.
- Nếu câu hỏi ngoài phạm vi không có tài liệu liên quan, hệ thống không suy diễn dữ liệu thời gian thực và không trả nguồn nội bộ.
- Các lỗi provider hiện tại tiếp tục dùng fallback và thông báo an toàn như trước.

## Testing

- Unit test cho phân loại: hello, cảm ơn, khả năng hỗ trợ, câu hỏi học vụ và câu hỏi ngoài phạm vi.
- API test bảo đảm basic không gọi retrieval, streaming basic phát token không có sources, và câu hỏi không liên quan không gọi generator RAG.
- Live smoke test với “Hello” và “Giá vàng hôm nay”, cùng regression test cho câu hỏi học vụ có nguồn.
