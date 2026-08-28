# Chatbot — Handoff Guide

Tài liệu này mô tả gói bàn giao của source hiện tại trong thư mục `chatbot-hocvu/`.
Ứng dụng gồm FastAPI backend, Next.js frontend và Qdrant vector database; dữ liệu trả lời hiện tại là bộ tài liệu học vụ.

## Phạm vi gói

- Có source backend/frontend, test, Dockerfile, Docker Compose, cấu hình mẫu và `data/raw/`.
- Không đưa vào gói: `.env`, virtualenv, `node_modules`, `.next`, cache, log, SQLite runtime database, Qdrant runtime storage và thư mục `DA08-VSF-AI/`.
- `data/raw/` có thể chứa tài liệu nội bộ. Chỉ gửi kèm khi bên nhận đã được phép tiếp cận.

Tạo archive bằng:

```bash
bash scripts/package_handoff.sh
```

Archive và checksum được tạo trong `handoff/`.

## Khởi chạy từ source

Yêu cầu: Python 3.12+, Node.js 18.18+, npm và Docker. Ollama là tùy chọn nếu dùng làm LLM fallback.

```bash
cp .env.example .env
# Đặt GEMINI_API_KEY, JWT_SECRET_KEY và ADMIN_PASSWORD bằng giá trị riêng của môi trường bàn giao.

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

cd frontend && npm ci && cd ..
docker compose up -d qdrant

PYTHONPATH=. .venv/bin/python -m ingestion.pipeline
PYTHONPATH=. .venv/bin/python -m api.main
```

Chạy frontend ở terminal khác:

```bash
cd frontend
npm run dev
```

- Backend: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Frontend: `http://localhost:3000`
- Health: `http://localhost:8000/health`

## Kiểm tra

```bash
# Backend — tắt pytest plugin ngoài môi trường để kết quả chỉ phản ánh project này
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q

cd frontend
npm test
npm run typecheck
npm run build
```

Baseline kiểm tra ngày 2026-08-28: backend `62 passed`; frontend unit tests `16 passed`; typecheck, lint và production build đều thành công. Frontend dùng Next `16.3.0`; build cố định Webpack theo cấu hình dự án.

Source đã triển khai vòng đời phiên bản tài liệu theo báo cáo: bản upload mới là `draft`, chỉ chuyển thành `active` sau khi re-index thành công; bản cũ bị thay thế chuyển thành `superseded`. Pipeline chỉ lập chỉ mục tập tài liệu có hiệu lực.

## Cấu hình và bảo mật trước khi nhận bàn giao

- Không phân phối `.env`. File đó có credential thật trong workspace hiện tại; các credential này cần được rotate/revoke trước khi gửi source hoặc archive.
- Không dùng giá trị mặc định trong `.env.example` ở production: đặc biệt `JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `GEMINI_API_KEY` và `QDRANT_API_KEY`.
- Production cần cấu hình CORS theo origin cụ thể thay vì wildcard, bật HTTPS/reverse proxy và đặt backup cho Qdrant/SQLite.
- `data/raw/` và `data/app.db` có thể chứa dữ liệu nhạy cảm; archive mặc định giữ raw documents để có thể ingest lại nhưng loại SQLite runtime database.

## Lưu ý bàn giao

`requirements.txt` khai báo dependency theo range và chưa phải lock file đầy đủ. Với môi trường production, nên chốt Python/platform, tạo lock file và kiểm tra lại dependency bằng quy trình bảo mật của bên nhận.
