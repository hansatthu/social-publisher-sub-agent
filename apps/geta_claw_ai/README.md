# 🤖 GETA CLAW - Hệ thống Tự động hóa & AI Assistant Đa Nhiệm

Chào mừng bạn đến với **GETA CLAW** (phiên bản 4.0). Đây là hệ thống tự động hóa điều phối bởi AI (Master Agent) tích hợp chatbot Telegram, hệ thống sản xuất nội dung (Blog SEO & Video TikTok Faceless), cào dữ liệu thị trường và tích hợp Zalo CRM.

---

## 🌟 Tính năng chính

### 1. 🧠 Master Agent (Điều phối thông minh)
- Tự động nhận diện ý định của người dùng từ Zalo/Telegram.
- Sử dụng mô hình ngôn ngữ lớn **DeepSeek V3/Gemini 2.5 Flash** để tự động phân tích và kích hoạt công cụ (Tools) phù hợp.
- Cơ chế fail-safe thông minh tự động kích hoạt tiến trình tương ứng ngay cả khi mô hình LLM gặp sự cố hoặc trả về không đúng định dạng.

### 2. 📝 Hệ thống sản xuất Blog SEO tự động (Interactive Workflow)
- **Tích hợp sâu WordPress & WooCommerce**: Quét sản phẩm, tự động tạo bài viết chuẩn SEO và đăng bài trực tiếp.
- **Quy trình tương tác qua Telegram**:
  - Chọn website đích đăng bài qua menu nút bấm trực quan.
  - Chọn nguồn ảnh thông minh: Tải ảnh trực tiếp lên (Upload), Chọn hình ảnh liên quan từ thư viện WordPress media hoặc không chèn ảnh.
  - Tự động liên kết link nội bộ (Internal Links) và link vệ tinh chuẩn SEO.

### 3. 🎥 Trình dựng video TikTok Faceless tự động
- Nhận chủ đề (Topic) và độ dài tùy chỉnh từ người dùng.
- Tự động viết kịch bản phân cảnh, đọc giọng đọc AI chuẩn Việt (TTS), cắt ghép tự động kho video B-Roll và xuất video hoàn chỉnh (chuẩn dọc 9:16).

### 4. 🔍 Cào dữ liệu & Nghiên cứu thị trường
- Cào dữ liệu sản phẩm, giá cả và nhà cung cấp từ các sàn TMĐT hoặc các group Facebook.
- Đồng bộ thông tin danh sách liên hệ khách hàng/đối thủ về Zalo CRM.

---

## 📂 Cấu trúc dự án

```text
geta_claw/
├── backend/                  # Backend FastAPI & Telegram Controller
│   ├── video_engine/         # Nền tảng tự động dựng video TikTok
│   ├── core_agent.py         # Master Agent điều phối & cấu hình Tools/Fail-safe
│   ├── workflow_engine.py    # Quản lý trạng thái và giao diện nút bấm Telegram
│   ├── tasks.py              # Các Celery tasks nền (quét data, dựng video, viết bài)
│   └── main.py               # API Gateway tiếp nhận Webhook Telegram/Zalo
├── blog_tool/                # Web Dashboard quản lý viết bài & sản phẩm
│   ├── database/             # Quản lý cơ sở dữ liệu SQLite/PostgreSQL của blog
│   ├── integrations/         # Kết nối API WordPress, WooCommerce, Google Sheets
│   ├── llm_engine/           # Lõi viết bài AI chuẩn SEO
│   └── ui/                   # Giao diện Streamlit Dashboard quản lý
├── scripts/                  # Các kịch bản cào dữ liệu thị trường
├── docker-compose.yml        # Docker compose khởi động PostgreSQL, Redis, Ollama
└── pyproject.toml            # Quản lý dependencies dự án
```

---

## 🛠️ Hướng dẫn cài đặt & Khởi chạy

### 1. Chuẩn bị tài nguyên cơ sở (Docker)
Đảm bảo đã cài đặt Docker Desktop. Khởi chạy PostgreSQL (pgvector), Redis và Ollama ở chế độ nền:
```bash
docker compose up -d
```

### 2. Thiết lập môi trường (.env)
Tạo file `.env` trong thư mục `backend/` và cấu hình các biến môi trường sau:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
DEEPSEEK_API_KEY=your_deepseek_api_key
GEMINI_API_KEYS=key1,key2,key3
DATABASE_URL=postgresql://user:password@localhost:5432/db_name
REDIS_URL=redis://localhost:6379/0
```

### 3. Cài đặt Python Dependencies
Khuyên dùng `uv` để cài đặt và quản lý môi trường nhanh chóng:
```bash
uv sync
```

### 4. Khởi chạy FastAPI Webhook Server
```bash
$env:PYTHONPATH="D:\GETA_WORKSPACE\python_backend"
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Khởi chạy Celery Worker (Xử lý tác vụ nền)
```bash
uv run celery -A tasks worker --loglevel=info
```

### 6. Khởi chạy Giao diện Dashboard (Streamlit)
```bash
cd blog_tool
uv run streamlit run ui/app.py
```

---

## 🤖 Hướng dẫn tương tác Telegram Chatbot
- **Viết bài blog**: Chat `"viết blog về in ly Tây Ninh, có chèn ảnh"`, chatbot sẽ kích hoạt luồng chọn website và tùy chọn tải lên/chọn ảnh từ thư viện.
- **Tạo video TikTok**: Chat `"làm video 15s về cách chọn ly trà sữa độc lạ"`, hệ thống tự động chạy Celery dựng video.
- **Nghiên cứu thị trường**: Chat `"nghiên cứu đối thủ bán ly nhựa giá sỉ"`, Master Agent gọi công cụ cào dữ liệu lưu về CRM.

---

## 📝 Định nghĩa hoàn thành công việc (DoD)
- [x] Master Agent nhận diện chuẩn xác ý định viết blog/dựng video bất kể từ khóa phụ.
- [x] Menu nút bấm tương tác chèn ảnh hoạt động mượt mà trên Telegram.
- [x] Hệ thống worker Celery chạy độc lập không làm nghẽn luồng chatbot Telegram.
