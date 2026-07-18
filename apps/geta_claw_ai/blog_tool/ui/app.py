import sys
import os
import re
import io
import html
import hashlib
import time
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from unidecode import unidecode
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import requests

from database.session import init_db
from llm_engine.agent import SEOAgent
from integrations.wordpress import WordPressPublisher
from integrations.woocommerce import WooCommercePublisher, WooCommerceIntegrationError
from ui.state import get_site_config_by_name, get_default_site_config
from integrations.google_sheets import GoogleSheetsAppender, GoogleSheetsIntegrationError
from services.article_repository import ArticleRepository, RepositoryError
from services.orchestrator import ArticleOrchestrator
from services.media_service import MediaService
from services.content_service import ContentService
from ui.state import (
    get_task_manager,
    get_global_task_state,
    reset_generate_result_state,
    reset_wc_result_state,
)
from ui.components.post_constants import ALT_STRATEGY_MAP, LANGUAGE_PROMPT_MAP
from ui.components.articles_grid import render_articles_grid_component
from ui.components.processing_panel import render_processing_panel_component
from ui.components.product_panel import render_product_automation_panel_component
from ui.components.publishing_panel import render_publishing_panel_component
from ui.components.sheets_toolbar import render_sheets_sync_toolbar_component
from ui.components.sidebar import render_sidebar_component
from ui.components.site_selector import render_site_selector

GLOBAL_TASK_STATE = get_global_task_state()

task_manager = get_task_manager("2026-03-18-task-state-v3")

# Khởi tạo Schema Database
@st.cache_resource
def startup_init():
    init_db()
    recovered = ArticleRepository.recover_stale_processing_articles()
    if recovered > 0:
        print(f"[*] Startup Recovery: Reset {recovered} stale articles.")
    return True

startup_init()

MAX_GENERATE_WORKERS = max(1, int(os.getenv("MAX_GENERATE_WORKERS", "4") or 4))
MAX_WC_WORKERS = min(5, max(3, int(os.getenv("MAX_WC_WORKERS", "4") or 4)))
MAX_WC_MEDIA_WORKERS = max(1, min(4, int(os.getenv("MAX_WC_MEDIA_WORKERS", "2") or 2)))
MAX_WC_MEDIA_RETRIES = max(1, min(5, int(os.getenv("MAX_WC_MEDIA_RETRIES", "3") or 3)))
MAX_WC_MEDIA_RETRY_DELAY_SECONDS = max(0.5, float(os.getenv("MAX_WC_MEDIA_RETRY_DELAY_SECONDS", "1.5") or 1.5))
WP_PUBLISHER_CACHE_VERSION = "2026-03-06-wp-media-token-fallback"
WC_PUBLISHER_CACHE_VERSION = "2026-03-14-wc-image-id-normalize-v3-zh-create-fix"
TARGET_LOCALES_BY_LANGUAGE = {
    "vi": ["Mộc Bài - Bavet", "Xa Mát"],
    "zh": ["木牌 - 巴域", "下马"],
}

# Cấu hình Page
st.set_page_config(page_title="SEO Automation Tool", layout="wide")

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem;
    }
    .stButton>button {
        transition: all 0.3s ease-in-out;
        border: 1px solid rgba(59, 130, 246, 0.4);
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(59, 130, 246, 0.5);
        border-color: #60A5FA;
    }
    [data-testid="stSidebarUserContent"] div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(145deg, rgba(30, 58, 138, 0.6) 0%, rgba(23, 37, 84, 0.8) 100%) !important;
        border: 1px solid #3B82F6 !important;
        border-radius: 0.5rem !important;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3) !important;
    }
    [data-testid="stSidebarUserContent"] div[data-testid="stVerticalBlockBorderWrapper"] p, 
    [data-testid="stSidebarUserContent"] div[data-testid="stVerticalBlockBorderWrapper"] label, 
    [data-testid="stSidebarUserContent"] div[data-testid="stVerticalBlockBorderWrapper"] h3 {
        color: #F8FAFC !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ================= CACHING RESOURCES =================
@st.cache_resource
def get_ai_agent():
    return SEOAgent()


# Lấy config site động từ session_state
@st.cache_resource
def get_wp_publisher(site_name: str | None = None, cache_version: str = WP_PUBLISHER_CACHE_VERSION):
    _ = cache_version
    site_name = site_name or st.session_state.get("active_site")
    site_cfg = get_site_config_by_name(site_name) if site_name else get_default_site_config()
    if site_cfg:
        return WordPressPublisher(
            site_url=site_cfg.get("wp_site_url"),
            username=site_cfg.get("wp_username"),
            app_password=site_cfg.get("wp_app_password")
        )
    return WordPressPublisher()


@st.cache_resource
def get_wc_publisher(site_name: str | None = None, cache_version: str = WC_PUBLISHER_CACHE_VERSION):
    _ = cache_version
    site_name = site_name or st.session_state.get("active_site")
    site_cfg = get_site_config_by_name(site_name) if site_name else get_default_site_config()
    if site_cfg:
        return WooCommercePublisher(
            base_url=site_cfg.get("wp_site_url"),
            consumer_key=site_cfg.get("wc_consumer_key"),
            consumer_secret=site_cfg.get("wc_consumer_secret")
        )
    return WooCommercePublisher()

@st.cache_resource
def get_sheets_appender():
    return GoogleSheetsAppender()

@st.cache_data(ttl=300)
def load_wp_categories_cached(site_name: str | None = None) -> list[dict]:
    publisher = get_wp_publisher(site_name=site_name)
    return publisher.list_categories()

@st.cache_data(ttl=300)
def load_wc_product_categories_cached(site_name: str | None = None) -> list[dict]:
    site_name = site_name or st.session_state.get("active_site")
    if site_name and "innhanhgeta.com" in site_name:
        wp_publisher = get_wp_publisher(site_name=site_name)
        return wp_publisher.list_taxonomy_terms("geta_product_cat")
    publisher = get_wc_publisher(site_name=site_name)
    return publisher.list_product_categories()

@st.cache_data(ttl=180)
def load_wp_media_items_cached(site_name: str | None = None, per_page: int = 100, max_pages: int = 3, search_term: str | None = None) -> list[dict]:
    publisher = get_wp_publisher(site_name=site_name)
    media_endpoint = str(getattr(publisher, "media_endpoint", "") or "").strip()
    auth = getattr(publisher, "auth", None)
    if not media_endpoint or not auth:
        return []

    items: list[dict] = []
    for page in range(1, max(1, int(max_pages)) + 1):
        params={
            "per_page": max(1, int(per_page)),
            "page": page,
            "orderby": "date",
            "order": "desc",
            "_fields": "id,source_url,title",
        }
        if search_term:
            params["search"] = search_term

        response = requests.get(
            media_endpoint,
            params=params,
            auth=auth,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json() or []
        if not isinstance(payload, list) or not payload:
            break

        for media_item in payload:
            media_id = media_item.get("id")
            source_url = str(media_item.get("source_url") or "").strip()
            title_obj = media_item.get("title") or {}
            title_rendered = str(title_obj.get("rendered") if isinstance(title_obj, dict) else "").strip()
            file_name = os.path.basename(source_url) if source_url else ""
            display_name = title_rendered or file_name or f"media-{media_id}"
            if source_url:
                items.append(
                    {
                        "id": media_id,
                        "label": f"ID:{media_id} | {display_name}",
                        "url": source_url,
                    }
                )

        if len(payload) < max(1, int(per_page)):
            break

    return items

# ================= UI CONTROLLER CLASS =================
class SEOAutomationUI:
    def __init__(self):
        try:
            site_name = st.session_state.get("active_site")
            self.agent = get_ai_agent()
            self.publisher = get_wp_publisher(site_name=site_name)
            try:
                self.wc_publisher = get_wc_publisher(site_name=site_name)
            except WooCommerceIntegrationError:
                self.wc_publisher = None
            try:
                self.sheets = get_sheets_appender()
            except GoogleSheetsIntegrationError:
                self.sheets = None
            self.orchestrator = ArticleOrchestrator(self.agent, self.publisher, self.wc_publisher, self.sheets)
        except Exception as e:
            st.error(f"Lỗi khởi tạo Core Services (Kiểm tra .env): {str(e)}")
            st.stop()

    @staticmethod
    def _clear_previous_result_messages() -> None:
        # Clear generate results/messages
        reset_generate_result_state(task_manager)

        # Clear publishing summary messages
        for key in ["bulk_publish_success", "bulk_publish_errors", "bulk_publish_links"]:
            if key in st.session_state:
                del st.session_state[key]

        # Clear Woo summary messages
        reset_wc_result_state(GLOBAL_TASK_STATE)

    def fetch_datagrid_view(self) -> pd.DataFrame:
        try:
            data = ArticleRepository.get_datagrid_overview()
            df = pd.DataFrame(data)
            if "seo_score" in df.columns:
                df["seo_score"] = pd.to_numeric(df["seo_score"], errors="coerce")
            return df
        except RepositoryError as e:
            st.error(str(e))
            return pd.DataFrame([])

    @staticmethod
    def _build_table_fingerprint(df_articles: pd.DataFrame) -> str:
        if df_articles is None or df_articles.empty:
            return "empty"
        normalized = df_articles.sort_values(by=["id"], ascending=True).fillna("")
        payload = normalized.to_json(orient="split", force_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _find_existing_skus_safe(self, sku_values: list[str]) -> dict[str, dict[str, Any]]:
        active_site = st.session_state.get("active_site")
        if active_site and "innhanhgeta.com" in active_site:
            existing_map: dict[str, dict[str, Any]] = {}
            auth = self.publisher.auth
            base_url = self.publisher.site_url
            for sku in sku_values:
                sku = sku.strip()
                if not sku:
                    continue
                try:
                    r = requests.get(
                        f"{base_url}/wp-json/wp/v2/geta_product",
                        params={"search": sku, "status": "any", "per_page": 10},
                        auth=auth,
                        timeout=20,
                    )
                    r.raise_for_status()
                    posts = r.json() or []
                    for post in posts:
                        meta = post.get("meta", {})
                        post_sku = str(meta.get("_sku") or "").strip()
                        if post_sku.lower() == sku.lower():
                            existing_map[sku] = {
                                "id": post["id"],
                                "name": post.get("title", {}).get("rendered", ""),
                                "permalink": post.get("link", ""),
                                "status": post.get("status", ""),
                            }
                            break
                except Exception:
                    pass
            return existing_map

        if not self.wc_publisher:
            return {}

        normalized_skus: list[str] = []
        seen: set[str] = set()
        for sku in sku_values:
            normalized = str(sku or "").strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized_skus.append(normalized)

        if not normalized_skus:
            return {}

        find_existing_method = getattr(self.wc_publisher, "find_existing_skus", None)
        if callable(find_existing_method):
            return find_existing_method(normalized_skus)

        get_by_sku_method = getattr(self.wc_publisher, "get_product_by_sku", None)
        if callable(get_by_sku_method):
            existing_map = {}
            for sku in normalized_skus:
                product = get_by_sku_method(sku)
                if product:
                    existing_map[sku] = product
            return existing_map

        request_method = getattr(self.wc_publisher, "_request", None)
        products_endpoint = str(getattr(self.wc_publisher, "products_endpoint", "") or "").strip()
        if callable(request_method) and products_endpoint:
            existing_map = {}
            for sku in normalized_skus:
                response = request_method(
                    "GET",
                    products_endpoint,
                    params={"sku": sku, "per_page": 100},
                )
                products = response.json() or []
                matched_product = next(
                    (
                        product
                        for product in products
                        if str(product.get("sku", "") or "").strip().lower() == sku.lower()
                    ),
                    None,
                )
                if matched_product:
                    existing_map[sku] = matched_product
            return existing_map

        raise WooCommerceIntegrationError(
            "Publisher WooCommerce hiện tại thiếu khả năng validate SKU. "
            "Vui lòng restart Streamlit để làm mới cache resource."
        )

    def _sync_full_table_to_sheets(self) -> int:
        if not self.sheets:
            raise GoogleSheetsIntegrationError("Google Sheets chưa được cấu hình trong .env")
        articles = ArticleRepository.get_all_articles_for_sync()
        return self.sheets.sync_all_articles(articles)

    def render_sheets_sync_toolbar(self, df_articles: pd.DataFrame, is_locked: bool) -> None:
        render_sheets_sync_toolbar_component(
            df_articles=df_articles,
            is_locked=is_locked,
            sheets=self.sheets,
            build_table_fingerprint_callback=self._build_table_fingerprint,
            sync_full_table_to_sheets_callback=self._sync_full_table_to_sheets,
        )

    def _delete_articles_rows(self, selected_delete_ids: list[Any]) -> int:
        deleted_count = ArticleRepository.delete_articles_by_ids(selected_delete_ids)
        if self.sheets:
            self.sheets.delete_rows_by_ids(selected_delete_ids)
        return deleted_count

    def render_sidebar(self, is_locked: bool):
        render_sidebar_component(
            is_locked=is_locked,
            agent=self.agent,
            sheets=self.sheets,
            clear_previous_result_messages_callback=self._clear_previous_result_messages,
        )

    def _build_thumbnail_upload_payload(self, article, image_file, image_index: int, thumbnail_alt_strategy: str) -> tuple[str, dict]:
        language_label = getattr(article, "language", None)
        original_name = getattr(image_file, "name", "") or "image.jpg"
        extension = os.path.splitext(original_name)[1].lower() or ".jpg"

        return self._build_media_upload_payload(
            article, extension, image_index,
            explicit_alt_text=self._resolve_single_alt_text(article, image_index, language_label, thumbnail_alt_strategy),
            filename_source="title",
        )

    @staticmethod
    def _sanitize_wc_error_message(message: str) -> str:
        text = str(message or "")
        if not text:
            return text
        text = re.sub(r"([?&]consumer_key=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
        text = re.sub(r"([?&]consumer_secret=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
        text = re.sub(r"(consumer_key=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
        text = re.sub(r"(consumer_secret=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _extract_keywords_list(raw_keyword: str) -> list[str]:
        normalized = (raw_keyword or "").strip()
        if not normalized: return []
        parts = [part.strip() for part in re.split(r"[,;\n\|、，；]+", normalized) if part.strip()]
        return parts if parts else [normalized]

    def _resolve_target_locales(self, language_label: str | None, raw_keyword: str, site_name: str | None = None) -> list[str]:
        language_hint = (language_label or "").strip().lower()
        detected_lang = MediaService.detect_keyword_language(raw_keyword or "")
        active_site = str(site_name or st.session_state.get("active_site") or "").strip().lower()

        if active_site == "innhanhgeta.com":
            return ["GETA印刷", "印刷"] if ("trung" in language_hint or "chinese" in language_hint or detected_lang == "zh") else ["GETA", "in ấn"]

        if active_site == "quangcao.getagroup.vn":
            return ["GETA广告", "广告"] if ("trung" in language_hint or "chinese" in language_hint or detected_lang == "zh") else ["GETA", "quảng cáo"]

        if active_site == "mocbaibavet.com":
            if "trung" in language_hint or "chinese" in language_hint or detected_lang == "zh":
                return TARGET_LOCALES_BY_LANGUAGE["zh"]
            return TARGET_LOCALES_BY_LANGUAGE["vi"]

        if "trung" in language_hint or "chinese" in language_hint or detected_lang == "zh":
            return ["dịch vụ", "chuyên nghiệp"]
        return ["dịch vụ", "chuyên nghiệp"]

    def _build_keyword_local_phrase(self, raw_keyword: str, image_index: int, language_label: str | None = None, site_name: str | None = None) -> str:
        keywords = self._extract_keywords_list(raw_keyword)
        keyword = keywords[image_index % len(keywords)] if keywords else (raw_keyword.strip() or "dịch vụ")
        target_locales = self._resolve_target_locales(language_label, raw_keyword, site_name=site_name)
        locale = target_locales[image_index % len(target_locales)]
        return f"{keyword} {locale}".strip() if locale else keyword

    def _resolve_single_alt_text(self, article, image_index: int, language_label: str | None, alt_strategy: str) -> str:
        active_site = st.session_state.get("active_site")
        if alt_strategy == "title":
            title_text = (article.title or article.keyword or "dịch vụ").strip()
            return f"{title_text} - {self._build_keyword_local_phrase(article.keyword or '', image_index, language_label, site_name=active_site)}".strip(" -")
        return self._build_keyword_local_phrase(article.keyword or "", image_index, language_label, site_name=active_site)

    def _build_alt_texts_for_article_images(self, article, article_images, language_label: str, alt_strategy: str) -> list[str]:
        count = len(article_images or [])
        if count <= 0: return []
        active_site = st.session_state.get("active_site")
        if alt_strategy == "ai":
            try:
                target_locales = self._resolve_target_locales(language_label, article.keyword or "", site_name=active_site)
                return self.orchestrator.agent.generate_alt_texts(
                    title=article.title or article.keyword or "dịch vụ",
                    keywords=self._extract_keywords_list(article.keyword or ""),
                    locales=target_locales,
                    language=language_label,
                    count=count
                )
            except Exception as e:
                pass # Fallback to keyword if AI fails
        if alt_strategy == "title":
            title_text = (article.title or article.keyword or "dịch vụ").strip()
            raw_alts = [f"{title_text} - {self._build_keyword_local_phrase(article.keyword or '', idx, language_label, site_name=active_site)}".strip(" -") for idx in range(count)]
            return raw_alts
        return [self._build_keyword_local_phrase(article.keyword or "", idx, language_label, site_name=active_site) for idx in range(count)]

    def _build_media_upload_payload(
        self,
        article,
        extension: str,
        image_index: int,
        explicit_alt_text: str | None = None,
        filename_source: str = "keyword",
    ) -> tuple[str, dict]:
        keyword = (article.keyword or "").strip() or "hinh-anh"
        article_description = (getattr(article, "meta_description", "") or "").strip()
        language_label = getattr(article, "language", None)
        keyword_language = MediaService.detect_keyword_language(keyword)
        title_source = (getattr(article, "title", "") or "").strip()
        slug_source = (getattr(article, "slug", "") or "").strip()

        if filename_source == "title":
            raw_file_base = title_source or slug_source or keyword
        else:
            # Safety: Nếu alt_text có dạng 'image/webp' (regex fallback cũ) thì bỏ qua
            if explicit_alt_text and ("image/" in explicit_alt_text or len(explicit_alt_text) < 3):
                raw_file_base = keyword
            else:
                raw_file_base = explicit_alt_text or keyword

        if language_label == "Tiếng Trung Giản Thể" or keyword_language == "zh":
            english_base = unidecode(raw_file_base or "").strip()
            safe_base = MediaService.sanitize_filename_base(english_base, keep_unicode=False, fallback="image")
            details_text = explicit_alt_text or self._build_keyword_local_phrase(keyword, image_index, "Tiếng Trung Giản Thể", site_name=st.session_state.get("active_site"))
        else:
            safe_base = MediaService.sanitize_filename_base(raw_file_base, keep_unicode=False, fallback="hinh-anh")
            details_text = explicit_alt_text or self._build_keyword_local_phrase(keyword, image_index, language_label, site_name=st.session_state.get("active_site"))

        if explicit_alt_text:
            file_name = f"{safe_base}{extension}"
        else:
            file_name = f"{safe_base}-{image_index + 1}{extension}"

        # Generate distinct strings for metadata to avoid duplicate SEO signals
        subject_text = f"Hình ảnh về {details_text}" if getattr(article, "language", "") == "Tiếng Việt" else f"关于 {details_text} 的图片"
        caption_text = f"{details_text} - {keyword}"

        active_site = st.session_state.get("active_site")
        author_text = active_site or "GETA Group"
        copyright_text = f"Copyright (C) {author_text}"

        details = {
            "title": details_text, 
            "alt_text": details_text, 
            "subject": subject_text, 
            "caption": caption_text,
            "description": f"{article_description} - {details_text}" if article_description else details_text, 
            "keywords": keyword, # Chèn toàn bộ danh sách keywords vào thẻ tags của ảnh
            "author": author_text,
            "copyright": copyright_text,
        }
        return file_name, details

    def _upload_media_and_get_info_with_fallback(self, file_bytes: bytes, file_name: str, details: dict | None = None) -> dict:
        try:
            return self.publisher.upload_media_and_get_info(file_bytes, file_name, details=details)
        except TypeError:
            return self.publisher.upload_media_and_get_info(file_bytes, file_name)

    @staticmethod
    def _inject_wp_media_urls_into_markdown(
        content_markdown: str,
        image_urls: list[str],
        max_images: int,
        alt_texts: list[str] | None = None,
    ) -> str:
        content = str(content_markdown or "").strip()
        if not content or not image_urls or max_images <= 0:
            return content_markdown

        selected_urls = [str(url or "").strip() for url in image_urls[:max_images] if str(url or "").strip()]
        if not selected_urls:
            return content_markdown

        paragraphs = [part.strip() for part in content.split("\n\n") if part.strip()]
        image_blocks: list[str] = []
        for idx, image_url in enumerate(selected_urls):
            custom_alt = alt_texts[idx] if alt_texts and idx < len(alt_texts) else f"image-{idx + 1}"
            image_blocks.append(f"![{custom_alt}]({image_url})")

        if len(paragraphs) < 2:
            return content + "\n\n" + "\n\n".join(image_blocks)

        total_paragraphs = len(paragraphs)
        insert_positions = {
            max(1, min(total_paragraphs - 1, int((index + 1) * total_paragraphs / (len(image_blocks) + 1))))
            for index in range(len(image_blocks))
        }
        sorted_positions = sorted(insert_positions)

        while len(sorted_positions) < len(image_blocks):
            for candidate in range(1, total_paragraphs):
                if candidate not in insert_positions:
                    insert_positions.add(candidate)
                    sorted_positions = sorted(insert_positions)
                    if len(sorted_positions) == len(image_blocks):
                        break

        result_parts: list[str] = []
        image_cursor = 0
        for idx, paragraph in enumerate(paragraphs):
            result_parts.append(paragraph)
            paragraph_index_1_based = idx + 1
            if image_cursor < len(image_blocks) and paragraph_index_1_based == sorted_positions[image_cursor]:
                result_parts.append(image_blocks[image_cursor])
                image_cursor += 1

        while image_cursor < len(image_blocks):
            result_parts.append(image_blocks[image_cursor])
            image_cursor += 1

        return "\n\n".join(result_parts)

    def _apply_images_to_ai_output(self, ai_output, article, article_images, per_post_images: int, language_label: str, enable_grouping_mvp: bool, alt_strategy: str):
        article_alt_texts = self._build_alt_texts_for_article_images(article, article_images, language_label, alt_strategy)
        if isinstance(ai_output, dict):
            use_wp_urls = bool(article_images) and all(isinstance(item, str) for item in article_images)
            if use_wp_urls:
                ai_output["content_markdown"] = self._inject_wp_media_urls_into_markdown(
                    ai_output.get("content_markdown", ""),
                    article_images,
                    per_post_images,
                    alt_texts=article_alt_texts,
                )
            else:
                ai_output["content_markdown"] = ContentService.inject_images_into_markdown(
                    ai_output.get("content_markdown", ""), article_images, per_post_images, alt_texts=article_alt_texts,
                )
        return ai_output
    
    def _upload_inline_images_and_replace_sources(self, content_markdown: str, article, post_index: int) -> str:
        """Giao tiếp với ContentService để tải lên ảnh hàng loạt (Bất đồng bộ)"""
        return ContentService.upload_inline_images_concurrently(
            content_markdown=content_markdown,
            article=article,
            post_index=post_index,
            payload_builder_callback=self._build_media_upload_payload,
            upload_callback=self._upload_media_and_get_info_with_fallback,
            max_workers=5,
        )

    @staticmethod
    def _parse_csv_like_values(value) -> list[str]:
        if value is None:
            return []
        normalized = str(value).strip()
        if not normalized or normalized.lower() in {"nan", "none", "null"}:
            return []
        normalized = normalized.strip("\"'")
        parts = re.split(r"[,;|\n\r、，；]+", normalized)
        return [item.strip().strip("\"'") for item in parts if item and item.strip()]

    @staticmethod
    def _normalize_uploaded_image_name(file_name: str) -> str:
        return (file_name or "").strip().lower()

    @staticmethod
    def _build_auto_product_id(name: str, sku: str, row_number: int) -> str:
        base = str(sku or "").strip() or str(name or "").strip() or f"row-{row_number}"
        digest = hashlib.md5(base.encode("utf-8")).hexdigest()[:8]
        return f"AUTO-{row_number:04d}-{digest}"

    @staticmethod
    def _detect_language_suffix_for_product(row_data: dict) -> str:
        probe_text = " ".join([
            str(row_data.get("name", "") or ""),
            str(row_data.get("description", "") or ""),
            str(row_data.get("short_description", "") or ""),
            str(row_data.get("categories", "") or ""),
        ]).strip()

        if re.search(r"[\u4e00-\u9fff]", probe_text):
            return "ZH"

        if re.search(r"[A-Za-zÀ-ỹ]", probe_text):
            return "VI"

        return "INTL"

    @staticmethod
    def _append_sku_suffix_if_missing(sku: str, suffix: str) -> str:
        normalized_sku = str(sku or "").strip()
        normalized_suffix = str(suffix or "").strip().upper()
        if not normalized_sku or not normalized_suffix:
            return normalized_sku

        sku_upper = normalized_sku.upper()
        if sku_upper.endswith(f"-{normalized_suffix}"):
            return normalized_sku
        return f"{normalized_sku}-{normalized_suffix}"

    @staticmethod
    def _score_decoded_csv_text(text: str) -> float:
        sample = (text or "")[:50000]
        if not sample:
            return float("inf")

        mojibake_markers = ["Ã", "Â", "Ä", "Å", "Æ", "Ð", "Ñ", "Ø", "Ý", "�"]
        marker_hits = sum(sample.count(marker) for marker in mojibake_markers)
        question_hits = sample.count("?")
        weird_control_hits = sum(1 for char in sample if ord(char) < 32 and char not in {"\n", "\r", "\t"})

        total_chars = max(1, len(sample))
        question_ratio = question_hits / total_chars
        return (marker_hits * 8.0) + (weird_control_hits * 10.0) + (question_ratio * 60.0)

    def _read_products_csv_with_fallback(self, uploaded_file) -> tuple[pd.DataFrame, str]:
        raw_bytes = uploaded_file.getvalue()
        encodings = ["utf-8-sig", "utf-8", "utf-16", "utf-16le", "utf-16be", "gb18030", "gbk", "big5", "cp1258", "cp1252", "latin1"]

        best_df: pd.DataFrame | None = None
        best_encoding = ""
        best_score = float("inf")
        decode_errors: list[str] = []

        for encoding in encodings:
            try:
                decoded_text = raw_bytes.decode(encoding)
            except Exception as decode_error:
                decode_errors.append(f"{encoding}: {decode_error}")
                continue

            try:
                candidate_df = pd.read_csv(io.StringIO(decoded_text))
            except Exception as parse_error:
                decode_errors.append(f"{encoding}: {parse_error}")
                continue

            score = self._score_decoded_csv_text(decoded_text)
            if score < best_score:
                best_score = score
                best_df = candidate_df
                best_encoding = encoding

            if score == 0 and encoding in {"utf-8-sig", "utf-8", "utf-16", "gb18030"}:
                break

        if best_df is None:
            raise ValueError(
                "Không giải mã được CSV với các encoding hỗ trợ. "
                f"Chi tiết: {' | '.join(decode_errors[:5])}"
            )

        return best_df, best_encoding

    def _read_products_input_file(self, uploaded_file) -> tuple[pd.DataFrame, str]:
        file_name = str(getattr(uploaded_file, "name", "") or "").lower()
        if file_name.endswith(".xlsx"):
            uploaded_file.seek(0)
            return pd.read_excel(uploaded_file), "xlsx"
        return self._read_products_csv_with_fallback(uploaded_file)

    def _attach_local_images_to_woocommerce_rows(
        self,
        rows: list[dict],
        uploaded_local_images,
        progress_callback=None,
        max_workers: int | None = None,
        max_retries: int | None = None,
        retry_delay_seconds: float | None = None,
    ) -> tuple[list[dict], list[str]]:
        worker_limit = max(1, int(max_workers or MAX_WC_MEDIA_WORKERS))
        retry_limit = max(1, int(max_retries or MAX_WC_MEDIA_RETRIES))
        retry_delay = max(0.2, float(retry_delay_seconds or MAX_WC_MEDIA_RETRY_DELAY_SECONDS))

        uploaded_files = uploaded_local_images or []
        file_lookup = {
            self._normalize_uploaded_image_name(getattr(file_obj, "name", "")): file_obj
            for file_obj in uploaded_files
            if self._normalize_uploaded_image_name(getattr(file_obj, "name", ""))
        }

        missing_file_errors: list[str] = []
        referenced_files: set[str] = set()

        for row_data in rows:
            row_number = int(row_data.get("__csv_row", 0))
            product_name = str(row_data.get("name", "")).strip() or f"row-{row_number}"
            local_file_names = self._parse_csv_like_values(row_data.get("local_images"))
            for local_file_name in local_file_names:
                normalized_name = self._normalize_uploaded_image_name(local_file_name)
                if normalized_name not in file_lookup:
                    missing_file_errors.append(
                        f"MISSING_FILE | Dòng {row_number} - {product_name}: thiếu file local '{local_file_name}'."
                    )
                else:
                    referenced_files.add(normalized_name)

        if missing_file_errors:
            return rows, missing_file_errors

        if not referenced_files:
            return rows, []

        ordered_file_names = sorted(referenced_files)
        total_files = len(ordered_file_names)
        if progress_callback:
            progress_callback(0, total_files)

        uploaded_ref_by_name: dict[str, str] = {}
        upload_errors: list[str] = []

        def upload_single_file(normalized_name: str) -> tuple[str, str]:
            upload_file = file_lookup.get(normalized_name)
            if upload_file is None:
                raise ValueError(f"Không tìm thấy file local '{normalized_name}' trong uploader.")

            # Trích xuất metadata từ dòng sản phẩm đầu tiên tham chiếu ảnh này
            row_ref = None
            for r in rows:
                local_imgs = self._parse_csv_like_values(r.get("local_images"))
                if any(self._normalize_uploaded_image_name(img) == normalized_name for img in local_imgs):
                    row_ref = r
                    break

            details = {}
            if row_ref:
                p_name = str(row_ref.get("name") or "").strip()
                p_sku = str(row_ref.get("sku") or "").strip()
                p_desc = str(row_ref.get("short_description") or row_ref.get("description") or "").strip()
                p_cats = str(row_ref.get("categories") or "").strip()
                
                details = {
                    "title": p_name,
                    "subject": f"{p_name} - {p_sku}" if p_sku else p_name,
                    "description": p_desc[:300] if p_desc else p_name,
                    "keywords": p_cats or p_name,
                }

            active_site = st.session_state.get("active_site")
            details["author"] = active_site or "GETA Group"
            details["copyright"] = f"Copyright (C) {details['author']}"

            file_bytes = upload_file.getvalue()
            file_name = getattr(upload_file, "name", "image.jpg")
            try:
                file_bytes = MediaService.embed_metadata_into_image_bytes(file_bytes, file_name, details)
            except Exception as embed_err:
                print(f"Lỗi nhúng metadata ảnh product '{file_name}': {embed_err}")

            last_error: Exception | None = None
            for attempt in range(1, retry_limit + 1):
                try:
                    media_info = self._upload_media_and_get_info_with_fallback(
                        file_bytes,
                        file_name,
                        details=details,
                    )
                    media_id_raw = media_info.get("id")
                    media_ref = ""
                    if media_id_raw is not None and str(media_id_raw).strip().isdigit():
                        media_ref = str(int(str(media_id_raw).strip()))
                    else:
                        media_ref = str(media_info.get("source_url") or "").strip()

                    if not media_ref:
                        raise ValueError(
                            f"Upload ảnh local thất bại, không nhận được media id/source_url cho file '{file_name}'."
                        )
                    return normalized_name, media_ref
                except Exception as error:
                    last_error = error
                    if attempt >= retry_limit:
                        break
                    time.sleep(retry_delay * attempt)

            raise ValueError(
                f"Upload thất bại sau {retry_limit} lần thử: {last_error}"
            )

        worker_count = max(1, min(worker_limit, total_files))
        completed_files = 0
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(upload_single_file, normalized_name): normalized_name
                for normalized_name in ordered_file_names
            }

            for future in as_completed(future_map):
                normalized_name = future_map[future]
                try:
                    uploaded_name, uploaded_ref = future.result()
                    uploaded_ref_by_name[uploaded_name] = uploaded_ref
                except Exception as upload_error:
                    upload_errors.append(f"UPLOAD_FAILED | {normalized_name}: {upload_error}")

                completed_files += 1
                if progress_callback:
                    progress_callback(completed_files, total_files)

        if upload_errors:
            return rows, upload_errors

        merged_rows: list[dict] = []
        for row_data in rows:
            current_wp_media_tokens = self._parse_csv_like_values(row_data.get("wp_media"))
            local_file_names = self._parse_csv_like_values(row_data.get("local_images"))

            merged_wp_media_tokens: list[str] = []
            for token in current_wp_media_tokens:
                if token and token not in merged_wp_media_tokens:
                    merged_wp_media_tokens.append(token)

            for local_file_name in local_file_names:
                normalized_name = self._normalize_uploaded_image_name(local_file_name)
                uploaded_ref = uploaded_ref_by_name.get(normalized_name)
                if uploaded_ref and uploaded_ref not in merged_wp_media_tokens:
                    merged_wp_media_tokens.append(uploaded_ref)

            prepared_row = dict(row_data)
            prepared_row["wp_media"] = ", ".join(merged_wp_media_tokens)
            merged_rows.append(prepared_row)

        return merged_rows, []

    def _resolve_wp_media_token_to_image_ref(self, media_token: str) -> str:
        normalized_token = str(media_token or "").strip()
        if not normalized_token:
            return ""

        compact_token = normalized_token.strip().strip("/")
        numeric_match = re.fullmatch(
            r"(?:(?:https?://)?)?(?:id\s*[:#-]?\s*)?(\d+)(?:\.0+)?",
            compact_token,
            flags=re.IGNORECASE,
        )
        if numeric_match:
            return str(int(numeric_match.group(1)))

        token_lower = normalized_token.lower()
        if token_lower.startswith("http://") or token_lower.startswith("https://"):
            return normalized_token

        if normalized_token.startswith("/"):
            site_url = str(getattr(self.publisher, "site_url", "") or "").rstrip("/")
            if site_url:
                return f"{site_url}{normalized_token}"

        if re.fullmatch(r"\d+", normalized_token):
            if not self.publisher:
                raise ValueError("WordPress publisher chưa sẵn sàng để resolve media ID.")
            return str(int(normalized_token))

        if not self.publisher:
            raise ValueError("WordPress publisher chưa sẵn sàng để resolve wp_media token.")

        find_by_token = getattr(self.publisher, "find_media_source_url_by_token", None)
        if callable(find_by_token):
            return find_by_token(normalized_token)

        media_endpoint = str(getattr(self.publisher, "media_endpoint", "") or "").strip()
        auth = getattr(self.publisher, "auth", None)
        if media_endpoint and auth:
            search_term = os.path.splitext(os.path.basename(normalized_token))[0].strip() or normalized_token
            response = requests.get(
                media_endpoint,
                params={"search": search_term, "per_page": 100},
                auth=auth,
                timeout=30,
            )
            response.raise_for_status()
            items = response.json() or []
            if not isinstance(items, list) or not items:
                raise ValueError(f"Không tìm thấy media cho token '{normalized_token}'.")

            normalized_base = os.path.splitext(os.path.basename(normalized_token))[0].strip().lower()
            for item in items:
                source_url = str(item.get("source_url") or "").strip()
                if not source_url:
                    continue
                source_base = os.path.splitext(os.path.basename(source_url))[0].strip().lower()
                if normalized_base and source_base == normalized_base:
                    return source_url

            first_url = str(items[0].get("source_url") or "").strip()
            if first_url:
                return first_url

        raise ValueError(
            "WordPress publisher cache cũ chưa hỗ trợ resolve wp_media token theo tên file. "
            "Vui lòng restart app để làm mới cache."
        )

    def _attach_wp_media_to_woocommerce_rows(self, rows: list[dict], progress_callback=None) -> tuple[list[dict], list[str]]:
        merged_rows: list[dict] = []
        resolve_errors: list[str] = []

        total_rows = len(rows)
        if progress_callback:
            progress_callback(0, total_rows)

        for idx, row_data in enumerate(rows, start=1):
            row_number = int(row_data.get("__csv_row", 0))
            product_name = str(row_data.get("name", "")).strip() or f"row-{row_number}"

            current_refs = self._parse_csv_like_values(row_data.get("images"))
            wp_media_tokens = self._parse_csv_like_values(row_data.get("wp_media"))

            merged_refs: list[str] = []
            for image_ref in current_refs:
                if image_ref and image_ref not in merged_refs:
                    merged_refs.append(image_ref)

            for token in wp_media_tokens:
                try:
                    resolved_ref = self._resolve_wp_media_token_to_image_ref(token)
                except Exception as resolve_error:
                    resolve_errors.append(
                        f"WP_MEDIA_INVALID | Dòng {row_number} - {product_name}: {resolve_error}"
                    )
                    continue

                if resolved_ref and resolved_ref not in merged_refs:
                    merged_refs.append(resolved_ref)

            prepared_row = dict(row_data)
            prepared_row["images"] = ", ".join(merged_refs)
            merged_rows.append(prepared_row)

            if progress_callback:
                progress_callback(idx, total_rows)

        if resolve_errors:
            return rows, resolve_errors
        return merged_rows, []

    def render_product_automation_panel(self, is_locked: bool):
        active_site = st.session_state.get("active_site")
        render_product_automation_panel_component(
            is_locked=is_locked,
            wc_publisher=self.wc_publisher,
            orchestrator=self.orchestrator,
            global_task_state=GLOBAL_TASK_STATE,
            reset_wc_result_state_callback=reset_wc_result_state,
            load_wc_product_categories_callback=lambda: load_wc_product_categories_cached(site_name=active_site),
            read_products_input_file_callback=self._read_products_input_file,
            parse_csv_like_values_callback=self._parse_csv_like_values,
            build_auto_product_id_callback=self._build_auto_product_id,
            detect_language_suffix_for_product_callback=self._detect_language_suffix_for_product,
            append_sku_suffix_if_missing_callback=self._append_sku_suffix_if_missing,
            find_existing_skus_safe_callback=self._find_existing_skus_safe,
            attach_local_images_to_rows_callback=self._attach_local_images_to_woocommerce_rows,
            attach_wp_media_to_rows_callback=self._attach_wp_media_to_woocommerce_rows,
            sanitize_wc_error_message_callback=self._sanitize_wc_error_message,
            max_wc_workers=MAX_WC_WORKERS,
            max_wc_media_workers=MAX_WC_MEDIA_WORKERS,
            max_wc_media_retries=MAX_WC_MEDIA_RETRIES,
            max_wc_media_retry_delay_seconds=MAX_WC_MEDIA_RETRY_DELAY_SECONDS,
        )

    def render_processing_panel(self, is_locked: bool):
        active_site = st.session_state.get("active_site")
        render_processing_panel_component(
            is_locked=is_locked,
            agent=self.agent,
            orchestrator=self.orchestrator,
            task_manager=task_manager,
            active_site=active_site,
            load_wp_media_items_callback=lambda: load_wp_media_items_cached(site_name=active_site),
            apply_images_to_ai_output_callback=self._apply_images_to_ai_output,
            alt_strategy_map=ALT_STRATEGY_MAP,
            language_prompt_map=LANGUAGE_PROMPT_MAP,
            max_generate_workers=MAX_GENERATE_WORKERS,
        )

    def render_publishing_panel(self, is_locked: bool):
        active_site = st.session_state.get("active_site")
        render_publishing_panel_component(
            is_locked=is_locked,
            active_site=active_site,
            orchestrator=self.orchestrator,
            load_wp_categories_callback=lambda: load_wp_categories_cached(site_name=active_site),
            build_thumbnail_upload_payload_callback=self._build_thumbnail_upload_payload,
            build_inline_image_alt_texts_callback=self._build_alt_texts_for_article_images,
            upload_inline_images_and_replace_sources_callback=self._upload_inline_images_and_replace_sources,
        )

    def render_auto_pilot_panel(self, is_locked: bool):
        from ui.components.auto_pilot_panel import render_auto_pilot_panel_component
        active_site = st.session_state.get("active_site")
        render_auto_pilot_panel_component(
            is_locked=is_locked,
            agent=self.agent,
            orchestrator=self.orchestrator,
            task_manager=task_manager,
            active_site=active_site,
            sheets=self.sheets,
            alt_strategy_map=ALT_STRATEGY_MAP,
            language_prompt_map=LANGUAGE_PROMPT_MAP,
            max_generate_workers=MAX_GENERATE_WORKERS,
            apply_images_to_ai_output_callback=self._apply_images_to_ai_output,
        )


    def run(self):
        active_site = st.session_state.get("active_site")
        if not active_site:
            render_site_selector()
            return

        try:
            db_processing = ArticleRepository.has_processing_articles()
        except RepositoryError as e:
            st.warning(f"Không kiểm tra được trạng thái PROCESSING: {str(e)}")
            db_processing = False

        # Use task_manager for generator lock state, and GLOBAL_TASK_STATE for wc publish
        current_state = task_manager.get_snapshot()
        is_locked_generate = current_state["is_running"]
        is_locked_wc = GLOBAL_TASK_STATE["is_running"]
        is_locked = is_locked_generate or is_locked_wc or db_processing

        if db_processing and not is_locked_generate and current_state["feature"] != "generate":
            task_manager.update(feature="generate")
        
        self.render_sidebar(is_locked)
        active_site = str(st.session_state.get("active_site") or "").strip()
        active_site_label = html.escape(active_site or "Chưa chọn site")
        st.markdown(
            f"""
            <style>
            .active-site-banner {{
                margin: 0.35rem 0 1rem 0;
                border: 1px solid rgba(56, 189, 248, 0.45);
                border-radius: 14px;
                background: linear-gradient(135deg, rgba(2, 132, 199, 0.25) 0%, rgba(30, 64, 175, 0.18) 55%, rgba(15, 23, 42, 0.55) 100%);
                box-shadow: 0 8px 30px rgba(2, 132, 199, 0.22);
                padding: 14px 18px;
            }}
            .active-site-banner .active-site-title {{
                color: #bae6fd;
                font-size: 0.82rem;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                font-weight: 700;
                margin-bottom: 0.25rem;
                opacity: 0.95;
            }}
            .active-site-banner .active-site-name {{
                color: #f8fafc;
                font-size: 1.65rem;
                font-weight: 800;
                line-height: 1.2;
                word-break: break-word;
            }}
            </style>
            <div class="active-site-banner">
                <div class="active-site-title">Site Dang Lam Viec</div>
                <div class="active-site-name">{active_site_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.get("active_feature", "Post Automation") == "Product Automation":
            self.render_product_automation_panel(is_locked)
            return
            
        if st.session_state.get("active_feature", "Post Automation") == "Auto Pilot":
            self.render_auto_pilot_panel(is_locked)
            return
            
        df_articles = self.fetch_datagrid_view()
        self.render_sheets_sync_toolbar(df_articles, is_locked)
        render_articles_grid_component(
            df_articles=df_articles,
            is_locked=is_locked,
            delete_rows_callback=self._delete_articles_rows,
        )

        st.divider()
        col1, col2 = st.columns(2, gap="large")
        with col1: self.render_processing_panel(is_locked)
        with col2: self.render_publishing_panel(is_locked)

if __name__ == "__main__":
    app = SEOAutomationUI()
    app.run()