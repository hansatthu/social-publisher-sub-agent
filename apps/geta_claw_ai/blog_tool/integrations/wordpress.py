import os
import mimetypes
import json
import re
import time
import requests
import markdown
from urllib.parse import quote
from unidecode import unidecode
from dotenv import load_dotenv

# Load cấu hình từ .env
load_dotenv()

class WordPressIntegrationError(Exception):
    """Custom Exception cho các lỗi liên quan đến WordPress API"""
    pass

class WordPressPublisher:
    def __init__(self, site_url=None, username=None, app_password=None):
        self.site_url = (site_url or os.getenv("WP_SITE_URL", "")).rstrip('/')
        self.username = username or os.getenv("WP_USERNAME")
        self.app_password = app_password or os.getenv("WP_APP_PASSWORD")
        self.request_retry_attempts = max(1, int(os.getenv("WP_REQUEST_RETRY_ATTEMPTS", "3") or 3))
        self.request_retry_backoff_seconds = max(0.1, float(os.getenv("WP_REQUEST_RETRY_BACKOFF_SECONDS", "1.2") or 1.2))

        if not all([self.site_url, self.username, self.app_password]):
            raise ValueError("Thiếu cấu hình WP_SITE_URL, WP_USERNAME hoặc WP_APP_PASSWORD trong file .env hoặc truyền vào constructor")

        self.api_endpoint = f"{self.site_url}/wp-json/wp/v2/posts"
        self.categories_endpoint = f"{self.site_url}/wp-json/wp/v2/categories"
        self.tags_endpoint = f"{self.site_url}/wp-json/wp/v2/tags"
        self.media_endpoint = f"{self.site_url}/wp-json/wp/v2/media"
        # Sử dụng Basic Auth với Application Passwords của WP
        self.auth = (self.username, self.app_password)

    @staticmethod
    def _is_transient_request_error(error: Exception) -> bool:
        if not isinstance(error, requests.exceptions.RequestException):
            return False

        response = getattr(error, "response", None)
        if response is not None and int(getattr(response, "status_code", 0)) in {429, 500, 502, 503, 504}:
            return True

        if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return True

        lowered = str(error).lower()
        transient_markers = [
            "connection aborted",
            "connection reset",
            "forcibly closed by the remote host",
            "10054",
            "timed out",
        ]
        return any(marker in lowered for marker in transient_markers)

    def _request_with_retries(self, method: str, url: str, **kwargs) -> requests.Response:
        if "auth" not in kwargs:
            kwargs["auth"] = self.auth

        last_error: requests.exceptions.RequestException | None = None
        for attempt in range(1, self.request_retry_attempts + 1):
            try:
                response = requests.request(method=method, url=url, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as error:
                last_error = error
                should_retry = self._is_transient_request_error(error) and attempt < self.request_retry_attempts
                if not should_retry:
                    raise
                sleep_seconds = self.request_retry_backoff_seconds * (2 ** (attempt - 1))
                time.sleep(sleep_seconds)

        if last_error:
            raise last_error

        raise WordPressIntegrationError("Request tới WordPress thất bại nhưng không có chi tiết lỗi.")

    def list_categories(self) -> list[dict]:
        params = {
            "per_page": 100,
            "page": 1,
            "hide_empty": "false",
            "_fields": "id,name,slug",
        }
        categories: list[dict] = []
        while True:
            response = requests.get(
                self.categories_endpoint,
                params=params,
                auth=self.auth,
                timeout=30,
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            categories.extend(batch)
            if len(batch) < params["per_page"]:
                break
            params["page"] += 1
        return categories

    def list_taxonomy_terms(self, taxonomy: str) -> list[dict]:
        endpoint = f"{self.site_url}/wp-json/wp/v2/{taxonomy}"
        params = {
            "per_page": 100,
            "page": 1,
            "hide_empty": "false",
            "_fields": "id,name,slug",
        }
        terms: list[dict] = []
        while True:
            response = requests.get(
                endpoint,
                params=params,
                auth=self.auth,
                timeout=30,
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            terms.extend(batch)
            if len(batch) < params["per_page"]:
                break
            params["page"] += 1
        return terms

    def _convert_markdown_to_html(self, md_text: str) -> str:
        """Chuyển đổi Markdown từ LLM sang HTML chuẩn cho WordPress"""
        # Sử dụng extensions để hỗ trợ table, list, header chuẩn xác
        return markdown.markdown(md_text, extensions=['extra', 'nl2br'])

    @staticmethod
    def _normalize_tag_names(keyword: str) -> list[str]:
        raw_keyword = (keyword or "").strip()
        if not raw_keyword:
            return []

        parts = [part.strip() for part in re.split(r"[,;\n\|、，；]+", raw_keyword) if part.strip()]
        if not parts:
            return []

        unique_tags: list[str] = []
        seen: set[str] = set()
        for part in parts:
            normalized = part.lower()
            if normalized not in seen:
                seen.add(normalized)
                unique_tags.append(part)
        return unique_tags[:8]

    def _find_tag_id(self, tag_name: str) -> int | None:
        response = requests.get(
            self.tags_endpoint,
            params={"search": tag_name, "per_page": 100},
            auth=self.auth,
            timeout=30,
        )
        response.raise_for_status()
        tags = response.json() or []
        for tag in tags:
            name = str(tag.get("name", "")).strip().lower()
            slug = str(tag.get("slug", "")).strip().lower()
            if name == tag_name.strip().lower() or slug == tag_name.strip().lower().replace(" ", "-"):
                return tag.get("id")
        return None

    def _create_tag(self, tag_name: str) -> int:
        response = requests.post(
            self.tags_endpoint,
            json={"name": tag_name},
            auth=self.auth,
            timeout=30,
        )
        response.raise_for_status()
        tag_id = response.json().get("id")
        if not tag_id:
            raise WordPressIntegrationError(f"Không tạo được tag '{tag_name}' trên WordPress.")
        return tag_id

    def _resolve_category_id(self, category_name: str) -> int | None:
        """Tra cứu Category ID theo tên, nếu không có thì tạo mới."""
        if not category_name:
            return None
            
        params = {
            "search": category_name,
            "_fields": "id,name"
        }
        try:
            res = requests.get(self.categories_endpoint, params=params, auth=self.auth, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for cat in data:
                    if cat.get('name', '').lower() == category_name.lower():
                        return cat['id']
                        
            # Không tìm thấy thì tạo mới
            return self._create_category(category_name)
        except Exception:
            return None
            
    def _create_category(self, category_name: str) -> int | None:
        """Tạo mới Category."""
        payload = {"name": category_name}
        try:
            res = requests.post(self.categories_endpoint, json=payload, auth=self.auth, timeout=10)
            if res.status_code == 201:
                return res.json().get('id')
            return None
        except Exception:
            return None

    def _resolve_tag_ids(self, keyword: str) -> list[int]:
        tag_names = self._normalize_tag_names(keyword)
        if not tag_names:
            return []

        tag_ids: list[int] = []
        for tag_name in tag_names:
            existing_id = self._find_tag_id(tag_name)
            if existing_id:
                tag_ids.append(existing_id)
                continue

            try:
                created_id = self._create_tag(tag_name)
                tag_ids.append(created_id)
            except requests.exceptions.RequestException:
                continue

        return tag_ids

    @staticmethod
    def _normalize_language_label(language_label: str | None) -> str:
        raw = str(language_label or "").strip()
        lowered = raw.lower()
        if "việt" in lowered or lowered in {"vietnamese", "vi", "vn"}:
            return "vi"
        if "trung" in lowered or "chinese" in lowered or "简体" in lowered or lowered in {"zh", "zh-cn"}:
            return "zh"
        return ""

    @staticmethod
    def _resolve_expected_blog_path(language_label: str | None) -> str:
        normalized = WordPressPublisher._normalize_language_label(language_label)
        if normalized == "vi":
            return "/vi/blog/"
        return "/blog/"

    @staticmethod
    def _infer_language_code(language_label: str | None, article_data: dict | None = None) -> str:
        normalized = WordPressPublisher._normalize_language_label(language_label)
        if normalized:
            return normalized

        payload = article_data or {}
        probe_text = " ".join(
            [
                str(payload.get("keyword") or ""),
                str((payload.get("seo_metadata") or {}).get("title") or ""),
                str((payload.get("seo_metadata") or {}).get("slug") or ""),
            ]
        ).strip()

        if re.search(r"[\u4e00-\u9fff]", probe_text):
            return "zh"
        if re.search(r"[A-Za-zÀ-ỹ]", probe_text):
            return "vi"
        return ""

    @staticmethod
    def _is_forbidden_zh_meta_error(response: requests.Response | None) -> bool:
        if not response or response.status_code != 403:
            return False
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError):
            return False

        body_text = json.dumps(payload, ensure_ascii=False)
        return "rest_cannot_update" in body_text and (
            "_post_title_zh" in body_text or "_post_content_zh" in body_text
        )

    @staticmethod
    def _build_safe_content_disposition(file_name: str) -> str:
        raw_name = (file_name or "image.jpg").strip() or "image.jpg"
        name, ext = os.path.splitext(raw_name)
        ext = ext or ".jpg"

        ascii_name = unidecode(name)
        ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_name).strip("-._") or "image"
        ascii_file_name = f"{ascii_name}{ext}"

        encoded_utf8_name = quote(raw_name, safe="")
        return f"attachment; filename=\"{ascii_file_name}\"; filename*=UTF-8''{encoded_utf8_name}"

    def upload_media_and_get_info(self, file_bytes: bytes, file_name: str, details: dict | None = None) -> dict:
        """
        Upload ảnh lên thư viện Media của WordPress và trả về thông tin media.
        """
        media_endpoint = f"{self.site_url}/wp-json/wp/v2/media"
        mime_type, _ = mimetypes.guess_type(file_name)
        if not mime_type:
            mime_type = "image/jpeg"

        headers = {
            "Content-Disposition": self._build_safe_content_disposition(file_name),
            "Content-Type": mime_type,
        }

        try:
            response = self._request_with_retries(
                method="POST",
                url=media_endpoint,
                headers=headers,
                data=file_bytes,
                timeout=90,
            )

            media_data = response.json() or {}
            attachment_id = media_data.get("id")
            if not attachment_id:
                raise WordPressIntegrationError("Upload ảnh thành công nhưng không nhận được attachment ID.")

            if details:
                self._update_media_details(attachment_id, details)

            return {
                "id": attachment_id,
                "source_url": media_data.get("source_url"),
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Lỗi upload ảnh lên WP: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f" | Chi tiết: {e.response.text}"
            error_msg += (
                " | Gợi ý: kiểm tra giới hạn upload trên WP/Nginx (client_max_body_size, post_max_size, upload_max_filesize) "
                "và độ ổn định mạng tới host WordPress."
            )
            raise WordPressIntegrationError(error_msg)

    def get_latest_media(self, limit: int = 10) -> list[dict]:
        """Fetch latest media items from WordPress library"""
        params = {
            "per_page": limit,
            "page": 1,
            "orderby": "date",
            "order": "desc",
            "_fields": "id,source_url,title",
        }
        try:
            r = requests.get(self.media_endpoint, params=params, auth=self.auth, timeout=30)
            r.raise_for_status()
            items = r.json()
            # Normalize title
            for item in items:
                if isinstance(item.get("title"), dict):
                    item["title"] = item["title"].get("rendered", "")
            return items
        except Exception as e:
            logger.error(f"Error fetching WP media: {e}")
            return []

    def upload_media(self, file_bytes: bytes, file_name: str, details: dict | None = None) -> int:
        """
        Upload ảnh lên thư viện Media của WordPress và trả về attachment ID.
        """
        media_info = self.upload_media_and_get_info(file_bytes, file_name, details)
        return int(media_info["id"])

    def get_media_source_url(self, media_id: int) -> str:
        media_item_endpoint = f"{self.media_endpoint}/{int(media_id)}"
        try:
            response = requests.get(
                media_item_endpoint,
                auth=self.auth,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json() or {}
            source_url = str(payload.get("source_url") or "").strip()
            if not source_url:
                raise WordPressIntegrationError(
                    f"Media ID {media_id} không có source_url hợp lệ trên WordPress."
                )
            return source_url
        except requests.exceptions.RequestException as e:
            detail = ""
            if hasattr(e, "response") and e.response is not None:
                detail = f" | Chi tiết: {e.response.text}"
            raise WordPressIntegrationError(
                f"Không lấy được media URL cho ID {media_id}: {str(e)}{detail}"
            )

    def find_media_source_url_by_token(self, token: str) -> str:
        normalized_token = str(token or "").strip()
        if not normalized_token:
            raise WordPressIntegrationError("Token media rỗng.")

        search_term = os.path.splitext(os.path.basename(normalized_token))[0].strip() or normalized_token
        try:
            response = requests.get(
                self.media_endpoint,
                params={"search": search_term, "per_page": 100},
                auth=self.auth,
                timeout=30,
            )
            response.raise_for_status()
            items = response.json() or []
        except requests.exceptions.RequestException as e:
            detail = ""
            if hasattr(e, "response") and e.response is not None:
                detail = f" | Chi tiết: {e.response.text}"
            raise WordPressIntegrationError(
                f"Không tìm được media theo token '{normalized_token}': {str(e)}{detail}"
            )

        if not isinstance(items, list) or not items:
            raise WordPressIntegrationError(f"Không tìm thấy media nào cho token '{normalized_token}'.")

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

        raise WordPressIntegrationError(
            f"Media tìm được cho token '{normalized_token}' nhưng không có source_url hợp lệ."
        )

    def _update_media_details(self, attachment_id: int, details: dict) -> None:
        media_item_endpoint = f"{self.site_url}/wp-json/wp/v2/media/{attachment_id}"
        allowed_keys = {"title", "alt_text", "caption", "description"}
        payload = {key: value for key, value in (details or {}).items() if key in allowed_keys and value}
        if not payload:
            return

        try:
            response = requests.post(
                media_item_endpoint,
                json=payload,
                auth=self.auth,
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException:
            return

    def publish_article(
        self,
        article_data: dict,
        status: str = "draft",
        category_id: int | None = None,
        category_name: str | None = None,
        thumbnail_id: int | None = None,
        language_label: str | None = None,
    ) -> dict:
        """
        Đẩy bài viết lên WordPress thông qua REST API.
        article_data: Dictionary chứa title, content_markdown, seo_metadata, keyword.
        status: 'draft' (bản nháp để review) hoặc 'publish' (đăng ngay).
        """
        try:
            print(f"[*] Đang đẩy bài viết '{article_data['seo_metadata']['title']}' lên WordPress...")
        except UnicodeEncodeError:
            print("[*] Đang đẩy bài viết lên WordPress...")
        html_content = self._convert_markdown_to_html(article_data['content_markdown'])
        meta_description = str(article_data['seo_metadata'].get('meta_description') or "").strip()

        # 1. Payload mặc định (Dùng chung cho cả 2 ngôn ngữ)
        payload = {
            "title": article_data['seo_metadata']['title'], # Bắt buộc có để WP tự tạo Slug chuẩn
            "content": html_content,
            "excerpt": meta_description,
            "status": status,
            "meta": {
                "_custom_seo_title": article_data['seo_metadata']['title'],
                "_custom_seo_description": meta_description,
                "_custom_focus_keyword": article_data['keyword']
            }
        }

        # 2. Khớp nối kiến trúc multilingual theme
        normalized_language = self._infer_language_code(language_label, article_data)
        if normalized_language:
            payload["lang"] = normalized_language
        if normalized_language == "zh":
            payload["meta"]["_post_title_zh"] = article_data['seo_metadata']['title']
            payload["meta"]["_post_content_zh"] = html_content

        if article_data['seo_metadata'].get('slug'):
            payload["slug"] = article_data['seo_metadata']['slug']
            
        if category_name and not category_id:
            resolved_cat_id = self._resolve_category_id(category_name)
            if resolved_cat_id:
                category_id = resolved_cat_id
                
        if category_id:
            payload["categories"] = [category_id]
            
        if thumbnail_id:
            payload["featured_media"] = thumbnail_id

        try:
            tag_ids = self._resolve_tag_ids(article_data.get('keyword', ''))
            if tag_ids:
                payload["tags"] = tag_ids
        except requests.exceptions.RequestException:
            pass

        # 3. Gửi HTTP POST Request
        try:
            response = requests.post(
                self.api_endpoint,
                json=payload,
                auth=self.auth,
                timeout=30 # Tránh treo tool nếu server WP phản hồi chậm
            )
            
            # Kiểm tra HTTP Status Code
            response.raise_for_status()
            
            # 4. Bóc tách kết quả trả về
            wp_data = response.json()
            raw_wp_post_url = wp_data.get("link")
            wp_post_id = wp_data.get("id")

            if wp_post_id:
                self._update_post_seo_meta_best_effort(
                    int(wp_post_id),
                    seo_title=article_data['seo_metadata']['title'],
                    meta_description=meta_description,
                    focus_keyword=article_data.get('keyword', ''),
                )

            # Data Transformation: Canonical URL construction for Multilingual Routing
            wp_post_url = raw_wp_post_url
            if raw_wp_post_url and normalized_language:
                expected_path = self._resolve_expected_blog_path(normalized_language)
                base_blog_path = "/blog/"

                # Mutate URL scheme if the expected path differs from the base WP permalink structure
                if expected_path != base_blog_path and base_blog_path in raw_wp_post_url:
                    wp_post_url = raw_wp_post_url.replace(base_blog_path, expected_path, 1)

            return {
                "wp_post_id": wp_post_id,
                "wp_post_url": wp_post_url
            }

        except requests.exceptions.RequestException as e:
            if self._is_forbidden_zh_meta_error(getattr(e, "response", None)):
                retry_payload = {
                    **payload,
                    "meta": dict(payload.get("meta", {})),
                }
                retry_payload["meta"].pop("_post_title_zh", None)
                retry_payload["meta"].pop("_post_content_zh", None)

                try:
                    retry_response = requests.post(
                        self.api_endpoint,
                        json=retry_payload,
                        auth=self.auth,
                        timeout=30,
                    )
                    retry_response.raise_for_status()

                    wp_data = retry_response.json()
                    raw_wp_post_url = wp_data.get("link")
                    wp_post_id = wp_data.get("id")

                    if wp_post_id:
                        self._update_post_seo_meta_best_effort(
                            int(wp_post_id),
                            seo_title=article_data['seo_metadata']['title'],
                            meta_description=meta_description,
                            focus_keyword=article_data.get('keyword', ''),
                        )

                    wp_post_url = raw_wp_post_url
                    if raw_wp_post_url and normalized_language:
                        expected_path = self._resolve_expected_blog_path(normalized_language)
                        base_blog_path = "/blog/"
                        if expected_path != base_blog_path and base_blog_path in raw_wp_post_url:
                            wp_post_url = raw_wp_post_url.replace(base_blog_path, expected_path, 1)

                    return {
                        "wp_post_id": wp_post_id,
                        "wp_post_url": wp_post_url,
                    }
                except requests.exceptions.RequestException as retry_error:
                    error_msg = f"Lỗi kết nối WordPress API: {str(retry_error)}"
                    if hasattr(retry_error, 'response') and retry_error.response is not None:
                        error_msg += f" | Chi tiết: {retry_error.response.text}"
                    raise WordPressIntegrationError(error_msg)

            error_msg = f"Lỗi kết nối WordPress API: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f" | Chi tiết: {e.response.text}"
            raise WordPressIntegrationError(error_msg)

    def _update_post_seo_meta_best_effort(
        self,
        post_id: int,
        seo_title: str,
        meta_description: str,
        focus_keyword: str,
    ) -> None:
        post_endpoint = f"{self.site_url}/wp-json/wp/v2/posts/{post_id}"
        updates = [
            {"meta": {"rank_math_title": seo_title}},
            {"meta": {"rank_math_description": meta_description}},
            {"meta": {"rank_math_focus_keyword": focus_keyword}},
            {"meta": {"yoast_wpseo_title": seo_title}},
            {"meta": {"yoast_wpseo_metadesc": meta_description}},
            {"meta": {"yoast_wpseo_focuskw": focus_keyword}},
            {"meta": {"_aioseo_title": seo_title}},
            {"meta": {"_aioseo_description": meta_description}},
            {"meta": {"_aioseo_keywords": focus_keyword}},
        ]

        for payload in updates:
            try:
                response = requests.post(
                    post_endpoint,
                    json=payload,
                    auth=self.auth,
                    timeout=15,
                )
                if response.status_code >= 400:
                    continue
            except requests.exceptions.RequestException:
                continue