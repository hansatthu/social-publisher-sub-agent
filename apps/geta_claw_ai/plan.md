Dưới đây là toàn bộ tài liệu đặc tả thiết kế hệ thống và kế hoạch triển khai tổng thể (End-to-End Deployment Plan) cho quy trình vận hành tự động hóa 5 bước. Kế hoạch này được tối ưu hóa riêng cho cấu hình phần cứng hiện tại của bạn (**i5-10400F, 16GB RAM, GTX 1660 Super 6GB VRAM**) theo mô hình **Kiến trúc Hỗn hợp (Hybrid Edge-Cloud Architecture)** nhằm chạy liên tục 24/7 với chi phí vận hành thấp nhất.

---

## 1. Kiến trúc Tổng thể Hệ thống (System Topology)

Hệ thống vận hành theo mô hình **Hướng sự kiện (Event-Driven Architecture)**. Máy tính local đóng vai trò là Trạm điều phối trung tâm (Orchestrator), Cổng kết nối (Gateway), và Cơ sở dữ liệu (Database). Các tác vụ AI nặng về tính toán sẽ được phân phối thông qua API Serverless để bảo vệ tài nguyên phần cứng local.

```
[MẠNG INTERNET BÊN NGOÀI]
  │ Facebook/TikTok Webhooks ──► Cloudflare Tunnel (HTTPS)
  ▼
[MÁY TÍNH LOCAL (Windows 10 Pro + WSL2 + Docker)]
  │
  ├──► [TẦNG ĐIỀU PHỐI MẠNG] ──────► FastAPI Gateway
  │                                    │
  ├──► [TẦNG LỌC TÍN HIỆU (GPU)] ────► Ollama Engine (Llama 3.2 3B INT4)
  │                                    │ (Nếu cần xử lý sâu)
  ├──► [TẦNG XỬ LÝ SỰ KIỆN] ─────────► Redis Streams (Broker) ◄──► Celery Workers
  │                                    │
  └──► [TẦNG LƯU TRỮ DỮ LIỆU] ──────► PostgreSQL + pgvector & DuckDB
  ▼
[TẦNG ĐIỀU KHIỂN AI (CLOUD CLUSTER)]
  │ Gọi API bảo mật (Outbound)
  ├──► Vertex AI (Gemini 1.5 Flash + Context Caching) ──► Xử lý Bước 2 & Bước 4
  └──► DeepSeek API (DeepSeek-R1 Engine) ────────────────► Xử lý Bước 3 (Analysis Loop)

```

---

## 2. Danh mục Công nghệ Triển khai (Technical Stack Matrix)

| Thành phần | Công nghệ triển khai | Cấu hình & Tham số Kỹ thuật | Vai trò trong hệ thống |
| --- | --- | --- | --- |
| **Hạ tầng 24/7** | Docker Desktop + WSL2 | Ubuntu 22.04 LTS Backend | Đóng gói toàn bộ mã nguồn thành các dịch vụ cô lập, tự phục hồi. |
| **Event Broker** | Redis (Streams & Pub/Sub) | Khởi chạy dạng Docker Container, cấu hình lưu dữ liệu xuống ổ đĩa (AOF) | Hàng đợi tin nhắn (Message Queue) điều phối tác vụ bất đồng bộ giữa các bước. |
| **Cơ sở dữ liệu** | PostgreSQL 15 + `pgvector` | Định cấu hình chỉ mục `HNSW` (Hierarchical Navigable Small World) | Lưu trữ trạng thái kho, lịch sử chat (State Store) và Vector nhúng của sản phẩm. |
| **Phân tích số liệu** | DuckDB (Embedded OLAP) | Thực thi trực tiếp trong tiến trình Python | Đọc log từ PostgreSQL, tính toán ma trận Ads ROI/ROAS ở Bước 3 với tốc độ cao. |
| **Mô hình Local** | Ollama Engine | Llama 3.2 (3B) - Quantized INT4 format | Chạy trên GPU GTX 1660 Super. Phân loại ý định khách hàng (Intent Router) ở Bước 4. |
| **Mô hình Cloud** | Gemini 1.5/2.0 Flash + DeepSeek-R1 | Tích hợp qua SDK với cơ chế Vertex Context Caching | Xử lý đa phương thức (Hình ảnh/Video) ở Bước 2; Chốt đơn nâng cao ở Bước 4; Tối ưu ngân sách ở Bước 3. |
| **Framework Agent** | LangGraph + Celery | Asyncio Runtime Python | Quản lý vòng lặp trạng thái (State Machine) của Agent; Tự động thử lại (Retry) tác vụ lỗi. |
| **Cổng mạng** | Cloudflare Tunnel (`cloudflared`) | Kênh truyền mã hóa Outbound-only | Tiếp nhận Webhook từ Meta/TikTok bắn về máy local an toàn mà không cần mở Port modem. |

---

## 3. Bản Kế hoạch Phân bổ Tài nguyên Phần cứng

Để máy tính chạy ổn định không bị tràn bộ nhớ (Out-of-Memory) dẫn đến sập nguồn Windows, tài nguyên của máy (16GB RAM / 6GB VRAM) được phân vùng nghiêm ngặt thông qua file cấu hình `.wslconfig`:

### Phân chia RAM (Tổng 16GB)

* **Hệ điều hành Windows 10 & Driver:** Giữ lại **5GB RAM** cho các tác vụ nền hệ thống.
* **WSL2 Sandbox (Cấp phát tối đa 11GB RAM):**
* *Ollama Engine (Chạy Llama 3.2 3B):* Chiếm **2.5GB RAM** hệ thống khi nạp mô hình vào bộ nhớ.
* *PostgreSQL & DuckDB:* Giới hạn sử dụng tối đa **2GB RAM** (Cấu hình `shared_buffers = 512MB` trong Postgres).
* *Redis Broker:* Giới hạn tối đa **500MB RAM** (Cấu hình `maxmemory 500mb` kèm chính sách xóa `volatile-lru`).
* *Celery Workers & FastAPI (4 tiến trình chạy song song):* Chiếm tối đa **3GB RAM**.
* *Bộ nhớ đệm dự phòng (Buffer/Cache cho OS Linux):* **3GB RAM**.



### Phân chia VRAM (Tổng 6GB trên GTX 1660 Super)

* *Llama 3.2 (3B) INT4:* Chiếm **1.8GB đến 2.2GB VRAM**.
* *Độ dài Context tối đa (Context Window):* Giới hạn ở mức **2048 tokens** để đảm bảo lượng VRAM biến thiên khi xử lý chuỗi không vượt quá **3.5GB VRAM**.
* *Phần VRAM còn lại (2.5GB):* Dành cho Windows Display Driver và tăng tốc phần cứng cơ bản.

---

## 4. Đặc tả Chi tiết Quy trình Vận hành 5 Bước (Data Pipeline)

```
[Bước 1: Kho Thượng Nguồn]
       │ Nhân viên quét barcode -> Cập nhật PostgreSQL -> Kích hoạt Trigger
       ▼
[Bước 2: Tiếp Thị Tự Nhiên]
       │ Celery Beat (9h sáng) -> Đọc tồn kho -> Gọi Gemini API (Sinh content/Hình ảnh) -> Đăng API tự động
       ▼
[Bước 3: Trạm Trung Gian - Analysis Loop]
       │ Khởi chạy mỗi 15 phút -> DuckDB gom số liệu Ads & Doanh thu -> XGBoost tính trọng số 
       │ -> DeepSeek-R1 API sinh JSON -> Gọi API tăng/giảm ngân sách Paid Ads
       ▼
[Bước 4: Chuyển Đổi Thương Mại]
       │ Khách nhắn tin -> Cloudflare Tunnel -> FastAPI -> Llama 3.2 (Local GPU) lọc Intent
       │ -> Nếu cần mua hàng -> Gọi Gemini API (Kết hợp pgvector RAG) -> Trả tin nhắn Real-time
       ▼
[Bước 5: Kho Hạ Nguồn]
       │ Chốt đơn -> Ghi PostgreSQL -> Bắn Webhook sang Đơn vị vận chuyển (3PL) -> Đóng vòng lặp dữ liệu về Bước 3

```

---

## 5. Quy trình Cấu hình Hạ tầng Kháng lỗi (24/7 Resilience Setup)

### Bước 1: Cấu hình Hệ điều hành Windows Kháng sập (OS Hardening)

1. **Vô hiệu hóa Sleep hoàn toàn:** `Control Panel` -> `Power Options` -> Thiết lập `Put the computer to sleep = Never`.
2. **Chặn Windows Update Tự khởi động lại máy:** * Mở `gpedit.msc` -> Tìm đến đường dẫn: `Computer Configuration \ Administrative Templates \ Windows Components \ Windows Update`.
* Kích hoạt chính sách: `No auto-restart with logged on users for scheduled automatic updates installations` chuyển sang **Enabled**.


3. **Tự động Đăng nhập khi mất nguồn có điện lại:** Cấu hình BIOS của bo mạch chủ ASUS sang chế độ `Restore on AC Power Loss = Power On`. Sử dụng công cụ `Autologon` của Microsoft để hệ thống tự động đăng nhập vào Windows mà không cần gõ mật khẩu sau khi khởi động.

### Bước 2: Cấu hình Tự phục hồi tầng Phần mềm (Docker Container Recovery)

Toàn bộ mã nguồn phải được quản lý bằng tệp lệnh `docker-compose.yml` cấu hình thuộc tính `restart: always`. Nếu tiến trình Python bị crash do lỗi logic hoặc tràn bộ nhớ, Docker Daemon sẽ tự khởi động lại container đó ngay lập tức:

```yaml
version: '3.8'

services:
  local-redis:
    image: redis:7-alpine
    container_name: production_redis_broker
    restart: always
    command: redis-server --appendonly yes --maxmemory 500mb --maxmemory-policy volatile-lru
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  intent-router-ai:
    image: ollama/ollama
    container_name: local_ollama_engine
    restart: always
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    volumes:
      - ollama_storage:/root/.ollama

  agent-conversion-service:
    build: ./conversion_agent
    container_name: live_chatbot_agent
    restart: always
    depends_on:
      - local-redis
    environment:
      - REDIS_URL=redis://local-redis:6379/0
      - GEMINI_API_KEY=${GEMINI_API_KEY}

```

### Bước 3: Bảo mật Mạng bằng Cloudflare Tunnel

Để nhận webhook tin nhắn từ Facebook/TikTok mà không cần mở Port trên Modem (tránh bị quét IP và tấn công mạng):

1. Cài đặt container `cloudflared` chạy song song trong cụm Docker Compose.
2. Thiết lập đường dẫn ngầm: `Khách hàng ──► Domain HTTPS Cloudflare ──► cloudflared container ──► Local FastAPI (Port 8000)`.

---

## 6. Tiêu chuẩn Quản trị Dữ liệu & Quy tắc Xử lý ngoại lệ (Governance & Failover)

* **Tính Độc Bản (Idempotency Key):** Mỗi tin nhắn từ webhook gửi về hoặc mỗi lệnh tạo đơn hàng ở Bước 4 chuyển sang Bước 5 bắt buộc phải đính kèm một mã băm `Idempotency-Key` (Cấu trúc: `MD5(Platform_Sender_ID + Message_Timestamp)`). Hệ thống kiểm tra key này trong Redis trước khi xử lý, đảm bảo nếu mạng bị chập chờn và webhook gửi trùng, hệ thống sẽ không phản hồi hai lần hoặc tạo hai đơn hàng trùng lặp.
* **Bảo vệ dữ liệu (PII Data Masking):** Trước khi dữ liệu hội thoại từ máy local được gửi lên API đám mây của Gemini/DeepSeek, một module Python nội bộ sẽ quét chuỗi bằng biểu thức chính quy (Regex) nhằm ẩn danh hóa số điện thoại, địa chỉ và tên khách hàng thành cấu trúc `<PHONE>`, `<ADDRESS>` để tuân thủ bảo mật dữ liệu. Thông tin gốc được lưu an toàn tại PostgreSQL nội bộ.
* **Cơ chế Dự phòng Mô hình (Model Fallback):** Triển khai thư viện `Tenacity` trong mã nguồn Python. Khi Agent gọi API DeepSeek ở Bước 3 để phân tích ngân sách mà gặp lỗi phản hồi (HTTP 503 / Rate Limit), hệ thống tự động kích hoạt cơ chế dịch chuyển luồng (Circuit Breaker) để chuyển cấu trúc Prompt sang mô hình **Gemini 1.5 Pro** làm phương án dự phòng, giữ cho mạch vận hành không bị đứt gãy.
* **Giám sát Chủ động qua Telegram:** Một worker chạy ngầm bằng thư viện `psutil` trên máy local thực hiện kiểm tra tài nguyên sau mỗi 60 giây. Nếu phát hiện RAM khả dụng < 1GB hoặc nhiệt độ GPU vượt quá 85°C, hệ thống tự động gửi một thông báo khẩn cấp (Alert) kèm thông số chi tiết qua Telegram Bot để bạn can thiệp từ xa.