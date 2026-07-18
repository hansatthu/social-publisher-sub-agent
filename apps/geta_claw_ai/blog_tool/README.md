# Blog Tool (SEO Automation)

## Chạy bằng uv

### 1) Cài dependency
```bash
uv sync
```

### 2) Chạy app
```bash
uv run streamlit run ui/app.py
```

App sẽ mở tại:
- `http://localhost:8501`

## Cấu hình nhiều site WordPress

Tool đọc danh sách site từ `sites.json`. Mỗi site nên có:
- `name`: tên hiển thị trong UI
- `wp_site_url`: URL gốc WordPress
- `env_prefix`: hậu tố để map biến môi trường theo site

Ví dụ biến môi trường theo `env_prefix=innhanhgeta.com`:

```dotenv
WP_USERNAME_innhanhgeta.com="your-wp-username"
WP_APP_PASSWORD_innhanhgeta.com="xxxx xxxx xxxx xxxx xxxx xxxx"
```

Khi chọn site trong UI, app sẽ tự lấy đúng credential theo tiền tố này để đăng bài.

## Lệnh nhanh (1 dòng)
```bash
uv sync; uv run streamlit run ui/app.py
```

## Multi API Key Rotation (Gemini)

Tool hỗ trợ tự động xoay API key khi key hiện tại bị hết quota/rate limit.

### Cấu hình `.env` (khuyến nghị cho 10 key)
```dotenv
GOOGLE_API_KEY_1="AIza..."
GOOGLE_API_KEY_2="AIza..."
GOOGLE_API_KEY_3="AIza..."
GOOGLE_API_KEY_4="AIza..."
GOOGLE_API_KEY_5="AIza..."
GOOGLE_API_KEY_6="AIza..."
GOOGLE_API_KEY_7="AIza..."
GOOGLE_API_KEY_8="AIza..."
GOOGLE_API_KEY_9="AIza..."
GOOGLE_API_KEY_10="AIza..."
```

Ngoài ra cũng hỗ trợ:
- `GOOGLE_API_KEY="..."` (1 key)
- `GOOGLE_API_KEYS="key1,key2,key3,..."` (nhiều key trong 1 biến)

Khi gặp lỗi quota (`resource_exhausted`, `quota exceeded`, `429`, `rate limit`), hệ thống sẽ tự chuyển sang key kế tiếp.

## Product Automation (WooCommerce)

### Cấu hình `.env`
```dotenv
WP_SITE_URL="https://your-site.com"
WC_CONSUMER_KEY="ck_xxx"
WC_CONSUMER_SECRET="cs_xxx"
WC_API_VERSION="wc/v3"
```

### Chuẩn file CSV
- Bắt buộc: `name`
- Tùy chọn: `description`, `short_description`, `name_zh`, `short_desc_zh`, `desc_zh`, `sku`, `regular_price`, `stock_quantity`, `categories`, `category_zh`, `local_images`, `wp_media`
- `product_id`: hệ thống tự sinh nội bộ khi upload, user không cần nhập
- `regular_price`: có thể để trống (phù hợp B2B/cần ẩn giá)
- `categories`: chọn từ dữ liệu category WooCommerce đã có trên WordPress (dropdown trong UI)
- `name_zh`: tên sản phẩm tiếng Trung ghi vào `_product_title_zh`
- `short_desc_zh`: mô tả ngắn tiếng Trung ghi vào `_product_short_desc_zh`
- `desc_zh`: mô tả chi tiết tiếng Trung ghi vào `_product_content_zh`
- `category_zh`: tên danh mục tiếng Trung sẽ ghi vào term meta `_term_name_zh`
- `local_images`: dùng khi chọn mode `Local images`, nhập tên file local đã chọn ở uploader
- `wp_media`: dùng khi chọn mode `WP Media`, nhập URL ảnh WP hoặc media ID (số) hoặc tên file ảnh trong Media Library
- Với CSV thô: nếu một ô có nhiều giá trị chứa dấu phẩy, bọc bằng dấu nháy kép. Ví dụ: `"a.jpg,b.jpg"`
- Với bảng chỉnh sửa trong UI: nhập `a.jpg,b.jpg` hoặc `a.jpg;b.jpg` (không cần nháy kép)

### CSV mẫu
File mẫu trong repo: `data/woocommerce_products_sample.csv`

```csv
name,description,short_description,name_zh,short_desc_zh,desc_zh,sku,regular_price,stock_quantity,categories,category_zh,local_images,wp_media
Bật lửa họa tiết Vân đá & Cẩm thạch,Dòng bật lửa họa tiết vân đá và cẩm thạch tinh tế.,Bật lửa họa tiết vân đá sang trọng.,,,,LGT-STONE-02-VI,199000,30,disposable-lighters,,bat-lua-stone-01.jpg,
Bật lửa họa tiết Vân đá & Cẩm thạch,,,石纹与大理石纹艺术打火机,大理石纹高颜值打火机，质感出众。,精选高质感石纹与大理石图案，外观大气端庄。,LGT-STONE-02,,,disposable-lighters,一次性打火机,,"2456,stone-02-zh.jpg"
Bật lửa phổ thông (Loại tốt),Dòng bật lửa nhựa phổ thông bền bỉ.,Bật lửa phổ thông giá tốt.,,,,LGT-STD-05-VI,159000,50,disposable-lighters,,"bat-lua-std-01.jpg,bat-lua-std-02.jpg",
```

### Nguồn ảnh sản phẩm
1. Chọn mode `Local images` hoặc `WP Media` trong Product Automation.
2. `Local images`:
	- Chọn ảnh ở ô uploader trong UI.
	- Dùng cột `local_images` để nhập tên file.
	- Tool tự upload lên WordPress Media rồi gắn URL vào `images` trước khi đẩy WooCommerce.
3. `WP Media`:
	- Không cần upload file local.
	- Dùng cột `wp_media` với URL ảnh, media ID, hoặc tên file ảnh đã có trong Media Library.
	- Tool resolve token -> URL rồi đẩy WooCommerce.

### Logic nhập dữ liệu tiếng Trung (ZH)
- Bật tùy chọn `Dữ liệu tiếng Trung: cập nhật vào sản phẩm có sẵn theo SKU` trong Product Automation.
- Khi một dòng chứa nội dung tiếng Trung, tool sẽ tìm sản phẩm hiện có theo SKU (cả dạng base, `-VI`, `-ZH`) rồi cập nhật các meta ZH thay vì tạo product mới.
- Các meta key sản phẩm ZH được ghi cố định theo logic theme:
	- `_product_title_zh`
	- `_product_short_desc_zh`
	- `_product_content_zh`

- Nếu có dữ liệu `category_zh`, tool sẽ cập nhật term meta:
	- `_term_name_zh`

### Nhập data trực tiếp trên bảng
1. Chọn `Nhập trực tiếp trên bảng` tại mục nguồn dữ liệu.
2. Nhập cột bắt buộc: `name`.
3. Có thể thêm các cột tùy chọn: `description`, `short_description`, `name_zh`, `short_desc_zh`, `desc_zh`, `sku`, `regular_price`, `stock_quantity`, `categories`, `category_zh`, `local_images`, `wp_media`.
4. Dòng nào thiếu `name` sẽ bị loại ở bước Validate.
5. Chọn đúng mode ảnh:
	- `Local images` -> dùng `local_images` + uploader file.
	- `WP Media` -> dùng `wp_media` (URL hoặc media ID).
6. Nếu muốn ẩn giá theo mô hình B2B, để trống `regular_price`.
7. `product_id` được hệ thống tự sinh nội bộ trong lúc upload.
8. Có tùy chọn tự thêm hậu tố ngôn ngữ vào SKU (`-VI` / `-ZH`) trước khi upload.

Ví dụ nhập nhanh trên bảng:
```text
name=Ao khoac gio | regular_price= | sku=AK-009 | categories=Thoi trang Nam | local_images=ao-khoac-1.jpg;ao-khoac-2.jpg
```

### Luồng chạy
1. Chọn nguồn dữ liệu: upload CSV hoặc nhập trực tiếp trên bảng.
2. (Tuỳ chọn) bật tự động thêm hậu tố ngôn ngữ vào SKU.
3. Bấm upload để chạy bước pre-validate: dữ liệu bắt buộc, SKU trùng trong file, SKU đã tồn tại trên WooCommerce.
4. Chỉ khi pre-validate pass, tool mới upload ảnh local và tạo sản phẩm.
5. Chọn trạng thái `draft` hoặc `publish`.
6. Bấm `🚀 Đẩy lên WooCommerce` để chạy nền đa luồng (3-5 workers), có progress realtime.
7. Có thể bấm `🛑 Dừng khẩn cấp upload sản phẩm` để dừng an toàn.
8. Sau khi xong, tool hiển thị:
	- Danh sách thành công kèm link sản phẩm.
	- Danh sách dòng lỗi kèm lý do.

## Crawl trumsiaz.com

Script crawl sản phẩm từ trumsiaz và xuất CSV/JSON sẵn cho import WooCommerce:

```bash
uv run python tmp/crawl_trumsiaz_products.py --output-dir tmp/sample_outputs
```

Một category test nhanh:

```bash
uv run python tmp/crawl_trumsiaz_products.py --category-url https://trumsiaz.com/san-pham/phu-kien-dien-thoai.html --max-pages-per-category 2 --max-products-per-category 1
```

Nếu muốn đẩy thẳng vào site đã cấu hình trong `sites.json`:

```bash
uv run python tmp/crawl_trumsiaz_products.py --site mocbaibavet.com --publish --status draft
```

CSV xuất ra dùng các cột chuẩn của Product Automation, trong đó `wp_media` có thể chứa URL ảnh source hoặc media ID tuỳ chế độ chạy.
