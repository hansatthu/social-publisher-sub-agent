# gemini-conversation
Exported on: 3/18/2026, 10:16:52 AM

---

**You:**
Tôi có build một tool để viết bài seo tự động. Hiện tại dự án của tôi có thể hiểu theo kiến trúc 5 lớp chính, với các file quan trọng như sau.  Điểm vào và cấu hình  app.py: giao diện Streamlit, điều phối toàn bộ thao tác người dùng (generate, publish WP, upload Woo, progress, stop khẩn cấp).  pyproject.toml: khai báo dependency và cấu hình project Python.  README.md: hướng dẫn chạy app, định dạng dữ liệu, luồng vận hành.  .env: biến môi trường cho WordPress, WooCommerce, API key, timeout, retry.  Tầng dữ liệu (Database)  session.py: khởi tạo kết nối DB, init schema.  models.py: định nghĩa model dữ liệu và trạng thái bài viết.  article\_repository.py: CRUD và truy vấn nghiệp vụ cho bài viết (pending, processing, publishable, save AI output...).  Tầng AI/SEO  agent.py: engine generate nội dung, hậu xử lý title/meta/content, enforce backlink, kiểm tra ngôn ngữ.  prompts.py: system prompt + user prompt + danh sách service link pair.  seo\_scoring\_service.py: chấm điểm SEO sau generate.  Tầng xử lý nội dung/media  orchestrator.py: orchestration chính giữa DB, AI, WP/Woo, và tiến trình đa luồng.  content\_service.py: inject ảnh vào markdown, upload inline image concurrent.  media\_service.py: xử lý ảnh, metadata EXIF/XMP, tạo tag ảnh responsive.  Tầng tích hợp ngoài (External Integrations)  wordpress.py: upload media và publish bài qua WP REST API.  woocommerce.py: tạo/cập nhật sản phẩm WooCommerce, map ảnh/category/SKU.  google\_sheets.py: đồng bộ dữ liệu sang Google Sheets.  Dữ liệu mẫu và file tạm  woocommerce\_products\_sample.csv: mẫu CSV upload sản phẩm.  tmp: nơi chứa script/test output tạm trong quá trình debug.  sample\_outputs: thư mục output mẫu khi test generate.    
 sơ đồ luồng:  flowchart TD      A[UI Streamlit\nui/app.py] --> B[Task State + Worker Threads\nui/app.py]      B --> C[ArticleOrchestrator\nservices/orchestrator.py]    
     C --> D[ArticleRepository\nservices/article\_repository.py]      D --> E[(SQLite DB\ndatabase/models.py + database/session.py)]    
     C --> F[SEOAgent\nllm\_engine/agent.py]      F --> G[Prompt Builder\nllm\_engine/prompts.py]      F --> H[Generated JSON\ntitle + meta + content]      C --> I[SEO Scoring\nservices/seo\_scoring\_service.py]    
     C --> J[ContentService\nservices/content\_service.py]      J --> K[MediaService\nservices/media\_service.py]    
     C --> L[WordPress Publisher\nintegrations/wordpress.py]      C --> M[WooCommerce Publisher\nintegrations/woocommerce.py]      C --> N[Google Sheets Sync\nintegrations/google\_sheets.py]    
     H --> D      I --> D      K --> L      J --> L      D --> A      L --> A      M --> A      N --> A    
     subgraph Generate Pipeline        F --> H        H --> D        D --> I        I --> D      end    
     subgraph Publish Pipeline        D --> J        J --> K        K --> L        L --> D      end    
 tôi cần refactor các files sau:  app.py  Tách nhỏ UI thành module (sidebar, processing panel, publishing panel, product panel). Đây là nơi rối nhất nhưng ít ảnh hưởng trực tiếp tới prompt/rule AI nếu giữ nguyên dữ liệu đầu vào/đầu ra.  orchestrator.py  Refactor cấu trúc worker/thread, logging, error handling. Giữ nguyên contract gọi sang agent/publisher là an toàn.  article\_repository.py  Tối ưu query, gom helper DB, đặt tên lại hàm nội bộ.  google\_sheets.py  Có thể tách transport + mapping mà gần như không ảnh hưởng rule generate.  woocommerce.py  Refactor độc lập với bài viết SEO (miễn giữ nguyên payload mapping hiện tại).    
 nếu chưa nắm rõ context thì hỏi hoặc yêu cầu. còn nếu đã nắm rõ context rồi thì suggest idea refactor và plan

**Gemini:**
Chào bạn, với tư cách là Senior AI Data Engineer, tôi đã xem xét kỹ lưỡng kiến trúc 5 lớp và toàn bộ source code bạn cung cấp.

Kiến trúc hiện tại của bạn phân lớp khá rõ ràng (UI, Orchestrator, Repository, Integration). Tuy nhiên, việc sử dụng Streamlit để quản lý Multi-threading (`ThreadPoolExecutor`, `threading.Thread`) kết hợp với Global State (`TaskStateManager`) trong `app.py` tiềm ẩn nhiều rủi ro về memory leak, thread starvation và race condition khi scale. Đồng thời, một số file đang vi phạm nguyên tắc Single Responsibility Principle (SRP).

Dưới đây là bản phân tích kỹ thuật và kế hoạch refactor (Refactoring Plan) chi tiết cho 5 file bạn yêu cầu, tập trung vào tính bảo trì (maintainability), khả năng mở rộng (scalability) và hiệu năng (performance).

### 1. Phân tích và Plan Refactor `app.py` (UI Layer)

**Vấn đề hiện tại:**

* File quá lớn (>1400 lines), chứa toàn bộ logic render UI cho cả Post Automation và Product Automation.
* Trộn lẫn logic xử lý file CSV/Excel (`_read_products_csv_with_fallback`) vào UI controller.
* State Machine (`TaskStateManager`) được định nghĩa ngay trong file UI.

**Hướng giải quyết (Modularization):**

* **Tách State Management:** Di chuyển `TaskStateManager` và các biến global state sang một file riêng (VD: `ui/state_manager.py`). Điều này giúp tách biệt logic quản lý lock/progress khỏi logic render.
* **Tách Data Processing:** Đưa logic đọc và xử lý CSV/Excel (`_read_products_input_file`, logic detect encoding) ra một module helper riêng (VD: `utils/file_parser.py`).
* **Component Pattern cho UI:** Tách `SEOAutomationUI` thành các module nhỏ theo Domain:

* `ui/components/sidebar.py`
* `ui/components/post_processing_panel.py`
* `ui/components/post_publishing_panel.py`
* `ui/components/product_automation_panel.py`
* `app.py` sẽ chỉ đóng vai trò là Entry Point, import các components và gọi hàm `render()`.

### 2. Phân tích và Plan Refactor `orchestrator.py` (Orchestration Layer)

**Vấn đề hiện tại:**

* Khởi tạo và quản lý thread pool (`_sheets_sync_executor`) trực tiếp trong class.
* `publish_woocommerce_product` đang chứa logic chuẩn hóa dữ liệu (`_normalize_woocommerce_row`).

**Hướng giải quyết:**

* **Tách Data Normalization:** Di chuyển `_normalize_woocommerce_row` ra một DTO (Data Transfer Object) hoặc Validator layer (sử dụng `pydantic` để validate payload trước khi đẩy vào Orchestrator).
* **Concurrency Management:** Abstract logic xử lý bất đồng bộ (Google Sheets sync) ra một `BackgroundTaskManager` hoặc `AsyncDispatcher`. Việc Orchestrator tự khởi tạo `ThreadPoolExecutor` khiến việc quản lý lifecycle của thread khó khăn khi ứng dụng shutdown.
* **Standardize Return Types:** Thống nhất kiểu trả về của các hàm (hiện tại trả về `Tuple[bool, str]`, `Tuple[bool, str, str]`) thành các object `Result` hoặc `ResponseDTO` chuẩn để UI dễ parse.

### 3. Phân tích và Plan Refactor `article_repository.py` (Data Access Layer)

**Vấn đề hiện tại:**

* Hàm `get_datagrid_overview` đang thực hiện UI formatting (VD: gán `"Chưa gán"`, `"None"`, format datetime thành string) ngay trong lúc query. Điều này vi phạm Separation of Concerns.
* Một số query sử dụng `.all()` không có limit/pagination, có thể gây tràn RAM (O(N) Space) khi volume dữ liệu lớn.

**Hướng giải quyết:**

* **Tách View Models:** `get_datagrid_overview` chỉ nên trả về danh sách các object (hoặc dict) thuần túy. Việc format `"Chưa gán"` hay datetime str phải được đẩy lên UI Layer (Streamlit formatters) hoặc một Presenter layer.
* **Tối ưu Query:** Áp dụng server-side pagination (limit/offset) hoặc chunking cho các hàm như `get_all_articles_for_sync`.
* **Gom nhóm Session:** Tách `_raise_repository_error` và context manager của SQLAlchemy thành một decorator Base để tái sử dụng, giảm boilerplate code `with SessionLocal() as db:` lặp lại liên tục.

### 4. Phân tích và Plan Refactor `google_sheets.py` (Integration Layer)

**Vấn đề hiện tại:**

* Class `GoogleSheetsAppender` đang đảm nhiệm 2 nhiệm vụ phân nhánh bằng `if self.mode == "webhook"`. Cấu trúc này làm tăng Cyclomatic Complexity và khó viết Unit Test.

**Hướng giải quyết (Strategy Pattern):**

* Tạo một abstract base class (interface) `BaseSheetsTransport`.
* Tạo 2 implementation: `GspreadTransport` và `WebhookTransport`.
* Sử dụng Dependency Injection: Lúc khởi tạo `GoogleSheetsAppender`, inject transport tương ứng dựa trên biến môi trường. Điều này giúp code decoupled hoàn toàn.

### 5. Phân tích và Plan Refactor `woocommerce.py` (Integration Layer)

**Vấn đề hiện tại:**

* File chứa class `WooCommercePublisher` quá khổng lồ, ôm đồm từ cấu hình API, parsing error, xử lý Category Tree (`_find_or_create_category_ids`), kiểm tra SKU, đến xử lý metadata tiếng Trung (`_build_zh_meta_updates`).

**Hướng giải quyết (Domain Separation):**

* **Tách API Client:** Abstract `_request`, error handling, auth ra một class `WooCommerceAPIClient` thuần túy.
* **Tách Domain Services:**

* `WooCategoryService`: Chứa toàn bộ logic `list_product_categories`, `_find_or_create_category_ids`, mapping category tree.
* `WooProductService`: Chứa logic `create_product`, validate SKU, update meta\_data.
* **Tách Logic Ngôn ngữ:** Các hàm helper như `_looks_like_chinese_text` nên được chuyển vào module chung như `utils/language_detector.py`.

---

**Kế hoạch triển khai (Execution Plan):**
Để hạn chế tối đa rủi ro gãy luồng (regression bug), chúng ta nên refactor theo thứ tự từ dưới lên trên (Bottom-Up):

1. **Phase 1:** Refactor `google_sheets.py` (Strategy Pattern) và `article_repository.py` (Gỡ UI formatting).
2. **Phase 2:** Refactor `woocommerce.py` (Tách Client và Domain Services).
3. **Phase 3:** Refactor `orchestrator.py` (Dọn dẹp payload normalization, DTOs).
4. **Phase 4:** Tách nhỏ `app.py` thành các UI components.

Bạn muốn bắt tay vào **Phase 1 (Repository & Sheets integration)** hay muốn ưu tiên tháo gỡ sự phức tạp ở **Phase 4 (app.py)** trước? Dựa trên lựa chọn của bạn, tôi sẽ cung cấp mã nguồn refactor cụ thể theo chuẩn.

---

**You:**
ok cụ thể từng phase đi

**Gemini:**
Chào bạn, quyết định đi từng phase (Bottom-Up) là một chiến lược refactoring rất an toàn và chuyên nghiệp, giúp chúng ta kiểm soát rủi ro hồi quy (regression) tốt nhất.

Chúng ta sẽ bắt đầu với **Phase 1: Chuẩn hóa Integration Layer (`google_sheets.py`) và Data Access Layer (`article_repository.py`)**.

### 1. Refactor `google_sheets.py` (Áp dụng Strategy Pattern)

**Vấn đề:** Hiện tại, class `GoogleSheetsAppender` đang phải gánh hai logic xử lý hoàn toàn khác biệt (Gspread API và Webhook Apps Script) thông qua việc check `if self.mode == "webhook":` ở mọi method. Việc này vi phạm Open/Closed Principle (OCP).

**Giải pháp:** Tôi sẽ tách logic này thành các class riêng biệt kế thừa từ một Interface chung (`BaseSheetsTransport`). `GoogleSheetsAppender` sẽ chỉ đóng vai trò Context để gọi interface.

```
# integrations/google_sheets.py
import json
import os
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime

import gspread
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

class GoogleSheetsIntegrationError(Exception):
    pass

# --- 1. Interface & Constants ---
HEADERS = [
    "id", "created_at", "created_date", "created_month", "keyword",
    "title", "slug", "meta_description", "language", "category_name",
    "status", "wp_post_id", "wp_post_url", "seo_score", "seo_notes",
]

def article_to_row(article: Any) -> List[str]:
    """Helper map Article object to List[str]"""
    created_at = article.created_at
    created_at_value = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else ""
    created_date_value = created_at.strftime("%Y-%m-%d") if created_at else ""
    created_month_value = created_at.strftime("%Y-%m") if created_at else ""
    status_val = getattr(article.status, "value", str(article.status)) if article.status else ""

    return [
        str(article.id), created_at_value, created_date_value, created_month_value,
        article.keyword or "", article.title or "", article.slug or "",
        article.meta_description or "", article.language or "", article.category_name or "",
        status_val, str(article.wp_post_id or ""), article.wp_post_url or "",
        str(article.seo_score) if getattr(article, "seo_score", None) is not None else "",
        article.seo_notes or "",
    ]

class BaseSheetsTransport(ABC):
    """Abstract Strategy cho Google Sheets Integration"""
    @abstractmethod
    def upsert_row(self, article: Any, worksheet_name: str) -> None:
        pass

    @abstractmethod
    def delete_rows(self, article_ids: List[int], worksheet_name: str) -> int:
        pass

    @abstractmethod
    def replace_all(self, articles: List[Any], worksheet_name: str) -> int:
        pass

# --- 2. Implementations ---
class WebhookTransport(BaseSheetsTransport):
    def __init__(self, webhook_url: str, secret: str, batch_size: int, timeout: int, max_retries: int):
        self.webhook_url = webhook_url
        self.secret = secret
        self.batch_size = batch_size
        self.timeout = timeout
        self.max_retries = max_retries

    def _post_webhook(self, action: str, payload: Dict[str, Any]) -> None:
        # Giữ nguyên logic retry và fallback payload của bạn ở đây
        # ... (logic request requests.post tương tự file cũ)
        pass

    def upsert_row(self, article: Any, worksheet_name: str) -> None:
        row_dict = dict(zip(HEADERS, article_to_row(article)))
        self._post_webhook("upsert", {"worksheet_name": worksheet_name, "row": row_dict, "rows": [row_dict]})

    def delete_rows(self, article_ids: List[int], worksheet_name: str) -> int:
        normalized_ids = [int(aid) for aid in article_ids if aid is not None]
        if not normalized_ids: return 0
        self._post_webhook("delete_ids", {"worksheet_name": worksheet_name, "article_ids": normalized_ids})
        return len(normalized_ids)

    def replace_all(self, articles: List[Any], worksheet_name: str) -> int:
        rows = [dict(zip(HEADERS, article_to_row(article))) for article in articles]
        self._post_webhook("replace_all", {"worksheet_name": worksheet_name, "headers": HEADERS, "rows": rows})
        return len(rows)

class GspreadTransport(BaseSheetsTransport):
    def __init__(self, sheet_id: str):
        self.sheet_id = sheet_id
        # Khởi tạo self.client, self.spreadsheet tương tự code cũ
        # ...
        
    def _get_or_create_worksheet(self, worksheet_name: str):
        # ... (Logic tạo worksheet và append headers)
        pass

    def upsert_row(self, article: Any, worksheet_name: str) -> None:
        worksheet = self._get_or_create_worksheet(worksheet_name)
        row_values = article_to_row(article)
        # ... (Logic tìm id_cell và update/append)
        pass

    def delete_rows(self, article_ids: List[int], worksheet_name: str) -> int:
        # ... (Logic batch_update xoá dimension ROWS)
        pass

    def replace_all(self, articles: List[Any], worksheet_name: str) -> int:
        worksheet = self._get_or_create_worksheet(worksheet_name)
        worksheet.clear()
        rows = [article_to_row(article) for article in articles]
        if rows: worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        return len(rows)

# --- 3. Context Class ---
class GoogleSheetsAppender:
    def __init__(self, worksheet_name: str = "Articles"):
        load_dotenv()
        self.worksheet_name = os.getenv("GOOGLE_SHEET_WORKSHEET_NAME", worksheet_name)
        webhook_url = os.getenv("GOOGLE_APPS_SCRIPT_WEBHOOK_URL", "").strip()
        
        # Dependency Injection tại runtime
        if webhook_url:
            self.transport = WebhookTransport(
                webhook_url=webhook_url,
                secret=os.getenv("GOOGLE_APPS_SCRIPT_SECRET", "").strip(),
                batch_size=int(os.getenv("GOOGLE_APPS_SCRIPT_BATCH_SIZE", "50")),
                timeout=int(os.getenv("GOOGLE_APPS_SCRIPT_TIMEOUT_SECONDS", "15")),
                max_retries=int(os.getenv("GOOGLE_APPS_SCRIPT_MAX_RETRIES", "2"))
            )
        else:
            self.transport = GspreadTransport(sheet_id=os.getenv("GOOGLE_SHEET_ID", "").strip())

    def upsert_article_row(self, article: Any) -> None:
        self.transport.upsert_row(article, self.worksheet_name)

    def delete_rows_by_ids(self, article_ids: List[int]) -> int:
        return self.transport.delete_rows(article_ids, self.worksheet_name)

    def sync_all_articles(self, articles: List[Any]) -> int:
        return self.transport.replace_all(articles, self.worksheet_name)

```

---

### 2. Refactor `article_repository.py` (Tách View logic)

**Vấn đề:** Method `get_datagrid_overview` đang thực hiện formatting string như `a.title if a.title else "None"` hoặc ép kiểu `strftime`. Tại Data Access Layer, chúng ta chỉ nên trả về Data thuần túy. Việc format sẽ làm khó khăn nếu sau này backend cần trả JSON cho một frontend khác (ví dụ React thay vì Streamlit).

**Giải pháp:** Trả về Raw Dict. Formatting sẽ được di chuyển sang UI Layer.

```
# services/article_repository.py

    @staticmethod
    def get_datagrid_overview() -> List[Dict[str, Any]]:
        """
        [DSA Optimization] Projection Query: 
        Trả về Raw Data. Format/Presentation Logic phải được xử lý ở Presentation Layer.
        """
        try:
            with SessionLocal() as db:
                articles = db.query(
                    Article.id,
                    Article.title,
                    Article.meta_description,
                    Article.keyword,
                    Article.category_name,
                    Article.language,
                    Article.created_at,
                    Article.status,
                    Article.seo_score,
                ).order_by(Article.id.desc()).all() 
                
                # Trả về raw data, loại bỏ if/else string formatting
                return [{
                    "id": a.id,
                    "title": a.title,
                    "meta_description": a.meta_description,
                    "keyword": a.keyword,
                    "category_name": a.category_name,
                    "language": a.language,
                    "created_at": a.created_at, # Giữ nguyên object datetime
                    "status": a.status.value if a.status else None,
                    "seo_score": a.seo_score,
                } for a in articles]
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error("tải danh sách bài viết", error)

```

**Lưu ý cho UI (`app.py`):** Khi gọi hàm này, tại `app.py`, bạn sẽ map lại Dataframe như sau:

```
df = pd.DataFrame(data)
df.rename(columns={"id": "ID", "title": "Tiêu đề", ...}, inplace=True)
df["Tiêu đề"] = df["Tiêu đề"].fillna("None")
df["Ngày tạo"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")

```

Bạn có muốn review kỹ lại kiến trúc Interface của `BaseSheetsTransport` trước khi chúng ta chuyển sang **Phase 2 (`woocommerce.py`)** không?

---

**You:**
chuyển sang các phase tiếp theo

**Gemini:**
Tuyệt vời. Chúng ta sẽ tiếp tục với **Phase 2, Phase 3 và Phase 4**. Tôi sẽ thiết kế các cấu trúc skeleton (bộ khung) chuẩn mực để bạn thấy rõ sự phân tách trách nhiệm (Separation of Concerns).

---

### Phase 2: Refactor `woocommerce.py` (Domain Driven Separation)

**Vấn đề:** `WooCommercePublisher` hiện tại là một "God Object" (lớp ôm đồm quá nhiều chức năng): từ cấu hình HTTP Client, Auth, phân tích lỗi, đến quản lý Category Tree phức tạp và tạo Product.

**Giải pháp:** Áp dụng nguyên tắc SRP (Single Responsibility Principle) bằng cách chia thành 3 phần:

1. **`WooCommerceAPIClient`**: Chỉ làm nhiệm vụ gọi HTTP, cấu hình Auth, Retry, Timeout và sanitize error log.
2. **`WooCategoryService`**: Chỉ quản lý danh mục (tìm, tạo, update meta tiếng Trung cho category).
3. **`WooProductService`**: Chuyên xử lý tạo/sửa product, validate SKU, map meta data sản phẩm.

```
# integrations/woocommerce/client.py
import os
import requests
from dotenv import load_dotenv

class WooCommerceIntegrationError(Exception): pass

class WooCommerceAPIClient:
    """Core HTTP Client, chịu trách nhiệm kết nối, auth và error sanitization"""
    def __init__(self):
        load_dotenv()
        self.base_url = (os.getenv("WC_API_URL") or os.getenv("WP_SITE_URL") or "").rstrip("/")
        self.auth = (os.getenv("WC_CONSUMER_KEY", "").strip(), os.getenv("WC_CONSUMER_SECRET", "").strip())
        self.timeout = int(os.getenv("WC_REQUEST_TIMEOUT_SECONDS", "75"))
        
        if not self.base_url or not self.auth[0]:
            raise WooCommerceIntegrationError("Thiếu cấu hình WC API trong .env")

    def request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/wp-json/wc/v3/{endpoint.lstrip('/')}"
        try:
            response = requests.request(method, url, auth=self.auth, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            # TODO: Di chuyển logic _sanitize_error_text và _build_readable_error_detail vào đây
            raise WooCommerceIntegrationError(f"API Error: {str(e)}")

# integrations/woocommerce/category_service.py
class WooCategoryService:
    """Domain Service quản lý Category Tree"""
    def __init__(self, api_client: WooCommerceAPIClient):
        self.api = api_client

    def list_product_categories(self) -> list[dict]:
        # Thực hiện gọi self.api.request("GET", "products/categories")
        pass

    def find_or_create_category_ids(self, category_names: list[str]) -> list[int]:
        # Bê logic phân tích ancestor chain và resolve existing ID vào đây
        pass

    def update_category_zh_meta(self, category_id: int, name_zh: str, desc_zh: str):
        # Update term meta
        pass

# integrations/woocommerce/product_service.py
class WooProductService:
    """Domain Service quản lý Product"""
    def __init__(self, api_client: WooCommerceAPIClient, category_service: WooCategoryService):
        self.api = api_client
        self.category_service = category_service # Inject category service để dùng khi cần map danh mục

    def get_product_by_sku(self, sku: str) -> dict:
        pass

    def create_product(self, payload: dict) -> dict:
        # Xử lý logic tạo product, catch duplicate SKU, retry
        pass

```

---

### Phase 3: Refactor `orchestrator.py` (DTOs & Worker Management)

**Vấn đề:** 1. Hàm `_normalize_woocommerce_row` nằm trong Orchestrator, biến nơi này thành chỗ chứa logic parsing data.
2. Trả về Tuple thô `(bool, str, str)` gây khó khăn cho việc mở rộng (ví dụ sau này cần trả thêm `product_id`).
3. Khởi tạo `ThreadPoolExecutor` trực tiếp có thể gây leak nếu ứng dụng restart nhiều lần.

**Giải pháp:**

1. Tạo Data Transfer Object (DTO) bằng `dataclasses`.
2. Tạo Response Object chuẩn.

```
# services/dtos/woocommerce_dto.py
from dataclasses import dataclass, field
from typing import List, Optional, Any
import re

@dataclass
class WooCommerceProductDTO:
    name: str
    regular_price: str = ""
    description: str = ""
    short_description: str = ""
    name_zh: str = ""
    sku: str = ""
    stock_quantity: Optional[int] = None
    category_names: List[str] = field(default_factory=list)
    image_urls: List[dict] = field(default_factory=list)
    update_zh_existing: bool = False

    @classmethod
    def from_csv_row(cls, row_data: dict[str, Any]) -> "WooCommerceProductDTO":
        """Di chuyển toàn bộ logic _normalize_woocommerce_row từ Orchestrator sang đây"""
        # Parsing logic...
        return cls(
            name=str(row_data.get("name", "")).strip(),
            sku=str(row_data.get("sku", "")).strip(),
            # ... map các field khác
        )

# services/dtos/response_dto.py
@dataclass
class OrchestratorResponse:
    is_success: bool
    message: str
    data: Optional[Any] = None

# services/orchestrator.py
class ArticleOrchestrator:
    # ...
    def publish_woocommerce_product(self, dto: WooCommerceProductDTO, status_val: str = "draft") -> OrchestratorResponse:
        """Nhận DTO đã chuẩn hóa, không cần parsing lại"""
        if not self.wc_publisher:
            return OrchestratorResponse(False, "WooCommerce chưa được cấu hình.")
        try:
            # Gọi product service
            wc_response = self.wc_publisher.product_service.create_product(payload=dto.__dict__)
            return OrchestratorResponse(
                is_success=True, 
                message=f"Tạo thành công: {dto.name}", 
                data={"url": wc_response.get("product_url")}
            )
        except Exception as e:
            return OrchestratorResponse(False, f"Lỗi: {str(e)}")

```

---

### Phase 4: Refactor `app.py` (UI Modularization)

**Vấn đề:** `app.py` dài hơn 1400 dòng, định nghĩa cả Global State, chứa logic đọc CSV và dựng UI bằng Streamlit. Khi team đông người hoặc tính năng phình to, file này sẽ gặp hiện tượng "Merge Conflict Hell".

**Giải pháp:** Cấu trúc lại thư mục UI.

**Cấu trúc thư mục đề xuất:**

```
ui/
├── app.py                 # (Entry Point) Chỉ chứa Layout shell và routing
├── state.py               # Chứa TaskStateManager và logic singleton
├── components/
│   ├── sidebar.py         # Quản lý quota, đề xuất từ khoá AI
│   ├── datagrid.py        # Bảng dữ liệu chính và chức năng sync sheets
│   ├── post_panel.py      # Panel xử lý Generate (Processing) & Publish bài viết
│   └── product_panel.py   # Toàn bộ logic Product Automation (WooCommerce)
└── utils/
    └── file_parser.py     # Chứa hàm _read_products_input_file, decode CSV

```

**Cách triển khai (Ví dụ cho `app.py` Entry Point mới):**

```
# ui/app.py
import streamlit as st
from ui.state import get_task_manager, init_global_state
from ui.components.sidebar import render_sidebar
from ui.components.datagrid import render_datagrid
from ui.components.post_panel import render_processing_panel, render_publishing_panel
from ui.components.product_panel import render_product_automation_panel
from services.orchestrator import ArticleOrchestrator
from services.article_repository import ArticleRepository

st.set_page_config(page_title="SEO Automation Tool", layout="wide")

def main():
    # 1. Khởi tạo State & Core Services (Sử dụng Dependency Injection)
    init_global_state()
    task_manager = get_task_manager()
    orchestrator = ArticleOrchestrator(...) # Inject các dependencies

    # 2. Đánh giá trạng thái hệ thống để khóa UI (is_locked)
    is_locked = task_manager.is_running() or ArticleRepository.has_processing_articles()

    # 3. Render Sidebar
    active_feature = render_sidebar(is_locked, orchestrator.agent)

    # 4. Routing dựa trên Feature chọn ở Sidebar
    if active_feature == "Product Automation":
        render_product_automation_panel(is_locked, orchestrator)
    else:
        render_datagrid(is_locked, orchestrator)
        st.divider()
        col1, col2 = st.columns(2, gap="large")
        with col1: 
            render_processing_panel(is_locked, orchestrator, task_manager)
        with col2: 
            render_publishing_panel(is_locked, orchestrator)

if __name__ == "__main__":
    main()

```

### Next Steps (Dành cho bạn)

Với bản thiết kế kiến trúc này:

1. Bạn không bị vỡ logic Generate/AI Prompt vì chúng ta hoàn toàn không đụng vào luồng dữ liệu truyền cho Agent.
2. Các external API calls đều được đóng gói.
3. Giao diện mượt mà và dễ maintain hơn.

Bạn có muốn tôi đi sâu vào việc viết code hoàn chỉnh cho một module cụ thể nào không (ví dụ: bóc tách logic đa luồng an toàn cho component `post_panel.py`)?

---

**You:**
code hoàn chỉnh cho module

**Gemini:**
Chào bạn, tôi sẽ cung cấp mã nguồn hoàn chỉnh cho module **UI State Management** và component **Post Processing Panel** (nơi chứa logic đa luồng phức tạp nhất của luồng sinh bài viết AI).

Việc bóc tách này giải quyết triệt để tình trạng "God Object" của `app.py`, tách biệt State ra khỏi UI Component, và cho phép tái sử dụng Orchestrator thông qua Dependency Injection (DI).

Dưới đây là mã nguồn cho 2 file quan trọng nhất trong cấu trúc mới.

### 1. `ui/state.py` (Quản lý State tập trung và Thread-safe)

File này chịu trách nhiệm duy trì trạng thái của các background workers, đảm bảo an toàn luồng (thread-safety) khi có nhiều thread cùng đọc/ghi kết quả, tách biệt hoàn toàn khỏi session state của Streamlit.

```
# ui/state.py
import threading
import streamlit as st

class TaskStateManager:
    """Singleton quản lý State an toàn luồng, tách biệt với st.session_state"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TaskStateManager, cls).__new__(cls)
                cls._instance._state_lock = threading.Lock()
                cls._instance._state = {
                    "is_running": False, "should_stop": False,
                    "completed": 0, "total": 1, "success": 0,
                    "errors": [], "feature": None, "success_msg": "",
                    "success_ids": [], "failed_ids": [],
                }
        return cls._instance

    def update(self, **kwargs):
        with self._state_lock:
            self._state.update(kwargs)

    def append_error(self, error_msg: str):
        with self._state_lock:
            self._state["errors"].append(error_msg)

    def append_success_id(self, article_id: int):
        with self._state_lock:
            if "success_ids" not in self._state:
                self._state["success_ids"] = []
            if article_id not in self._state["success_ids"]:
                self._state["success_ids"].append(article_id)

    def append_failed_id(self, article_id: int):
        with self._state_lock:
            if "failed_ids" not in self._state:
                self._state["failed_ids"] = []
            if article_id not in self._state["failed_ids"]:
                self._state["failed_ids"].append(article_id)

    def increment(self, success: bool = False):
        with self._state_lock:
            self._state["completed"] += 1
            if success:
                self._state["success"] += 1

    def get_snapshot(self) -> dict:
        with self._state_lock:
            return self._state.copy()

    def is_running(self) -> bool:
        with self._state_lock:
            return self._state.get("is_running", False)

@st.cache_resource
def get_task_manager(cache_version: str = "2026-03-18-task-state-v3") -> TaskStateManager:
    """Lấy instance của TaskStateManager, cache lại qua các lần rerun của Streamlit"""
    _ = cache_version
    return TaskStateManager()

def init_global_state():
    """Khởi tạo các global state cần thiết cho WooCommerce (nếu cần giữ lại)"""
    if "GLOBAL_TASK_STATE" not in st.session_state:
        st.session_state["GLOBAL_TASK_STATE"] = {
            "is_running": False,
            "should_stop": False,
            "completed": 0,
            "total": 1,
            "success": 0,
            "errors": [],
            "feature": None,
            "success_msg": "",
            "wc_last_result": None,
            "wc_success_links": [],
            "wc_failed_rows": [],
        }

```

### 2. `ui/components/post_panel.py` (Component xử lý viết bài AI)

Module này được tách ra từ hàm `render_processing_panel` khổng lồ trong `app.py`. Component này nhận `orchestrator` và `task_manager` thông qua parameters (Dependency Injection), giúp dễ dàng viết test và module hóa. Logic đa luồng (`background_generate_worker`) vẫn được giữ nguyên nhưng nằm gọn trong scope của module.

```
# ui/components/post_panel.py
import os
import queue
import threading
import time
from typing import Any, List

import streamlit as st
from services.article_repository import ArticleRepository, RepositoryError
from services.media_service import MediaService
from ui.state import TaskStateManager

# Mapping constant
LANGUAGE_MAP = {
    "Tiếng Việt": "Vietnamese",
    "Tiếng Trung Giản Thể": "Chinese (Simplified)",
}
ALT_STRATEGY_MAP = {
    "AI viết (Câu hoàn chỉnh max 14 từ)": "ai", 
    "Dùng title bài": "title", 
    "Keyword + local": "keyword_local"
}
MAX_GENERATE_WORKERS = max(1, int(os.getenv("MAX_GENERATE_WORKERS", "4") or 4))

def render_processing_panel(is_locked: bool, orchestrator: Any, task_manager: TaskStateManager):
    """
    Component chuyên trách UI và điều phối quá trình Generate bài viết bằng AI.
    Áp dụng DI: orchestrator và task_manager được tiêm từ ngoài vào.
    """
    st.subheader("Xử lý bài viết")

    # 1. Hiển thị Log kết quả từ Background Task
    current_state = task_manager.get_snapshot()
    if not is_locked and current_state["feature"] == "generate":
        _render_task_results(current_state, task_manager)

    # 2. Lấy danh sách bài viết PENDING/FAILED
    try:
        processable_options = ArticleRepository.get_processable_options()
    except RepositoryError as e:
        st.error(str(e))
        return

    selected_option_list = st.multiselect(
        "Chọn bài viết để viết hàng loạt (PENDING/GENERATE_FAILED)",
        options=list(processable_options.keys()),
        default=[],
        disabled=is_locked
    )

    if selected_option_list:
        _render_keyword_language_detection(selected_option_list)
        if not is_locked:
            _render_outline_step(selected_option_list, processable_options, orchestrator, is_locked)

    # 3. Cấu hình chèn ảnh và ngôn ngữ
    post_image_source_mode = st.radio(
        "Nguồn ảnh chèn bài",
        ["Upload local", "WP Media (đã có sẵn)"],
        horizontal=True,
        key="post_image_source_mode",
        disabled=is_locked,
    )

    uploaded_images = []
    selected_wp_media_urls = []
    
    if post_image_source_mode == "Upload local":
        uploaded_images = _render_local_image_uploader(is_locked)
    else:
        # Giả định load_wp_media_items_cached được định nghĩa ở lớp utility chung
        from utils.wp_helpers import load_wp_media_items_cached
        try:
            wp_media_items = load_wp_media_items_cached()
            media_map = {item["label"]: item for item in wp_media_items}
            selected_media_labels = st.multiselect("Chọn ảnh từ WP Media", options=list(media_map.keys()), disabled=is_locked)
            selected_wp_media_urls = [str(media_map[label]["url"]) for label in selected_media_labels if label in media_map]
        except Exception as media_error:
            st.warning(f"Không tải được danh sách WP Media: {media_error}")

    images_per_post = st.number_input("Số hình mỗi bài", min_value=0, value=2, step=1, disabled=is_locked)
    alt_strategy_label = st.selectbox("Cách tạo ALT và Tên file Ảnh", options=list(ALT_STRATEGY_MAP.keys()), index=0, disabled=is_locked)
    language_label = st.selectbox("Ngôn ngữ cho tất cả bài được chọn", options=["Tự động phát hiện (Theo từ khóa)", "Tiếng Việt", "Tiếng Trung Giản Thể"], index=0, disabled=is_locked)

    # 4. Trạng thái Lock UI và Nút Thực thi
    _handle_ui_lock_and_execution(
        is_locked, current_state, task_manager, orchestrator, 
        selected_option_list, processable_options, post_image_source_mode, 
        uploaded_images, selected_wp_media_urls, images_per_post, 
        alt_strategy_label, language_label
    )

# --- INTERNAL HELPERS ---

def _render_task_results(current_state: dict, task_manager: TaskStateManager):
    if current_state["success"] > 0:
        st.success(current_state["success_msg"])
    
    success_ids = [int(item) for item in (current_state.get("success_ids") or [])]
    failed_ids = [int(item) for item in (current_state.get("failed_ids") or [])]

    if success_ids:
        st.info(f"ID generate thành công: {', '.join(str(item) for item in sorted(success_ids))}")
    if failed_ids:
        st.warning(f"ID generate thất bại: {', '.join(str(item) for item in sorted(failed_ids))}")

    if current_state["errors"]:
        st.error("Một số bài viết generate thất bại / bị hủy:")
        st.text("\n".join(current_state["errors"][:20]))
    
    if st.button("Xác nhận & Dọn dẹp Message", key="clear_gen_msg"):
        task_manager.update(feature=None, errors=[], success=0, success_ids=[], failed_ids=[])
        st.rerun()

def _detect_keyword_lang_from_option(option_label: str) -> str | None:
    parts = option_label.split(" - ", 1)
    if len(parts) <= 1: return None
    keyword_part = parts[1].rsplit(" [", 1)[0]
    return MediaService.detect_keyword_language(keyword_part)

def _render_keyword_language_detection(selected_option_list: List[str]):
    detected_langs = [_detect_keyword_lang_from_option(opt) for opt in selected_option_list]
    vi_count = sum(1 for lang in detected_langs if lang == "vi")
    zh_count = sum(1 for lang in detected_langs if lang == "zh")
    st.caption(f"Phát hiện từ khóa đã chọn: VI={vi_count} | ZH={zh_count}")

def _render_outline_step(selected_option_list: List[str], processable_options: dict, orchestrator: Any, is_locked: bool):
    st.markdown("---")
    st.markdown("### 📋 Đề xuất dàn ý bài viết")
    
    outline_target = st.selectbox("Chọn bài muốn xem đề xuất dàn ý", options=selected_option_list, key="outline_target_select")
    outline_article_id = processable_options.get(outline_target)
    
    current_outline = ""
    if outline_article_id:
        try:
            _outline_article = ArticleRepository.get_article_by_id(outline_article_id)
            current_outline = (_outline_article.context or "") if _outline_article else ""
        except Exception:
            pass

    col_gen, col_save, col_clear = st.columns([2, 2, 1])
    with col_gen:
        if st.button("🤖 AI đề xuất dàn ý", key="btn_generate_outline", use_container_width=True, disabled=is_locked):
            if outline_article_id:
                with st.spinner("AI đang phân tích từ khóa và soạn dàn ý..."):
                    try:
                        _kw_lang = _detect_keyword_lang_from_option(outline_target)
                        _lang_label = "Tiếng Trung Giản Thể" if _kw_lang == "zh" else "Tiếng Việt"
                        _kw_part = outline_target.split(" - ", 1)[1].rsplit(" [", 1)[0] if " - " in outline_target else outline_target
                        
                        _outline_text = orchestrator.agent.generate_content_outline(
                            keyword=_kw_part,
                            language=LANGUAGE_MAP[_lang_label],
                        )
                        st.session_state[f"outline_{outline_article_id}"] = _outline_text
                        ArticleRepository.update_article_fields(outline_article_id, context=_outline_text)
                        st.success("Đã tạo dàn ý!")
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Lỗi tạo dàn ý: {str(_e)}")

    _display_outline = st.session_state.get(f"outline_{outline_article_id}", current_outline)
    edited_outline = st.text_area("Dàn ý bài viết", value=_display_outline, height=350, key=f"outline_textarea_{outline_article_id}")

    with col_save:
        if st.button("💾 Lưu dàn ý", key=f"save_outline_{outline_article_id}", use_container_width=True, disabled=is_locked):
            ArticleRepository.update_article_fields(outline_article_id, context=edited_outline)
            st.session_state[f"outline_{outline_article_id}"] = edited_outline
            st.success("Dàn ý đã được lưu!")
    with col_clear:
        if st.button("🗑️ Xóa", key=f"clear_outline_{outline_article_id}", use_container_width=True, disabled=is_locked):
            ArticleRepository.update_article_fields(outline_article_id, context="")
            st.session_state.pop(f"outline_{outline_article_id}", None)
            st.rerun()
    st.markdown("---")

def _render_local_image_uploader(is_locked: bool):
    if "post_images_uploader_nonce" not in st.session_state:
        st.session_state["post_images_uploader_nonce"] = 0

    uploader_col, clear_col = st.columns([12, 1])
    with clear_col:
        st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
        if st.button("🗑️", key="clear_post_uploaded_images_btn", disabled=is_locked, use_container_width=True):
            st.session_state["post_images_uploader_nonce"] = int(st.session_state.get("post_images_uploader_nonce", 0)) + 1
            st.rerun()

    with uploader_col:
        uploader_key = f"post_images_uploader_{int(st.session_state.get('post_images_uploader_nonce', 0))}"
        return st.file_uploader("Chọn hình ảnh để chèn vào bài", accept_multiple_files=True, type=['png', 'jpg', 'webp'], disabled=is_locked, key=uploader_key)

def _handle_ui_lock_and_execution(
    is_locked: bool, current_state: dict, task_manager: TaskStateManager, orchestrator: Any,
    selected_option_list: List[str], processable_options: dict, post_image_source_mode: str,
    uploaded_images: List[Any], selected_wp_media_urls: List[str], images_per_post: int,
    alt_strategy_label: str, language_label: str
):
    """Xử lý khóa UI khi Thread đang chạy và hiển thị nút Generate/Stop"""
    
    if is_locked and current_state["feature"] == "generate":
        st.info("⏳ AI đang trong tiến trình Generate. Các tính năng khác đã bị khóa an toàn.")
        progress_val = current_state["completed"] / max(1, current_state["total"])
        st.progress(progress_val)
        st.write(f"Đã xử lý: {current_state['completed']} / {current_state['total']} bài")
        
        if st.button("🛑 Dừng Generate Khẩn Cấp", type="primary"):
            if "global_cancel_event" in st.session_state:
                st.session_state["global_cancel_event"].set()
            task_manager.update(should_stop=True)
            st.warning("Đã gửi tín hiệu dừng khẩn cấp đến các Workers. Vui lòng chờ...")
        
        time.sleep(1.5)
        st.rerun()
    elif is_locked:
        st.info("⏳ Phát hiện bài viết đang ở trạng thái PROCESSING trong Database.")
        if st.button("🔄 Kiểm tra lại trạng thái xử lý"):
            st.rerun()
    else:
        if st.button("Viết bài", type="primary", disabled=is_locked):
            _start_generate_jobs(
                selected_option_list, processable_options, post_image_source_mode, 
                uploaded_images, selected_wp_media_urls, images_per_post, 
                alt_strategy_label, language_label, orchestrator, task_manager
            )

def _start_generate_jobs(
    selected_option_list: List[str], processable_options: dict, post_image_source_mode: str,
    uploaded_images: List[Any], selected_wp_media_urls: List[str], images_per_post: int,
    alt_strategy_label: str, language_label: str, orchestrator: Any, task_manager: TaskStateManager,
    force_single_language: bool = False
):
    """Trích xuất logic chuẩn bị Payload và khởi tạo Background Thread"""
    if not selected_option_list:
        st.warning("Vui lòng chọn ít nhất một bài viết.")
        return

    selected_article_ids = {opt: processable_options[opt] for opt in selected_option_list}
    images_by_source_article = {}
    
    if images_per_post > 0:
        source_images = uploaded_images if post_image_source_mode == "Upload local" else selected_wp_media_urls
        if source_images:
            for index, opt in enumerate(selected_option_list):
                start_idx = index * images_per_post
                images_by_source_article[selected_article_ids[opt]] = source_images[start_idx:start_idx + images_per_post]

    generation_jobs = []
    target_lang_code = "vi" if language_label == "Tiếng Việt" else ("zh" if language_label == "Tiếng Trung Giản Thể" else "auto")
    mismatch_options = [opt for opt in selected_option_list if target_lang_code != "auto" and _detect_keyword_lang_from_option(opt) != target_lang_code]

    # Handle Language Mismatch Dialog (Giữ nguyên logic của hệ thống cũ)
    if mismatch_options and not force_single_language:
        st.session_state.update({
            "generate_lang_confirm_needed": True,
            "generate_lang_confirm_label": language_label,
            "generate_lang_confirm_mismatch_count": len(mismatch_options),
            "generate_lang_confirm_mismatch_preview": mismatch_options[:5]
        })
        st.rerun()
        return

    for opt in selected_option_list:
        source_article_id = selected_article_ids[opt]
        row_lang_label = "Tiếng Trung Giản Thể" if (language_label == "Tự động phát hiện (Theo từ khóa)" and _detect_keyword_lang_from_option(opt) == "zh") else (language_label if language_label != "Tự động phát hiện (Theo từ khóa)" else "Tiếng Việt")
        
        generation_jobs.append({
            "article_id": source_article_id,
            "source_article_id": source_article_id,
            "language_label": row_lang_label,
            "language_prompt": LANGUAGE_MAP[row_lang_label],
            "display_label": opt,
        })

    if not generation_jobs: return

    # Khởi tạo Task
    task_manager.update(is_running=True, should_stop=False, completed=0, total=len(generation_jobs), success=0, errors=[], feature="generate", success_ids=[], failed_ids=[])
    st.session_state["global_cancel_event"] = threading.Event()

    # Worker Thread (Được định nghĩa khép kín trong module)
    def background_generate_worker(jobs: List[dict], cancel_event: threading.Event):
        job_queue = queue.Queue()
        for job in jobs: job_queue.put(job)
        
        def worker_thread():
            while not job_queue.empty() and not cancel_event.is_set():
                try: job = job_queue.get_nowait()
                except queue.Empty: break

                src_id, lang_label = int(job["source_article_id"]), str(job["language_label"])

                def process_ai_output_images(ai_output, article, sid=src_id, l_label=lang_label):
                    from utils.image_injector import apply_images_to_ai_output # Abstract logic tiêm ảnh ra Utils
                    return apply_images_to_ai_output(ai_output, article, images_by_source_article.get(sid, []), min(images_per_post, 10), l_label, False, ALT_STRATEGY_MAP[alt_strategy_label], orchestrator)

                try:
                    is_success, message = orchestrator.generate_single_article(
                        article_id=int(job["article_id"]), language_label=lang_label,
                        language_prompt=str(job["language_prompt"]), ai_output_processor_callback=process_ai_output_images,
                        cancel_event=cancel_event
                    )
                    task_manager.increment(success=is_success)
                    task_manager.append_success_id(int(job["article_id"])) if is_success else task_manager.append_failed_id(int(job["article_id"]))
                    if not is_success: task_manager.append_error(message)
                except Exception as e:
                    task_manager.increment(success=False)
                    task_manager.append_failed_id(int(job["article_id"]))
                    task_manager.append_error(f"{job['display_label']}: {str(e)}")
                finally:
                    job_queue.task_done()

        threads = [threading.Thread(target=worker_thread, daemon=True) for _ in range(min(MAX_GENERATE_WORKERS, len(generation_jobs)))]
        for t in threads: t.start()
        for t in threads: t.join()

        final_state = task_manager.get_snapshot()
        if cancel_event.is_set(): task_manager.append_error("🚫 Luồng đã bị dừng khẩn cấp.")
        task_manager.update(is_running=False, success_msg=f"Hoàn thành Generate {final_state['success']}/{final_state['total']} bài.")

    threading.Thread(target=background_generate_worker, args=(generation_jobs, st.session_state["global_cancel_event"]), daemon=True).start()
    st.rerun()

```

### Tại sao thiết kế này lại ưu việt?

1. **Separation of Concerns (SoC):** `app.py` không còn phải ôm đồm logic UI, xử lý file và Multi-threading nữa. `post_panel.py` bây giờ chỉ thuần túy làm nhiệm vụ nhận input từ người dùng và đẩy job vào queue.
2. **Dependency Injection:** Bằng cách truyền `orchestrator` và `task_manager` qua params của `render_processing_panel`, chúng ta cắt đứt sự phụ thuộc cứng (hard-coupling) giữa UI và Core Logic. Bạn có thể mock Orchestrator để viết Unit Test cho UI.
3. **Thread Safety:** State được cô lập vào class `TaskStateManager` với `threading.Lock()` bảo vệ mọi thao tác đọc/ghi (`increment`, `append_error`). UI Streamlit chỉ việc gọi `get_snapshot()` để render progress an toàn mà không sợ hiện tượng Race Condition.

---

