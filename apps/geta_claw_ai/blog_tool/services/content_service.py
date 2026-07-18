import re
import base64
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Any, Dict, List

from services.media_service import MediaService

class ContentService:
    """
    Service Layer: Xử lý các thao tác liên quan đến Markdown nội dung,
    bao gồm thuật toán tiêm (inject) ảnh vào bài viết và upload ảnh bất đồng bộ (Concurrent I/O).
    """

    @staticmethod
    def build_lightweight_preview_markdown(content_markdown: str, max_chars: int = 12000) -> str:
        """Tạo bản preview rút gọn cho Markdown (chống đơ UI khi render ảnh base64)."""
        if not content_markdown:
            return ""
        stripped = MediaService.INLINE_DATA_IMAGE_PATTERN.sub("![inline-image](inline-image-uploaded)", content_markdown)
        if len(stripped) > max_chars:
            return stripped[:max_chars] + "\n\n... (preview truncated)"
        return stripped

    @staticmethod
    def inject_images_into_markdown(
        content_markdown: str,
        uploaded_images: List[Any],
        max_images: int,
        alt_texts: List[str] | None = None,
    ) -> str:
        """Thuật toán phân bổ đều hình ảnh vào các đoạn văn (Paragraphs) trong Markdown."""
        if not content_markdown.strip() or not uploaded_images or max_images <= 0:
            return content_markdown

        selected_images = uploaded_images[:max_images]
        image_blocks = []
        for idx, image_file in enumerate(selected_images):
            image_bytes = image_file.getvalue()
            mime_type = getattr(image_file, "type", "image/jpeg")
            file_name = getattr(image_file, "name", f"image_{idx}.jpg")
            custom_alt = alt_texts[idx] if alt_texts and idx < len(alt_texts) else None
            
            img_tag = MediaService.build_responsive_image_tag(
                image_bytes=image_bytes, 
                mime_type=mime_type, 
                file_name=file_name, 
                custom_alt_text=custom_alt
            )
            image_blocks.append(img_tag)

        return ContentService.inject_raw_blocks_into_markdown(content_markdown, image_blocks)

    @staticmethod
    def inject_raw_blocks_into_markdown(content_markdown: str, blocks: List[str]) -> str:
        """Chèn các block HTML/Markdown có sẵn vào bài viết theo cùng thuật toán phân bổ."""
        if not content_markdown.strip() or not blocks:
            return content_markdown

        paragraphs = [part.strip() for part in content_markdown.split("\n\n") if part.strip()]

        # Fallback nếu bài viết quá ngắn
        if len(paragraphs) < 2:
            return content_markdown + "\n\n" + "\n\n".join(blocks)

        # Thuật toán rải vị trí (O(N) Complexity)
        total_paragraphs = len(paragraphs)
        faq_start_idx = total_paragraphs
        for i, paragraph in enumerate(paragraphs):
            lower_p = paragraph.lower()
            if lower_p.startswith("##") and ("faq" in lower_p or "câu hỏi" in lower_p or "问答" in lower_p or "常见问题" in lower_p):
                faq_start_idx = i
                break

        # Calculate insertion positions only before the FAQ section
        usable_paragraphs = max(2, faq_start_idx) # Ensure at least a few points
        insert_positions = {
            max(1, min(usable_paragraphs - 1, int((index + 1) * usable_paragraphs / (len(blocks) + 1))))
            for index in range(len(blocks))
        }
        sorted_positions = sorted(insert_positions)

        # Xử lý va chạm vị trí (Collision handling)
        while len(sorted_positions) < len(blocks):
            added = False
            for candidate in range(1, usable_paragraphs):
                if candidate not in insert_positions:
                    insert_positions.add(candidate)
                    sorted_positions = sorted(insert_positions)
                    added = True
                    if len(sorted_positions) == len(blocks):
                        break
            if not added:
                break

        # Render kết quả
        result_parts: list[str] = []
        block_cursor = 0
        for idx, paragraph in enumerate(paragraphs):
            result_parts.append(paragraph)
            paragraph_index_1_based = idx + 1
            if block_cursor < len(sorted_positions) and paragraph_index_1_based == sorted_positions[block_cursor]:
                result_parts.append(blocks[block_cursor])
                block_cursor += 1

        while block_cursor < len(blocks):
            result_parts.append(blocks[block_cursor])
            block_cursor += 1

        return "\n\n".join(result_parts)

    @classmethod
    def inject_grouped_images_into_markdown(cls, content_markdown: str, grouped_images: Dict[str, List[tuple]]) -> str:
        """Thuật toán phân bổ hình ảnh theo Context/Group (Heading Matching)."""
        if not content_markdown.strip() or not grouped_images:
            return content_markdown

        paragraphs = [part.strip() for part in content_markdown.split("\n\n") if part.strip()]
        if len(paragraphs) < 2:
            flat_images = [img for images in grouped_images.values() for img, _ in images]
            flat_alts = [alt for images in grouped_images.values() for _, alt in images]
            return cls.inject_images_into_markdown(content_markdown, flat_images, len(flat_images), alt_texts=flat_alts)

        group_blocks: list[tuple[str, str]] = []
        for group_name, images in grouped_images.items():
            if not images:
                continue
            
            image_blocks = []
            for image_file, alt_text in images:
                img_bytes = image_file.getvalue()
                mime_type = getattr(image_file, "type", "image/jpeg")
                file_name = getattr(image_file, "name", "image.jpg")
                tag = MediaService.build_responsive_image_tag(img_bytes, mime_type, file_name, alt_text)
                image_blocks.append(tag)
                
            section_block = "\n\n".join([f"### {group_name}"] + image_blocks)
            group_blocks.append((group_name, section_block))

        if not group_blocks:
            return content_markdown

        faq_start_idx = len(paragraphs)
        for i, paragraph in enumerate(paragraphs):
            lower_p = paragraph.lower()
            if lower_p.startswith("##") and ("faq" in lower_p or "câu hỏi" in lower_p or "问答" in lower_p or "常见问题" in lower_p):
                faq_start_idx = i
                break

        usable_paragraphs = max(2, faq_start_idx)
        insertion_map: dict[int, list[str]] = {}
        used_positions: set[int] = set()
        unresolved_blocks: list[tuple[str, str]] = []

        for group_name, block in group_blocks:
            group_name_lower = group_name.lower().strip()
            token_candidates = [token for token in re.split(r"\s+", group_name_lower) if len(token) >= 3]

            matched_position = None
            for idx, paragraph in enumerate(paragraphs):
                paragraph_lower = paragraph.lower()
                is_heading = paragraph_lower.startswith("#")
                if not is_heading:
                    continue

                token_match = any(token in paragraph_lower for token in token_candidates) if token_candidates else False
                direct_match = group_name_lower and group_name_lower in paragraph_lower
                if token_match or direct_match:
                    candidate_position = max(1, min(usable_paragraphs - 1, idx + 1))
                    if candidate_position not in used_positions:
                        matched_position = candidate_position
                        break

            if matched_position is None:
                unresolved_blocks.append((group_name, block))
            else:
                insertion_map.setdefault(matched_position, []).append(block)
                used_positions.add(matched_position)

        if unresolved_blocks:
            unresolved_count = len(unresolved_blocks)
            for unresolved_index, (_, block) in enumerate(unresolved_blocks, start=1):
                proposed = max(1, min(usable_paragraphs - 1, int(unresolved_index * usable_paragraphs / (unresolved_count + 1))))
                if proposed in used_positions:
                    next_slot = proposed
                    while next_slot in used_positions and next_slot < usable_paragraphs - 1:
                        next_slot += 1
                    if next_slot in used_positions:
                        next_slot = proposed
                        while next_slot in used_positions and next_slot > 1:
                            next_slot -= 1
                    proposed = next_slot

                insertion_map.setdefault(proposed, []).append(block)
                used_positions.add(proposed)

        result_parts: list[str] = []
        for idx, paragraph in enumerate(paragraphs):
            result_parts.append(paragraph)
            position = idx + 1
            if position in insertion_map:
                result_parts.extend(insertion_map[position])

        return "\n\n".join(result_parts)

    @staticmethod
    def inject_wp_media_urls_into_markdown(
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
            : img_block
            for index, img_block in enumerate(image_blocks)
        }

        result_parts = []
        for i, p in enumerate(paragraphs):
            result_parts.append(p)
            if i in insert_positions:
                result_parts.append(insert_positions[i])

        return "\n\n".join(result_parts)

    @staticmethod
    def upload_inline_images_concurrently(
        content_markdown: str,
        article: Any,
        post_index: int,
        payload_builder_callback: Callable,
        upload_callback: Callable,
        max_workers: int = 5
    ) -> str:
        """
        [DSA Optimization] Tối ưu I/O Bất đồng bộ bằng ThreadPoolExecutor.
        Sử dụng kỹ thuật Reverse String Replacement để tránh lệch Index khi thao tác trên Markdown.
        """
        if not content_markdown:
            return content_markdown

        matches = list(MediaService.INLINE_DATA_IMAGE_PATTERN.finditer(content_markdown))
        if not matches:
            return content_markdown

        # 1. Pipeline: Data Extraction
        upload_tasks = {}
        for image_index, match in enumerate(matches):
            mime_type = (match.group("mime") or "").lower().strip()
            base64_data = (match.group("data") or "").strip()
            if not mime_type or not base64_data:
                continue

            try:
                image_bytes = base64.b64decode(base64_data, validate=True)
            except Exception:
                continue

            extension = mimetypes.guess_extension(mime_type) or ".jpg"
            if extension == ".jpe":
                extension = ".jpg"

            unique_index = (post_index * 100) + image_index
            
            # Injection logic: Gọi UI Callback để lấy tên file an toàn và Metadata
            try:
                alt_text = match.group("alt").strip()
            except (IndexError, AttributeError):
                alt_text = None
            
            upload_file_name, media_details = payload_builder_callback(article, extension, unique_index, alt_text)
            
            # Transformation: Tiêm Metadata (XMP/Exif) bằng MediaService
            prepared_bytes = MediaService.embed_metadata_into_image_bytes(
                image_bytes,
                upload_file_name,
                media_details,
            )

            upload_tasks[image_index] = {
                "match": match,
                "bytes": prepared_bytes,
                "file_name": upload_file_name,
                "details": media_details
            }

        if not upload_tasks:
            return content_markdown

        # 2. Pipeline: Concurrent API Calls
        results = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(upload_tasks))) as executor:
            future_to_index = {
                executor.submit(
                    upload_callback,
                    task["bytes"],
                    task["file_name"],
                    details=task["details"]
                ): index for index, task in upload_tasks.items()
            }

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    media_info = future.result()
                    results[index] = media_info.get("source_url")
                except Exception as e:
                    print(f"Lỗi upload concurrent ảnh {index}: {e}")
                    results[index] = None

        # 3. Pipeline: Data Reconstruction (Reverse String Replacement)
        updated_content = content_markdown
        for index in sorted(results.keys(), reverse=True):
            source_url = results[index]
            if not source_url:
                continue

            match = upload_tasks[index]["match"]
            original_tag = match.group(0)
            replaced_tag = re.sub(
                r'src=["\']data:[^"\']+["\']',
                f'src="{source_url}"',
                original_tag,
                count=1,
                flags=re.IGNORECASE,
            )

            # Do cắt chuỗi từ dưới lên, index phía trước được bảo toàn
            start, end = match.start(), match.end()
            updated_content = updated_content[:start] + replaced_tag + updated_content[end:]

        return updated_content