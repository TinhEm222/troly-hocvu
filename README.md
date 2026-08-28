# Trợ lý ảo học vụ CTUT

Hệ thống trợ lý ảo hỗ trợ sinh viên tra cứu tài liệu học vụ của Trường Đại học Kỹ thuật - Công nghệ Cần Thơ bằng Retrieval-Augmented Generation (RAG).

## Kiến trúc và cấu hình chính

- Frontend: Next.js, TypeScript, Tailwind CSS.
- Backend: FastAPI, JWT, SQLAlchemy và SQLite.
- Kho vector: Qdrant, dense vector 384 chiều và sparse vector.
- Embedding: `intfloat/multilingual-e5-small` với tiền tố `query:` và `passage:`.
- Retrieval: Dense Search 60% + BM25 40%, lấy Top-6 ứng viên.
- Reranking: `cross-encoder/ms-marco-MiniLM-L-6-v2`, giữ Top-5 và ngưỡng liên quan 3,0.
- LLM chính: Gemini; dự phòng: Ollama với `qwen2.5:3b`.
- Chunking: tối đa 450 token, overlap 90 token sau khi chia theo Phần/Chương/Mục/Điều/Khoản.

## Chức năng

- Sinh viên đăng ký, đăng nhập, tạo/xóa cuộc trò chuyện, hỏi đáp dạng streaming và xem nguồn tham khảo.
- Quản trị viên xem thống kê, quản lý người dùng và tài liệu PDF.
- Tài liệu hỗ trợ quản lý phiên bản bằng `document_code`, `version_number`, `lifecycle_status` và `replaces_document_id`.
- Phiên bản mới ở trạng thái `draft`; sau khi re-index thành công mới chuyển sang `active`, còn phiên bản cũ chuyển thành `superseded`.
- Pipeline chỉ đưa phiên bản đang hiệu lực vào Qdrant và re-index toàn bộ corpus để tránh dữ liệu cũ/trùng lặp.

## Chạy trên Windows bằng VS Code

Mở thư mục dự án bằng VS Code, sau đó chạy tại terminal PowerShell ở thư mục gốc:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
docker compose up -d qdrant
python -m api.main
```

Mở terminal thứ hai:

```powershell
cd frontend
npm ci
npm run dev
```

Địa chỉ sử dụng:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Swagger API: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Trước khi chạy, sửa `.env` và đặt tối thiểu `GEMINI_API_KEY`, `JWT_SECRET_KEY`, `ADMIN_EMAIL` và `ADMIN_PASSWORD`. Nếu cần fallback cục bộ, cài Ollama rồi chạy:

```powershell
ollama pull qwen2.5:3b
```

## Chạy kiểm thử

```powershell
$env:PYTHONPATH = "."
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q

cd frontend
npm test
npm run typecheck
npm run lint
npm run build
```

## Cập nhật tài liệu

1. Đăng nhập bằng tài khoản quản trị viên.
2. Mở **Quản lý tài liệu**.
3. Chọn **Tài liệu mới** hoặc **Cập nhật phiên bản**.
4. Nếu cập nhật, chọn đúng tài liệu đang hiệu lực rồi tải một file PDF mới.
5. Backend tự động chạy re-index sau khi upload hoặc xóa thành công. Có thể dùng nút **Re-index** để chạy lại khi cần.

Nếu re-index thất bại, phiên bản mới giữ trạng thái `draft/failed` và phiên bản cũ vẫn `active`.
