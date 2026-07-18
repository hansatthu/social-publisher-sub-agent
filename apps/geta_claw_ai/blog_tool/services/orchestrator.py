import traceback
import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, Any, Callable

logger = logging.getLogger(__name__)

from database.models import ArticleStatus
from database.models import Article

AIOutputProcessor = Callable[[dict[str, Any], Article], dict[str, Any]]
from services.article_repository import ArticleRepository, RepositoryError
from services.dtos import WooCommerceProductDTO
from services.media_service import MediaService
from llm_engine.agent import SEOAgent
from integrations.wordpress import WordPressPublisher
from integrations.woocommerce import WooCommercePublisher, WooCommerceIntegrationError
from integrations.google_sheets import GoogleSheetsAppender
from services.seo_scoring_service import SeoScoringService

class ArticleOrchestrator:
    """
    [Architecture] Orchestration Layer / Use Case Layer.
    Điều phối Data Flow giữa Database (Repository), LLM (Agent), và External API (WordPress).
    Tách biệt hoàn toàn Business Logic khỏi UI (Streamlit).
    """
    
    def __init__(
        self,
        agent: SEOAgent,
        wp_publisher: WordPressPublisher,
        wc_publisher: WooCommercePublisher | None = None,
        sheets_appender: GoogleSheetsAppender | None = None,
    ):
        # Dependency Injection (DI)
        self.agent = agent
        self.wp_publisher = wp_publisher
        self.wc_publisher = wc_publisher
        self.sheets_appender = sheets_appender
        self.generate_timeout_seconds = max(1, int(os.getenv("GENERATE_TIMEOUT_SECONDS", "120") or 120))
        
        # Thêm ThreadPool duy nhất để xử lý tuần tự API Google Sheets, tránh 429 Rate Limit
        self._sheets_sync_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SheetsSyncWorker")

    def publish_woocommerce_product(self, row_data: dict[str, Any], status_val: str = "draft") -> Tuple[bool, str, str]:
        """
        Orchestrate single WooCommerce product publish.
        Trả về: (is_success, message, product_url)
        """
        is_geta_catalog = "innhanhgeta.com" in (self.wp_publisher.site_url or "")
        if is_geta_catalog:
            return self.publish_geta_catalog_product(row_data, status_val)

        if not self.wc_publisher:
            return False, "WooCommerce chưa được cấu hình trong hệ thống.", ""

        try:
            product_dto = WooCommerceProductDTO.from_dict(row_data)
            if not product_dto.name:
                return False, "Thiếu name.", ""

            wc_response = self.wc_publisher.create_product(product_dto, status=status_val)
            product_id = wc_response.get("product_id")
            if not product_id:
                return False, "WooCommerce không trả về product_id sau khi tạo sản phẩm.", ""
            if wc_response.get("updated_existing"):
                return True, f"Đã cập nhật dữ liệu ZH cho sản phẩm có sẵn: {product_dto.name}", str(wc_response.get("product_url") or "")

            return True, f"Tạo sản phẩm thành công: {product_dto.name}", str(wc_response.get("product_url") or "")

        except ValueError:
            return False, "stock_quantity không hợp lệ (phải là số).", ""
        except WooCommerceIntegrationError as e:
            return False, str(e), ""
        except Exception as e:
            return False, f"Lỗi không xác định: {str(e)}", ""

    def publish_geta_catalog_product(self, row_data: dict[str, Any], status_val: str = "draft") -> Tuple[bool, str, str]:
        import requests
        
        try:
            name = str(row_data.get("name") or "").strip()
            if not name:
                return False, "Thiếu name.", ""
                
            sku = str(row_data.get("sku") or "").strip()
            regular_price = str(row_data.get("regular_price") or "").strip() or "Liên hệ"
            description = str(row_data.get("description") or "").strip()
            short_description = str(row_data.get("short_description") or "").strip()
            
            # Subtitle, badge, faqs, highlights
            subtitle = str(row_data.get("subtitle") or "").strip()
            badge = str(row_data.get("badge") or "").strip()
            faqs_raw = row_data.get("faqs")
            highlights_raw = row_data.get("highlights")
            
            highlights = []
            if highlights_raw:
                if isinstance(highlights_raw, list):
                    highlights = highlights_raw
                else:
                    lines = [line.strip() for line in str(highlights_raw).split("\n") if line.strip()]
                    for line in lines:
                        parts = line.split("|")
                        if len(parts) >= 3:
                            highlights.append({
                                "icon": parts[0].strip(),
                                "title": parts[1].strip(),
                                "text": parts[2].strip()
                            })
                            
            faqs = []
            if faqs_raw:
                if isinstance(faqs_raw, list):
                    faqs = faqs_raw
                else:
                    lines = [line.strip() for line in str(faqs_raw).split("\n") if line.strip()]
                    for line in lines:
                        parts = line.split("|")
                        if len(parts) >= 3:
                            faqs.append({
                                "active": parts[0].strip() == "1",
                                "question": parts[1].strip(),
                                "answer": parts[2].strip()
                            })
                            
            description_intro = str(row_data.get("description_intro") or short_description or "").strip()
            description_outro = str(row_data.get("description_outro") or "").strip()
            
            catalog_data = {
                "subtitle": subtitle,
                "badge": badge,
                "description_intro": description_intro,
                "description_outro": description_outro,
                "faqs": faqs,
                "highlights": highlights
            }
            
            categories_str = str(row_data.get("categories") or "").strip()
            category_names = [item.strip() for item in categories_str.split(",") if item.strip()] if categories_str else []
            
            wp_publisher = self.wp_publisher
            auth = wp_publisher.auth
            base_url = wp_publisher.site_url
            
            cat_ids = []
            if category_names:
                cat_endpoint = f"{base_url}/wp-json/wp/v2/geta_product_cat"
                for cat_name in category_names:
                    try:
                        r = requests.get(cat_endpoint, params={"search": cat_name, "per_page": 100}, auth=auth, timeout=20)
                        r.raise_for_status()
                        terms = r.json() or []
                        matched_id = None
                        for term in terms:
                            if term.get("name", "").strip().lower() == cat_name.lower():
                                matched_id = term.get("id")
                                break
                        if matched_id:
                            cat_ids.append(matched_id)
                        else:
                            r_create = requests.post(cat_endpoint, json={"name": cat_name}, auth=auth, timeout=20)
                            r_create.raise_for_status()
                            new_term = r_create.json()
                            if new_term.get("id"):
                                cat_ids.append(new_term["id"])
                    except Exception as e:
                        logger.error(f"Lỗi phân tích danh mục geta_product_cat '{cat_name}': {e}")
            
            images_str = str(row_data.get("images") or "").strip()
            image_refs = [item.strip() for item in images_str.split(",") if item.strip()] if images_str else []
            
            featured_media_id = None
            gallery_ids = []
            for ref in image_refs:
                if ref.isdigit():
                    img_id = int(ref)
                    if not featured_media_id:
                        featured_media_id = img_id
                    gallery_ids.append(img_id)
            
            existing_post = None
            if sku:
                product_endpoint = f"{base_url}/wp-json/wp/v2/geta_product"
                try:
                    r = requests.get(product_endpoint, params={"search": sku, "status": "any", "per_page": 10}, auth=auth, timeout=20)
                    r.raise_for_status()
                    posts = r.json() or []
                    for post in posts:
                        meta = post.get("meta", {})
                        post_sku = str(meta.get("_sku") or "").strip()
                        if post_sku.lower() == sku.lower():
                            existing_post = post
                            break
                except Exception as e:
                    logger.error(f"Lỗi kiểm tra SKU tồn tại: {e}")
            
            payload = {
                "title": name,
                "content": description,
                "status": status_val,
                "meta": {
                    "_geta_catalog_price": regular_price,
                    "_sku": sku,
                    "_geta_catalog_data": catalog_data,
                    "_geta_product_gallery": gallery_ids
                }
            }
            if cat_ids:
                payload["geta_product_cat"] = cat_ids
            if featured_media_id:
                payload["featured_media"] = featured_media_id
                
            if existing_post:
                post_id = existing_post["id"]
                url = f"{base_url}/wp-json/wp/v2/geta_product/{post_id}"
                r_post = requests.post(url, json=payload, auth=auth, timeout=30)
                r_post.raise_for_status()
                res_data = r_post.json()
                return True, f"Đã cập nhật sản phẩm Geta có sẵn: {name}", res_data.get("link") or ""
            else:
                url = f"{base_url}/wp-json/wp/v2/geta_product"
                r_post = requests.post(url, json=payload, auth=auth, timeout=30)
                r_post.raise_for_status()
                res_data = r_post.json()
                return True, f"Tạo sản phẩm Geta thành công: {name}", res_data.get("link") or ""
                
        except Exception as e:
            return False, f"Lỗi không xác định: {str(e)}", ""

    def _sync_to_sheets_async(self, article_id: int) -> None:
        if not self.sheets_appender:
            return

        def _worker() -> None:
            try:
                article = ArticleRepository.get_article_by_id(article_id)
                if article:
                    self.sheets_appender.upsert_article_row(article)
            except Exception as e:
                logger.error(f"Lỗi đồng bộ Sheets cho ID {article_id}: {e}")

        # Đẩy vào hàng đợi tuần tự thay vì spawn Thread mới
        self._sheets_sync_executor.submit(_worker)

    @staticmethod
    def _build_wp_article_data(article: Article, content_markdown_processed: str) -> dict[str, Any]:
        return {
            "keyword": article.keyword,
            "seo_metadata": {
                "title": article.title,
                "meta_description": article.meta_description,
                "slug": article.slug,
            },
            "content_markdown": content_markdown_processed,
        }

    def _mark_upload_failed_and_sync(self, article_id: int, error_message: str, error_prefix: str) -> Tuple[bool, str, str]:
        ArticleRepository.update_processing_state(article_id, ArticleStatus.UPLOAD_FAILED, str(error_message))
        self._sync_to_sheets_async(article_id)
        return False, f"ID {article_id}: {error_prefix} - {str(error_message)}", ""

    @staticmethod
    def _load_article_or_message(article_id: int) -> tuple[Article | None, str]:
        article = ArticleRepository.get_article_by_id(article_id)
        if not article:
            return None, f"ID {article_id}: Không tìm thấy bài viết."
        return article, ""

    def _run_ai_generation(self, article: Article, language_prompt: str, site_name: str | None) -> tuple[dict[str, Any], float]:
        start_time = time.time()
        
        # Lấy danh sách link bài viết cũ (Dynamic Internal Links) của website đích
        target = site_name or article.target_site
        published_links = ArticleRepository.get_recent_published_links(site_name=target, limit=15)
        context_text = str(article.context or "").strip()
        
        if published_links:
            links_str = "\n".join([f"- {item['title']}: {item['url']}" for item in published_links])
            context_text += f"\n\n[DYNAMIC INTERNAL LINKS]\nCó thể chọn ra 3-5 link từ danh sách sau để chèn vào bài:\n{links_str}"
        
        ai_output = self.agent.generate_article(
            keyword=article.keyword,
            context=context_text,
            language=language_prompt,
            site_name=site_name,
        )
        elapsed = time.time() - start_time
        return ai_output, elapsed

    def _run_seo_scoring(self, article_id: int) -> None:
        try:
            scored_article = ArticleRepository.get_article_by_id(article_id)
            if scored_article:
                scoring_result = SeoScoringService.evaluate_article(scored_article)
                ArticleRepository.save_seo_scoring(article_id, scoring_result.get("score", 0), scoring_result.get("notes", []))
        except Exception as scoring_error:
            logger.error(f"[JOB-{article_id}] Lỗi Scoring: {scoring_error}")

    def _mark_generate_failed_and_sync(self, article_id: int, error_msg: str) -> tuple[bool, str]:
        try:
            ArticleRepository.update_processing_state(article_id, ArticleStatus.GENERATE_FAILED, error_msg)
        except RepositoryError as db_err:
            logger.error(f"[JOB-{article_id}] Fatal: Không thể rollback trạng thái vào DB: {db_err}")
        self._sync_to_sheets_async(article_id)
        return False, f"ID {article_id}: Lỗi hệ thống - {error_msg}"

    def generate_single_article(
        self,
        article_id: int,
        language_label: str,
        language_prompt: str,
        site_name: str | None = None,
        ai_output_processor_callback: AIOutputProcessor | None = None,
        cancel_event: threading.Event = None # Truyền tín hiệu dừng từ Worker
    ) -> Tuple[bool, str]:
        
        logger.info(f"[JOB-{article_id}] Bắt đầu tiến trình Generate.")
        
        # 1. Cooperative Stop Check
        if cancel_event and cancel_event.is_set():
            logger.warning(f"[JOB-{article_id}] Bị hủy trước khi thực thi.")
            return False, f"ID {article_id}: Bị hủy bởi tín hiệu hệ thống."

        try:
            article, not_found_message = self._load_article_or_message(article_id)
            if not article:
                return False, not_found_message

            ArticleRepository.update_processing_state(article_id, ArticleStatus.PROCESSING)

            # 2. Gọi Agent đồng bộ (Agent đã xử lý httpx timeout ngầm)
            ai_output, elapsed = self._run_ai_generation(article, language_prompt, site_name)
            logger.info(f"[JOB-{article_id}] Hoàn tất AI Inference mất {elapsed:.2f}s.")

            # Cooperative Stop Check Post-Inference
            if cancel_event and cancel_event.is_set():
                ArticleRepository.update_processing_state(article_id, ArticleStatus.GENERATE_FAILED, "Hủy sau khi gen xong (chưa lưu).")
                return False, f"ID {article_id}: Đã hủy tiến trình trước khi lưu DB."

            # 3. Guard Limits: Xử lý hình ảnh an toàn
            if ai_output_processor_callback:
                logger.info(f"[JOB-{article_id}] Kích hoạt xử lý Media injection.")
                # Note: Nếu ai_output_processor_callback có vòng lặp, nên check cancel_event bên trong nó.
                ai_output = ai_output_processor_callback(ai_output, article)

            # 4. Lưu Data Lineage
            ArticleRepository.save_ai_generated_content(article_id, ai_output, language=language_label)

            # 5. SEO Scoring (Tách try-except riêng biệt tránh fail toàn bộ pipeline)
            self._run_seo_scoring(article_id)

            self._sync_to_sheets_async(article_id)
            logger.info(f"[JOB-{article_id}] Hoàn tất toàn bộ pipeline.")
            return True, ""

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[JOB-{article_id}] Failed: {error_msg}\n{traceback.format_exc()}")
            return self._mark_generate_failed_and_sync(article_id, error_msg)

    def publish_single_article(
        self,
        article_id: int,
        status_val: str,
        category_id: int | None,
        category_name: str | None,
        thumbnail_bytes: bytes | None,
        thumbnail_name: str | None,
        thumbnail_details: dict | None,
        content_markdown_processed: str
    ) -> Tuple[bool, str, str]:
        """
        Thực thi luồng đẩy dữ liệu lên WordPress.
        Trả về: (is_success, error_message, published_url)
        """
        try:
            article = ArticleRepository.get_article_by_id(article_id)
            if not article:
                return False, f"ID {article_id}: Không tìm thấy bài viết.", ""

            # 1. Upload Thumbnail (Nếu có)
            thumbnail_id = None
            if thumbnail_bytes and thumbnail_name:
                prepared_bytes = MediaService.embed_metadata_into_image_bytes(
                    thumbnail_bytes, thumbnail_name, thumbnail_details
                )
                try:
                    thumbnail_id = self.wp_publisher.upload_media(
                        prepared_bytes, thumbnail_name, details=thumbnail_details
                    )
                except TypeError as e:
                    if "unexpected keyword argument 'details'" not in str(e):
                        raise
                    thumbnail_id = self.wp_publisher.upload_media(prepared_bytes, thumbnail_name)

            # 2. Chuẩn bị Payload
            article_data = self._build_wp_article_data(article, content_markdown_processed)

            # 3. Gọi REST API WordPress
            wp_response = self.wp_publisher.publish_article(
                article_data,
                status=status_val,
                category_id=category_id,
                category_name=category_name,
                thumbnail_id=thumbnail_id,
                language_label=article.language,
            )

            # 4. Lưu trạng thái hoàn thành
            ArticleRepository.save_publish_info(
                article_id,
                wp_response['wp_post_id'],
                wp_response['wp_post_url'],
                category_id=category_id,
                category_name=category_name,
            )
            self._sync_to_sheets_async(article_id)
            return True, "", wp_response.get('wp_post_url', '')

        except RepositoryError as e:
            return self._mark_upload_failed_and_sync(article_id, str(e), "Lỗi DB")
        except Exception as e:
            return self._mark_upload_failed_and_sync(article_id, str(e), "Lỗi API WP")