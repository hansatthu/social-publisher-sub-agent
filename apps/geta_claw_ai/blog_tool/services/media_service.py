import os
import io
import re
import base64
import mimetypes
from typing import Any
from html import escape
from xml.sax.saxutils import escape as xml_escape
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, PngImagePlugin
from unidecode import unidecode

class MediaService:
    """
    Service Layer: Đảm nhiệm toàn bộ logic xử lý ảnh, Metadata (Exif, XMP), 
    Base64 encoding, và Markdown injection.
    Tách biệt hoàn toàn khỏi UI và Data Access.
    """
    
    # Pre-compile regex để tối ưu Regex Engine Time Complexity
    INLINE_DATA_IMAGE_PATTERN = re.compile(
        r'<img\b[^>]*\bsrc=["\']data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>[^"\']+)["\'][^>]*\balt=["\'](?P<alt>[^"\']*)["\'][^>]*>',
        re.IGNORECASE,
    )

    @staticmethod
    def detect_keyword_language(keyword: str) -> str | None:
        normalized = (keyword or "").strip()
        if not normalized:
            return None

        if re.search(r"[\u4e00-\u9fff]", normalized):
            return "zh"

        if re.search(r"[A-Za-zÀ-ỹ]", normalized):
            return "vi"

        return None

    @classmethod
    def build_lightweight_preview_markdown(cls, content_markdown: str, max_chars: int = 12000) -> str:
        if not content_markdown:
            return ""

        stripped = cls.INLINE_DATA_IMAGE_PATTERN.sub("![inline-image](inline-image-uploaded)", content_markdown)
        if len(stripped) > max_chars:
            return stripped[:max_chars] + "\n\n... (preview truncated)"
        return stripped

    @classmethod
    def extract_inline_image_assets(cls, content_markdown: str) -> list[dict[str, Any]]:
        """Trích các ảnh inline base64 từ markdown để tái sử dụng khi regenerate content."""
        if not content_markdown:
            return []

        assets: list[dict[str, Any]] = []
        for index, match in enumerate(cls.INLINE_DATA_IMAGE_PATTERN.finditer(content_markdown), start=1):
            mime_type = str(match.group("mime") or "image/jpeg").strip().lower()
            base64_data = str(match.group("data") or "").strip()
            alt_text = str(match.group("alt") or "").strip()
            if not base64_data:
                continue

            try:
                image_bytes = base64.b64decode(base64_data, validate=True)
            except Exception:
                continue

            extension = mimetypes.guess_extension(mime_type) or ".jpg"
            if extension == ".jpe":
                extension = ".jpg"

            assets.append(
                {
                    "bytes": image_bytes,
                    "mime_type": mime_type,
                    "file_name": f"inline-image-{index}{extension}",
                    "alt_text": alt_text,
                }
            )

        return assets

    @staticmethod
    def sanitize_filename_base(text: str, keep_unicode: bool = True, fallback: str = "image") -> str:
        """Chuẩn hóa chuỗi thành tên file an toàn."""
        normalized = (text or "").strip()
        if not normalized:
            return fallback

        if not keep_unicode:
            normalized = unidecode(normalized)

        normalized = normalized.replace("_", " ")
        normalized = re.sub(r"[\\/:*?\"<>|]", " ", normalized)
        if not keep_unicode:
            normalized = re.sub(r"[^A-Za-z0-9\s-]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        normalized = normalized.replace(" ", "-")
        normalized = re.sub(r"-+", "-", normalized).strip("-")
        return normalized[:150] if normalized else fallback

    @staticmethod
    def _to_windows_utf16_bytes(text: str) -> bytes:
        return (text or "").encode("utf-16-le") + b"\x00\x00"

    @staticmethod
    def _to_exif_ascii(text: str) -> str:
        if not text:
            return ""
        return str(text).encode("latin-1", "replace").decode("latin-1")

    @staticmethod
    def _to_exif_ascii_fallback(text: str) -> str:
        if not text:
            return ""
        transliterated = unidecode(str(text))
        transliterated = re.sub(r"\s+", " ", transliterated).strip()
        return transliterated.encode("latin-1", "replace").decode("latin-1")

    @staticmethod
    def _is_ascii_text(text: str) -> bool:
        if text is None:
            return True
        try:
            str(text).encode("ascii")
            return True
        except UnicodeEncodeError:
            return False

    @staticmethod
    def _to_exif_unicode_comment(text: str) -> bytes:
        if not text:
            return b""
        # EXIF UserComment uses an 8-byte charset marker followed by the encoded payload.
        return b"UNICODE\x00" + str(text).encode("utf-16-be")

    @staticmethod
    def _build_xmp_packet(details: dict) -> bytes:
        """Đóng gói XMP Metadata cho ảnh WebP/JPEG."""
        title = xml_escape(str(details.get("title") or "").strip())
        subject = xml_escape(str(details.get("subject") or details.get("keywords") or "").strip())
        description = xml_escape(str(details.get("description") or "").strip())
        keywords = xml_escape(str(details.get("keywords") or "").strip())
        author = xml_escape(str(details.get("author") or "").strip())
        copyright_text = xml_escape(str(details.get("copyright") or "").strip())

        xmp = f"""<?xpacket begin=\"﻿\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>
<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">
 <rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">
  <rdf:Description rdf:about=\"\"
   xmlns:dc=\"http://purl.org/dc/elements/1.1/\"
   xmlns:xmpRights=\"http://ns.adobe.com/xap/1.0/rights/\"
   xmlns:photoshop=\"http://ns.adobe.com/photoshop/1.0/\">
   <dc:title><rdf:Alt><rdf:li xml:lang=\"x-default\">{title}</rdf:li></rdf:Alt></dc:title>
   <dc:description><rdf:Alt><rdf:li xml:lang=\"x-default\">{description}</rdf:li></rdf:Alt></dc:description>
   <dc:creator><rdf:Seq><rdf:li>{author}</rdf:li></rdf:Seq></dc:creator>
   <dc:rights><rdf:Alt><rdf:li xml:lang=\"x-default\">{copyright_text}</rdf:li></rdf:Alt></dc:rights>
   <dc:subject><rdf:Bag><rdf:li>{subject}</rdf:li><rdf:li>{keywords}</rdf:li></rdf:Bag></dc:subject>
   <photoshop:AuthorsPosition>{author}</photoshop:AuthorsPosition>
   <xmpRights:Marked>True</xmpRights:Marked>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end=\"w\"?>"""
        return xmp.encode("utf-8")

    @classmethod
    def embed_metadata_into_image_bytes(cls, file_bytes: bytes, file_name: str, details: dict | None = None) -> bytes:
        """
        Gắn chuẩn SEO Metadata vào nhị phân ảnh bằng thư viện Pillow (PIL).
        Trả về bytes đã tiêm.
        """
        if not file_bytes:
            return file_bytes

        details = details or {}
        title = str(details.get("title") or "").strip()
        subject = str(details.get("subject") or details.get("keywords") or title).strip()
        description = str(details.get("description") or "").strip()
        keywords = str(details.get("keywords") or details.get("alt_text") or "").strip()
        author = str(details.get("author") or "").strip()
        copyright_text = str(details.get("copyright") or "").strip()
        
        if not any([title, subject, description, keywords, author, copyright_text]):
            return file_bytes

        extension = os.path.splitext(file_name or "")[1].lower()

        try:
            with Image.open(io.BytesIO(file_bytes)) as image:
                output = io.BytesIO()

                if extension in {".jpg", ".jpeg", ".webp"}:
                    exif = image.getexif()
                    if title:
                        exif[40091] = cls._to_windows_utf16_bytes(title)
                    if subject:
                        exif[40095] = cls._to_windows_utf16_bytes(subject)
                    if description:
                        # Tag 270 (ImageDescription) is commonly treated as ASCII by readers.
                        # Store an ASCII-safe transliteration there to avoid mojibake, while
                        # preserving the original Unicode text in XPComment/UserComment/XMP.
                        exif[270] = (
                            description if cls._is_ascii_text(description) else cls._to_exif_ascii_fallback(description)
                        )
                        exif[40092] = cls._to_windows_utf16_bytes(description)
                        exif[37510] = cls._to_exif_unicode_comment(description)
                    if keywords:
                        exif[40094] = cls._to_windows_utf16_bytes(keywords)
                    if author:
                        exif[40093] = cls._to_windows_utf16_bytes(author)
                        exif[315] = cls._to_exif_ascii(author)
                    if copyright_text:
                        exif[33432] = cls._to_exif_ascii(copyright_text)

                    save_format = "JPEG" if extension in {".jpg", ".jpeg"} else "WEBP"
                    save_kwargs = {"format": save_format, "exif": exif.tobytes()}
                    if save_format == "JPEG":
                        save_kwargs["quality"] = 95
                    if save_format == "WEBP":
                        save_kwargs["xmp"] = cls._build_xmp_packet({
                            "title": title, "subject": subject, "description": description,
                            "keywords": keywords, "author": author, "copyright": copyright_text
                        })
                    image.save(output, **save_kwargs)
                    return output.getvalue()

                if extension == ".png":
                    png_info = PngImagePlugin.PngInfo()
                    if title: png_info.add_text("Title", title)
                    if subject: png_info.add_text("Subject", subject)
                    if description: 
                        png_info.add_text("Description", description)
                        png_info.add_text("Comment", description)
                    if keywords: png_info.add_text("Keywords", keywords)
                    if author: 
                        png_info.add_text("Author", author)
                        png_info.add_text("Artist", author)
                    if copyright_text: png_info.add_text("Copyright", copyright_text)
                    
                    image.save(output, format="PNG", pnginfo=png_info)
                    return output.getvalue()
        except Exception:
            pass # Fallback về bytes ban đầu nếu lỗi thư viện

        return file_bytes

    @staticmethod
    def build_responsive_image_tag(image_bytes: bytes, mime_type: str, file_name: str, custom_alt_text: str | None = None) -> str:
        """Tạo HTML img tag dạng Base64 để nhúng vào Markdown."""
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        alt_text = (custom_alt_text or "").strip() or os.path.splitext(file_name)[0].replace("_", " ").strip() or "hinh-anh"
        safe_alt = escape(alt_text)

        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                width, height = image.size
        except Exception:
            width, height = None, None

        style = "display:block;max-width:100%;width:100%;height:auto !important;aspect-ratio:auto !important;object-fit:contain !important;"
        src = f"data:{mime_type};base64,{image_b64}"

        if width and height:
            return f'<img src="{src}" alt="{safe_alt}" width="{width}" height="{height}" style="{style}" loading="lazy" />'
        return f'<img src="{src}" alt="{safe_alt}" style="{style}" loading="lazy" />'

    @classmethod
    def build_responsive_image_tag_from_upload(cls, image_file, custom_alt_text: str | None = None) -> str:
        image_bytes = image_file.getvalue()
        mime_type = image_file.type or "image/jpeg"
        file_name = getattr(image_file, "name", "image.jpg")
        return cls.build_responsive_image_tag(image_bytes, mime_type, file_name, custom_alt_text)

    @classmethod
    def inject_images_into_markdown(
        cls,
        content_markdown: str,
        uploaded_images,
        max_images: int,
        alt_texts: list[str] | None = None,
    ) -> str:
        if not content_markdown.strip() or not uploaded_images or max_images <= 0:
            return content_markdown

        selected_images = uploaded_images[:max_images]
        paragraphs = [part.strip() for part in content_markdown.split("\n\n") if part.strip()]

        if len(paragraphs) < 2:
            image_blocks = [
                cls.build_responsive_image_tag_from_upload(
                    image_file,
                    custom_alt_text=(alt_texts[idx] if alt_texts and idx < len(alt_texts) else None),
                )
                for idx, image_file in enumerate(selected_images)
            ]
            return content_markdown + "\n\n" + "\n\n".join(image_blocks)

        image_blocks = [
            cls.build_responsive_image_tag_from_upload(
                image_file,
                custom_alt_text=(alt_texts[idx] if alt_texts and idx < len(alt_texts) else None),
            )
            for idx, image_file in enumerate(selected_images)
        ]

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

    @classmethod
    def inject_grouped_images_into_markdown(cls, content_markdown: str, grouped_images: dict[str, list[tuple]]) -> str:
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
            image_blocks = [
                cls.build_responsive_image_tag_from_upload(image_file, custom_alt_text=alt_text)
                for image_file, alt_text in images
            ]
            section_block = "\n\n".join([f"### {group_name}"] + image_blocks)
            group_blocks.append((group_name, section_block))

        if not group_blocks:
            return content_markdown

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
                    candidate_position = max(1, min(len(paragraphs) - 1, idx + 1))
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
                proposed = max(
                    1,
                    min(
                        len(paragraphs) - 1,
                        int(unresolved_index * len(paragraphs) / (unresolved_count + 1)),
                    ),
                )

                if proposed in used_positions:
                    next_slot = proposed
                    while next_slot in used_positions and next_slot < len(paragraphs) - 1:
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

    @classmethod
    def upload_inline_images_and_replace_sources(
        cls,
        content_markdown: str,
        post_index: int,
        build_payload_callback,
        upload_callback,
        max_workers: int = 4,
    ) -> str:
        if not content_markdown:
            return content_markdown

        matches = list(cls.INLINE_DATA_IMAGE_PATTERN.finditer(content_markdown))
        if not matches:
            return content_markdown

        workers = max(1, min(max_workers, len(matches)))

        def _process_match(image_index: int, match):
            mime_type = (match.group("mime") or "").lower().strip()
            base64_data = (match.group("data") or "").strip()
            if not mime_type or not base64_data:
                return None

            try:
                image_bytes = base64.b64decode(base64_data, validate=True)
            except Exception:
                return None

            extension = mimetypes.guess_extension(mime_type) or ".jpg"
            if extension == ".jpe":
                extension = ".jpg"

            unique_index = (post_index * 100) + image_index
            upload_file_name, media_details = build_payload_callback(extension, unique_index)
            prepared_bytes = cls.embed_metadata_into_image_bytes(image_bytes, upload_file_name, media_details)
            source_url = upload_callback(prepared_bytes, upload_file_name, media_details)
            if not source_url:
                return None

            original_tag = match.group(0)
            replaced_tag = re.sub(
                r'src=["\']data:[^"\']+["\']',
                f'src="{source_url}"',
                original_tag,
                count=1,
                flags=re.IGNORECASE,
            )
            return {
                "start": match.start(),
                "end": match.end(),
                "replacement": replaced_tag,
            }

        replacements: list[dict] = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(_process_match, image_index, match): (image_index, match)
                for image_index, match in enumerate(matches)
            }
            for future in as_completed(future_map):
                result = future.result()
                if result:
                    replacements.append(result)

        if not replacements:
            return content_markdown

        updated_content = content_markdown
        for item in sorted(replacements, key=lambda x: x["start"], reverse=True):
            updated_content = updated_content[: item["start"]] + item["replacement"] + updated_content[item["end"] :]

        return updated_content