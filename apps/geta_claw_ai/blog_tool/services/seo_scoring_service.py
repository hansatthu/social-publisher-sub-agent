import re
from typing import Any


class SeoScoringService:
    """Rule Engine chấm điểm SEO (Hỗ trợ đa ngôn ngữ Google/Baidu)."""

    LOCAL_TERMS = [
        "mộc bài", "bavet", "xa mát",
        "木牌", "巴域", "下马",
        "geta", "geta group", "in ấn", "in an", "printing", "quảng cáo",
    ]

    TRUST_TERMS = [
        "dịch vụ", "báo giá", "liên hệ", "cam kết", "uy tín", "service",
        "报价", "联系我们", "专业", "服务",
    ]

    @staticmethod
    def _extract_primary_keyword(raw_keyword: str) -> str:
        normalized = (raw_keyword or "").strip()
        if not normalized:
            return ""
        parts = [part.strip() for part in re.split(r"[,;\n\|、，；]+", normalized) if part.strip()]
        return parts[0] if parts else normalized

    @staticmethod
    def _word_count(text: str) -> int:
        if not text:
            return 0
        # [Fix NLP Bug]: Tách riêng các ký tự Latin/số (nhóm bằng dấu +) và từng ký tự CJK (tiếng Trung) riêng lẻ
        tokens = re.findall(r"[A-Za-zÀ-ỹà-ỹ0-9]+|[\u4e00-\u9fff]", text)
        return len(tokens)

    @staticmethod
    def _sentence_count(text: str) -> int:
        if not text:
            return 0
        pieces = [part.strip() for part in re.split(r"[\.!\?。！？\n]+", text) if part.strip()]
        return len(pieces)

    @staticmethod
    def _count_h1_h2(markdown_text: str) -> tuple[int, int]:
        if not markdown_text:
            return 0, 0
        h1_count = len(re.findall(r"(?m)^#\s+", markdown_text))
        h2_count = len(re.findall(r"(?m)^##\s+", markdown_text))
        return h1_count, h2_count

    @staticmethod
    def _count_links(markdown_text: str) -> tuple[int, int]:
        if not markdown_text:
            return 0, 0
        links = re.findall(r"\[[^\]]+\]\(([^\)]+)\)", markdown_text)
        external, internal = 0, 0
        for url in links:
            lower_url = (url or "").strip().lower()
            if lower_url.startswith("http://") or lower_url.startswith("https://"):
                external += 1
            elif lower_url.startswith("/"):
                internal += 1
        return internal, external

    @staticmethod
    def _count_images_and_alts(markdown_text: str) -> tuple[int, int]:
        if not markdown_text:
            return 0, 0
        markdown_images = re.findall(r"!\[([^\]]*)\]\(([^\)]+)\)", markdown_text)
        html_images = re.findall(r"<img\s+[^>]*alt=[\"']([^\"']*)[\"'][^>]*>", markdown_text, flags=re.IGNORECASE)

        total_images = len(markdown_images) + len(html_images)
        valid_alts = len([alt for alt, _ in markdown_images if (alt or "").strip()]) + len(
            [alt for alt in html_images if (alt or "").strip()]
        )
        return total_images, valid_alts

    @classmethod
    def evaluate_article(cls, article: Any) -> dict[str, Any]:
        title = (getattr(article, "title", "") or "").strip()
        meta_description = (getattr(article, "meta_description", "") or "").strip()
        slug = (getattr(article, "slug", "") or "").strip()
        content_markdown = (getattr(article, "content_markdown", "") or "").strip()
        raw_keyword = (getattr(article, "keyword", "") or "").strip()
        language = (getattr(article, "language", "") or "").lower()

        # Xác định Engine mục tiêu (Google vs Baidu)
        is_chinese = "trung" in language or "zh" in language or "chinese" in language

        primary_keyword = cls._extract_primary_keyword(raw_keyword)
        content_lower = content_markdown.lower()
        title_lower = title.lower()
        meta_lower = meta_description.lower()
        keyword_lower = primary_keyword.lower()

        notes: list[str] = []
        score = 0

        # 1. Chiều dài Title (Google: 50-60 | Baidu: 20-35)
        title_len = len(title)
        min_title, max_title = (20, 35) if is_chinese else (45, 65)
        if min_title <= title_len <= max_title and (not keyword_lower or keyword_lower in title_lower):
            score += 10
        elif title_len > 0:
            score += 4
            notes.append(f"Title độ dài chưa tối ưu (Hiện tại: {title_len}, Khuyến nghị: {min_title}-{max_title} ký tự).")
        else:
            notes.append("Thiếu Title SEO.")

        # 2. Chiều dài Meta Description (Google: 120-155 | Baidu: 60-100)
        meta_len = len(meta_description)
        min_meta, max_meta = (60, 100) if is_chinese else (120, 160)
        if min_meta <= meta_len <= max_meta and (not keyword_lower or keyword_lower in meta_lower):
            score += 10
        elif meta_len > 0:
            score += 4
            notes.append(f"Meta Description chưa tối ưu (Hiện tại: {meta_len}, Khuyến nghị: {min_meta}-{max_meta} ký tự).")
        else:
            notes.append("Thiếu Meta Description.")

        # 3. Cấu trúc Heading
        h1_count, h2_count = cls._count_h1_h2(content_markdown)
        if h1_count <= 1 and 3 <= h2_count <= 8:
            score += 10
        elif h2_count >= 2:
            score += 6
            notes.append("Heading chưa đạt chuẩn (cần 1 H1 và 3-8 H2).")
        else:
            score += 2
            notes.append("Thiếu cấu trúc thẻ Heading rõ ràng.")

        # 4. Keyword Density (Baidu ưu tiên Exact Match hơi cao hơn một chút)
        words = cls._word_count(content_markdown)
        keyword_occurrences = content_lower.count(keyword_lower) if keyword_lower else 0
        density = (keyword_occurrences / max(words, 1)) * 100
        min_density, max_density = (1.5, 5.0) if is_chinese else (0.5, 3.0)

        if keyword_occurrences >= 3 and min_density <= density <= max_density:
            score += 15
        elif keyword_occurrences >= 1:
            score += 8
            notes.append(f"Mật độ keyword là {density:.1f}% (Khuyến nghị: {min_density}% - {max_density}%).")
        else:
            score += 2
            notes.append("Keyword xuất hiện quá ít, bot không hiểu được chủ đề chính.")

        # 5. Slug URL (Baidu ưu tiên slug ngắn)
        if slug and len(slug) <= 80 and " " not in slug:
            score += 5
        elif slug:
            score += 2
            notes.append("Slug nên ngắn gọn (<80 ký tự) và ngăn cách bằng dấu gạch ngang.")

        # 6. Chiều dài bài viết
        min_words = 600 if is_chinese else 900
        if words >= min_words:
            score += 15
        elif words >= min_words * 0.7:
            score += 8
            notes.append(f"Bài hơi ngắn ({words} chữ).")
        else:
            score += 3
            notes.append(f"Content quá mỏng (cần > {min_words} chữ).")

        # 7. Internal / External Links
        internal_links, external_links = cls._count_links(content_markdown)
        if internal_links >= 1 and external_links >= 1:
            score += 10
        elif internal_links + external_links >= 1:
            score += 5
            notes.append("Bổ sung đủ internal & external link để tăng luồng Crawl cho Bot.")
        else:
            notes.append("Chưa có bất kỳ link nào trong bài.")

        # 8. Images & Alt Texts
        image_count, alt_count = cls._count_images_and_alts(content_markdown)
        if image_count >= 1 and alt_count == image_count:
            score += 10
        elif image_count >= 1:
            score += 5
            notes.append("Baidu/Google Bot không hiểu ảnh nếu thiếu thẻ ALT.")
        else:
            notes.append("Cần tối thiểu 1 hình ảnh minh họa cho bài.")

        # 9. Readability
        sentence_count = cls._sentence_count(content_markdown)
        avg_words = words / max(sentence_count, 1)
        # Tiếng Trung câu có xu hướng ngắn hơn về mặt ký tự
        good_avg = (5, 20) if is_chinese else (8, 25)
        if good_avg[0] <= avg_words <= good_avg[1]:
            score += 10
        else:
            score += 5
            notes.append(f"Readability kém. Trung bình {avg_words:.1f} chữ/câu (Tối ưu: {good_avg[0]}-{good_avg[1]}).")

        # 10. EEAT / Local Trust Signals
        local_hit = any(term in content_lower or term in title_lower for term in cls.LOCAL_TERMS)
        trust_hit = any(term in content_lower for term in cls.TRUST_TERMS)
        if local_hit and trust_hit:
            score += 5
        elif local_hit:
            score += 3
            notes.append("Có tín hiệu Địa phương (Local) nhưng thiếu Trust signal (Báo giá, Uy tín...).")
        else:
            notes.append("Chưa có tín hiệu Local/Brand EEAT phù hợp với site đang viết.")

        return {"score": max(0, min(100, int(round(score)))), "notes": notes}
