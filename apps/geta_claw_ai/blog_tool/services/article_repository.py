import logging
from typing import List, Dict, Any, Optional
import json
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from database.session import SessionLocal
from database.models import Article, ArticleStatus

logger = logging.getLogger(__name__)

class RepositoryError(Exception):
    """Lỗi tầng Repository để UI xử lý an toàn mà không làm sập ứng dụng."""
    pass

def retry_db_transaction(func):
    """
    Decorator: Exponential backoff + Jitter cho các Transaction.
    Chỉ retry khi gặp OperationalError (Database is locked).
    """
    @retry(
        retry=retry_if_exception_type(OperationalError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=0.5, min=1, max=10),
        reraise=True
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper
class ArticleRepository:
    """
    Data Access Layer (DAL) cho thực thể Article.
    Đóng gói toàn bộ logic truy vấn (SQLAlchemy) để cách ly hoàn toàn với tầng UI.
    """

    @staticmethod
    def _raise_repository_error(operation: str, error: SQLAlchemyError) -> None:
        message = f"Lỗi truy cập dữ liệu khi {operation}."
        if isinstance(error, OperationalError) and "database is locked" in str(error).lower():
            message = "Database đang bận (locked). Vui lòng thử lại sau vài giây."
        raise RepositoryError(message) from error

    @staticmethod
    def _read_value(source: Any, key: str, default: Any = None) -> Any:
        if source is None:
            return default
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)

    @staticmethod
    def _normalize_ai_payload(ai_data: Any) -> Dict[str, str]:
        seo_metadata = ArticleRepository._read_value(ai_data, "seo_metadata", {})

        title = ArticleRepository._read_value(
            seo_metadata,
            "title",
            ArticleRepository._read_value(ai_data, "title", ""),
        )
        meta_description = ArticleRepository._read_value(
            seo_metadata,
            "meta_description",
            ArticleRepository._read_value(ai_data, "meta_description", ""),
        )
        slug = ArticleRepository._read_value(
            seo_metadata,
            "slug",
            ArticleRepository._read_value(ai_data, "slug", ""),
        )
        content_markdown = ArticleRepository._read_value(ai_data, "content_markdown", "")

        return {
            "title": str(title or ""),
            "meta_description": str(meta_description or ""),
            "slug": str(slug or ""),
            "content_markdown": str(content_markdown or ""),
        }

    @staticmethod
    def _normalize_language_label(language: str | None) -> str | None:
        raw = str(language or "").strip()
        if not raw:
            return None
        lowered = raw.lower()
        if "việt" in lowered or lowered in {"vietnamese", "vi", "vn"}:
            return "Tiếng Việt"
        if "trung" in lowered or "chinese" in lowered or "简体" in lowered or lowered in {"zh", "zh-cn"}:
            return "Tiếng Trung Giản Thể"
        return raw

    @staticmethod
    def _get_article_by_id_in_session(db, article_id: int) -> Optional[Article]:
        return db.query(Article).filter(Article.id == article_id).first()

    @staticmethod
    def _expunge_if_present(db, article: Optional[Article]) -> None:
        if article is not None:
            db.expunge(article)

    @staticmethod
    def _build_option_map(items: list[Any], label_builder) -> Dict[str, int]:
        return {label_builder(item): item.id for item in items if getattr(item, "id", None) is not None}

    @staticmethod
    def get_datagrid_overview() -> List[Dict[str, Any]]:
        """
        [DSA Optimization] Projection Query: 
        Chỉ fetch các cột cần thiết cho Data Grid để tiết kiệm RAM (O(N) Space Complexity).
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
                    Article.context,
                ).order_by(Article.id.desc()).all() # Lấy bài mới nhất lên đầu

                result = []
                for article in articles:
                    context_str = str(article.context or "")
                    if "Bài Chính (Pillar Article)" in context_str or "Long-tail keywords:" in context_str:
                        cluster_role = "👑 Pillar"
                    elif "vệ tinh" in context_str.lower() or "satellite" in context_str.lower():
                        cluster_role = "🛰️ Satellite"
                    else:
                        cluster_role = "📄 Đơn Lẻ"

                    result.append({
                        "id": article.id,
                        "type": cluster_role,
                        "title": article.title,
                        "meta_description": article.meta_description,
                        "keyword": article.keyword,
                        "category_name": article.category_name,
                        "language": article.language,
                        "created_at": article.created_at,
                        "status": article.status.value if article.status else None,
                        "seo_score": article.seo_score,
                    })
                return result
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error("tải danh sách bài viết", error)

    @staticmethod
    def has_processing_articles() -> bool:
        """Kiểm tra có bài nào đang ở trạng thái PROCESSING hay không."""
        try:
            with SessionLocal() as db:
                count = db.query(Article.id).filter(Article.status == ArticleStatus.PROCESSING).count()
                return bool(count and count > 0)
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error("kiểm tra trạng thái PROCESSING", error)

    @staticmethod
    def get_processable_options() -> Dict[str, int]:
        """Lấy danh sách bài viết có thể generate lại: PENDING + GENERATE_FAILED (+ legacy FAILED)."""
        try:
            with SessionLocal() as db:
                processable_list = db.query(Article.id, Article.keyword, Article.status).filter(
                    Article.status.in_([
                        ArticleStatus.PENDING,
                        ArticleStatus.GENERATE_FAILED,
                        ArticleStatus.FAILED,
                    ])
                ).order_by(Article.id.desc()).all()
                return ArticleRepository._build_option_map(
                    processable_list,
                    lambda a: f"{a.id} - {a.keyword} [{a.status.value}]",
                )
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error("tải danh sách bài viết cần xử lý", error)

    @staticmethod
    def get_pending_options() -> Dict[str, int]:
        """Backward-compatible alias: dùng processable options (PENDING + FAILED)"""
        return ArticleRepository.get_processable_options()

    @staticmethod
    def get_publishable_options() -> Dict[str, int]:
        """Lấy danh sách bài viết có thể upload lại/đăng: GENERATED + PUBLISHED + UPLOAD_FAILED."""
        try:
            with SessionLocal() as db:
                publishable_list = db.query(Article.id, Article.title, Article.status, Article.seo_score).filter(
                    Article.status.in_([
                        ArticleStatus.GENERATED,
                        ArticleStatus.PUBLISHED,
                        ArticleStatus.UPLOAD_FAILED,
                    ])
                ).order_by(Article.id.desc()).all()
                filtered = [a for a in publishable_list if a.title]
                return ArticleRepository._build_option_map(
                    filtered,
                    lambda a: f"{a.id} - {a.title} [{a.status.value}] (SEO: {a.seo_score if a.seo_score is not None else '-'})",
                )
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error("tải danh sách bài viết có thể đăng", error)

    @staticmethod
    def get_publish_ready_options(min_seo_score: int = 80) -> Dict[str, int]:
        """Chỉ lấy bài GENERATED đạt ngưỡng SEO score để đưa vào Publish Gate."""
        try:
            with SessionLocal() as db:
                publish_ready_list = db.query(Article.id, Article.title, Article.status, Article.seo_score).filter(
                    Article.status == ArticleStatus.GENERATED,
                    Article.seo_score.isnot(None),
                    Article.seo_score >= int(min_seo_score),
                ).order_by(Article.id.desc()).all()
                filtered = [a for a in publish_ready_list if a.title]
                return ArticleRepository._build_option_map(
                    filtered,
                    lambda a: f"{a.id} - {a.title} [{a.status.value}] (SEO: {a.seo_score})",
                )
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error("tải danh sách bài viết đạt ngưỡng SEO để đăng", error)

    @staticmethod
    def get_generated_options() -> Dict[str, int]:
        """Backward-compatible alias: dùng publishable options (GENERATED + PUBLISHED)"""
        return ArticleRepository.get_publishable_options()

    @staticmethod
    def get_recent_published_links(site_name: str | None = None, limit: int = 20) -> list[dict[str, str]]:
        """Lấy danh sách các bài viết đã đăng thành công để làm Dynamic Internal Linking."""
        try:
            with SessionLocal() as db:
                query = db.query(Article.title, Article.wp_post_url).filter(
                    Article.status == ArticleStatus.PUBLISHED,
                    Article.wp_post_url.isnot(None),
                    Article.title.isnot(None)
                )
                if site_name:
                    query = query.filter(
                        (Article.target_site == site_name) |
                        (Article.wp_post_url.like(f"%{site_name}%"))
                    )
                published_list = query.order_by(Article.id.desc()).limit(limit).all()
                return [{"title": p.title, "url": p.wp_post_url} for p in published_list]
        except SQLAlchemyError as error:
            logger.error(f"Lỗi tải danh sách published links: {error}")
            return []

    @staticmethod
    def add_keyword(
        keyword: str, 
        status: ArticleStatus = ArticleStatus.PENDING,
        target_site: str = None,
        source_images: str = None
    ) -> Article:
        """
        Thêm một từ khóa mới vào DB và trả về object độc lập.
        """
        try:
            with SessionLocal() as db:
                new_article = Article(
                    keyword=keyword, 
                    status=status,
                    target_site=target_site,
                    source_images=source_images
                )
                db.add(new_article)
                db.commit()
                db.refresh(new_article)
                db.expunge(new_article)
                return new_article
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error(f"thêm từ khóa mới '{keyword}'", error)

    @staticmethod
    def get_article_by_id(article_id: int) -> Optional[Article]:
        """
        Lấy Data Object độc lập (Detached Instance).
        Sử dụng db.expunge() để object vẫn tồn tại sau khi đóng session.
        """
        try:
            with SessionLocal() as db:
                article = ArticleRepository._get_article_by_id_in_session(db, article_id)
                ArticleRepository._expunge_if_present(db, article)
                return article
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error(f"lấy bài viết ID={article_id}", error)

    @staticmethod
    def recover_stale_processing_articles() -> int:
        """[Startup Recovery] Reset các bài viết bị kẹt ở trạng thái PROCESSING."""
        try:
            with SessionLocal() as db:
                stale_articles = db.query(Article).filter(Article.status == ArticleStatus.PROCESSING).all()
                if not stale_articles:
                    return 0
                for article in stale_articles:
                    article.status = ArticleStatus.GENERATE_FAILED
                    article.error_log = "[SYSTEM_RECOVERY] Reset stale processing state from previous crash."
                db.commit()
                return len(stale_articles)
        except SQLAlchemyError as e:
            logger.warning(f"[STARTUP] DB schema may be outdated or database locked, skipping recovery: {e}")
            return 0

    @staticmethod
    @retry_db_transaction
    def update_processing_state(article_id: int, state: ArticleStatus, error_msg: str = None) -> None:
        """Cập nhật nhanh trạng thái bài viết (VD: Đang xử lý, Lỗi)"""
        try:
            with SessionLocal() as db:
                article = ArticleRepository._get_article_by_id_in_session(db, article_id)
                if article:
                    article.status = state
                    if error_msg:
                        article.error_log = error_msg
                    db.commit()
        except SQLAlchemyError as error:
            db.rollback() 
            ArticleRepository._raise_repository_error(f"cập nhật trạng thái bài viết ID={article_id}", error)

    @staticmethod
    def force_reset_processing_articles(reason: str = "[AUTO-RESET] Emergency stop from UI") -> int:
        """Reset toàn bộ bài đang PROCESSING về GENERATE_FAILED để mở khóa UI ngay lập tức."""
        try:
            with SessionLocal() as db:
                processing_articles = db.query(Article).filter(Article.status == ArticleStatus.PROCESSING).all()
                if not processing_articles:
                    return 0

                for article in processing_articles:
                    previous_log = str(article.error_log or "").strip()
                    article.status = ArticleStatus.GENERATE_FAILED
                    article.error_log = f"{previous_log} | {reason}".strip(" |")

                db.commit()
                return len(processing_articles)
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error("reset trạng thái PROCESSING", error)

    @staticmethod
    @retry_db_transaction
    def save_ai_generated_content(article_id: int, ai_data: Any, language: str | None = None) -> None:
        """Mapping dữ liệu AI (dict hoặc dataclass/object) vào Database Schema."""
        normalized = ArticleRepository._normalize_ai_payload(ai_data)
        try:
            with SessionLocal() as db:
                article = ArticleRepository._get_article_by_id_in_session(db, article_id)
                if article:
                    article.title = normalized["title"]
                    article.meta_description = normalized["meta_description"]
                    article.slug = normalized["slug"]
                    article.content_markdown = normalized["content_markdown"]
                    normalized_language = ArticleRepository._normalize_language_label(language)
                    if normalized_language:
                        article.language = normalized_language
                    article.status = ArticleStatus.GENERATED
                    db.commit()
        except SQLAlchemyError as error:
            db.rollback()
            ArticleRepository._raise_repository_error(f"lưu nội dung AI cho bài viết ID={article_id}", error)

    @staticmethod
    @retry_db_transaction
    def update_article_fields(article_id: int, **fields) -> None:
        """Cập nhật thủ công các field cho bài viết, gồm cả metadata category/language."""
        allowed = {
            "title",
            "meta_description",
            "slug",
            "content_markdown",
            "context",
            "long_tail_keywords",
            "language",
            "category_id",
            "category_name",
        }
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return
        try:
            with SessionLocal() as db:
                article = ArticleRepository._get_article_by_id_in_session(db, article_id)
                if article:
                    for k, v in to_update.items():
                        setattr(article, k, v)
                    db.commit()
        except SQLAlchemyError as error:
            db.rollback()
            ArticleRepository._raise_repository_error(f"cập nhật field bài viết ID={article_id}", error)

    @staticmethod
    def save_seo_scoring(article_id: int, seo_score: int, seo_notes: list[str] | str | None) -> None:
        """Lưu điểm SEO và ghi chú đánh giá cho bài viết."""
        try:
            with SessionLocal() as db:
                article = ArticleRepository._get_article_by_id_in_session(db, article_id)
                if article:
                    article.seo_score = int(seo_score)
                    if isinstance(seo_notes, list):
                        article.seo_notes = json.dumps(seo_notes, ensure_ascii=False)
                    elif isinstance(seo_notes, str):
                        article.seo_notes = seo_notes
                    else:
                        article.seo_notes = ""
                    db.commit()
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error(f"lưu SEO score cho bài viết ID={article_id}", error)

    @staticmethod
    def save_publish_info(article_id: int, wp_post_id: int, wp_post_url: str, category_id: int = None, category_name: str = None) -> Article:
        """Lưu trữ Data Lineage sau khi bắn qua WordPress API"""
        try:
            with SessionLocal() as db:
                article = ArticleRepository._get_article_by_id_in_session(db, article_id)
                if article:
                    article.wp_post_id = wp_post_id
                    article.wp_post_url = wp_post_url
                    if category_id is not None:
                        article.category_id = category_id
                    if category_name:
                        article.category_name = category_name
                    article.status = ArticleStatus.PUBLISHED
                    db.commit()
                    ArticleRepository._expunge_if_present(db, article) # Trả về object đã tách khỏi DB session để UI in ra log
                    return article
            return None
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error(f"lưu thông tin publish cho bài viết ID={article_id}", error)

    @staticmethod
    def get_all_articles_for_sync() -> list[Article]:
        """Lấy toàn bộ bài viết để đồng bộ ra hệ thống ngoài (ví dụ Google Sheets)."""
        try:
            with SessionLocal() as db:
                articles = db.query(Article).order_by(Article.id.asc()).all()
                for article in articles:
                    ArticleRepository._expunge_if_present(db, article)
                return articles
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error("lấy toàn bộ bài viết để đồng bộ", error)

    @staticmethod
    def delete_articles_by_ids(article_ids: list[int]) -> int:
        """Xóa nhiều bài viết theo danh sách ID, trả về số dòng đã xóa."""
        normalized_ids = sorted({int(article_id) for article_id in article_ids if article_id is not None})
        if not normalized_ids:
            return 0

        try:
            with SessionLocal() as db:
                deleted_count = db.query(Article).filter(Article.id.in_(normalized_ids)).delete(
                    synchronize_session=False
                )
                db.commit()
                return int(deleted_count or 0)
        except SQLAlchemyError as error:
            ArticleRepository._raise_repository_error("xóa bài viết theo danh sách ID", error)