Xây dựng phần khung (Scaffolding) trước, kiểm tra kết nối (Ping-Check) sau đó mới đắp Logic Agent vào.

Dưới đây là lộ trình chia Phase:

---

## Phase 1: Thiết lập "Hạ tầng" (Local Environment & Docker Base)

**Mục tiêu:** Tạo môi trường chạy ổn định cho AI Assistant đọc hiểu, cấu hình thành công các Container nền tảng mà không bị xung đột tài nguyên.

* **Các bước thực hiện:**
1. Cấu hình file `.wslconfig` trên Windows để giới hạn RAM/CPU cho WSL2.
2. Viết file `docker-compose.yml` khởi tạo 3 Container nền tảng: **PostgreSQL (kèm pgvector)**, **Redis (cho Celery/Streams)**, và **Ollama** (đã map GPU).
3. Chạy Ollama nội bộ và tải mô hình `llama3.2:3b`.

* **Tiêu chí nghiệm thu (Definition of Done):** Toàn bộ container ở trạng thái `Up`, gõ lệnh `ollama run llama3.2:3b` trên terminal local trả về kết quả dưới 2 giây.

---

## Phase 2: Trục Dữ liệu & Cổng kết nối bảo mật (Data Layer & Cloudflare Tunnel)

**Mục tiêu:** Xây dựng Schema cơ sở dữ liệu và mở cổng HTTPS an toàn để sẵn sàng nhận Webhook từ Facebook/TikTok mà không lo nghẽn mạng.

* **Các bước thực hiện:**
1. Tạo Schema PostgreSQL cho các bảng: `inventory` (Kho), `orders` (Đơn hàng), `agent_states` (Trạng thái hội thoại LangGraph), và `ads_metrics` (Log chi phí quảng cáo).
2. Tạo một ứng dụng `FastAPI` cơ bản với một Endpoint `/webhook` đơn giản để in ra log (Print raw request).
3. Tích hợp Container `cloudflared` vào Docker Compose để ánh xạ Port của FastAPI ra một Domain HTTPS miễn phí của Cloudflare.

* **Tiêu chí nghiệm thu (Definition of Done):** Sử dụng Postman hoặc điện thoại gửi một request POST vào URL HTTPS của Cloudflare, terminal local hiển thị log JSON ngay lập tức.

---

## Phase 3: Xây dựng Lớp Phòng vệ Chốt đơn (Step 4 - Phase A: Intent Router)

**Mục tiêu:** Ứng dụng GPU local chạy Llama 3.2 3B để phân loại tin nhắn khách hàng nhằm tối ưu hóa chi phí token.

* **Các bước thực hiện:**
1. Viết module kết nối FastAPI với Ollama API (`localhost:11434`).
2. Xây dựng System Prompt ép Llama 3.2 bắt buộc phải trả về 1 trong 3 từ khóa định dạng JSON sạch: `{"intent": "GREETING"}`, `{"intent": "PURCHASE"}`, hoặc `{"intent": "SPAM"}`.
3. Thiết lập logic rẽ nhánh: Nếu không phải `PURCHASE`, trả lời tự động bằng template (Không gọi lên Gemini).

* **Tiêu chí nghiệm thu (Definition of Done):** Chạy Unit test thành công. Thời gian xử lý phân loại (TTFT) của mô hình local trên card 1660 Super phải dưới 200ms.

---

## Phase 4: Core Agent Chốt đơn & Tích hợp RAG (Step 4 - Phase B: Conversion Core)

**Mục tiêu:** Hoàn thiện Agent chốt đơn thông minh sử dụng Gemini API qua mạng Đám mây kết hợp Context Caching và Vector Search nội bộ.

* **Các bước thực hiện:**
1. Viết script tự động chuyển đổi danh mục sản phẩm (Text) thành Vector Embeddings bằng Vertex AI API và lưu vào bảng `pgvector` ở Phase 2.
2. Sử dụng thư viện `LangGraph` để thiết lập State Machine cho cuộc hội thoại: Nhận tin nhắn -> Tìm Vector sản phẩm phù hợp -> Gọi Gemini API (Kèm Context Cache) -> Trả kết quả và lưu trạng thái vào DB.

* **Tiêu chí nghiệm thu (Definition of Done):** Giả lập một chuỗi chat 5 câu liên tiếp của khách hàng mua sản phẩm, Agent phải nhớ ngữ cảnh câu trước, truy xuất đúng giá tiền sản phẩm từ Database và không bị ảo tưởng thông tin.

---

## Phase 5: Vòng lặp Phân tích & Tự động hóa Quảng cáo (Step 3: Analysis Loop)

**Mục tiêu:** Hiện thực hóa Trạm trung gian, tính toán dữ liệu bằng DuckDB và ra quyết định thay đổi ngân sách bằng DeepSeek-R1 API.

* **Các bước thực hiện:**
1. Cấu hình `Celery Beat` để kích hoạt một Task Python chạy ngầm định kỳ mỗi 15 phút.
2. Sử dụng `DuckDB` đọc trực tiếp dữ liệu từ bảng `orders` và `ads_metrics` trong PostgreSQL để tính toán chỉ số ROAS.
3. Đưa chỉ số ROAS vào Prompt của **DeepSeek-R1 API**, yêu cầu sinh mã lệnh JSON để gọi API tăng/giảm ngân sách Paid Ads.

* **Tiêu chí nghiệm thu (Definition of Done):** Chạy thử nghiệm task, log hệ thống hiển thị chính xác bảng phân tích số liệu của DuckDB và sinh ra payload JSON chuẩn của DeepSeek-R1 mà không có ký tự text thừa.

---

## Phase 6: Đóng vòng Logistics & Vận hành Kháng lỗi (Step 1, 5 & Hardening)

**Mục tiêu:** Đồng bộ trạng thái kho thượng nguồn/hạ nguồn, tích hợp tính năng Idempotency bảo vệ đơn hàng và thiết lập hệ thống cảnh báo 24/7.

* **Các bước thực hiện:**
1. Viết Middleware kiểm tra cấu trúc mã `Idempotency-Key` bằng Redis nhằm ngăn chặn trùng lặp đơn hàng khi mạng lỗi.
2. Viết hàm kết nối Webhook giả lập tới đơn vị vận chuyển (3PL). Khi đơn hàng chuyển sang trạng thái "Đang giao", tự động trừ số lượng tồn kho trong bảng `inventory`.
3. Viết Script kiểm tra tài nguyên máy (RAM, CPU, Nhiệt độ GPU), nếu vượt ngưỡng cảnh báo thì tự động gửi tin nhắn qua Telegram Bot.