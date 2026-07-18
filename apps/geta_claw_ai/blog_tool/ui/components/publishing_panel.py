import re
import html
import base64
import mimetypes
from typing import Any, List

import streamlit as st

from services.article_repository import ArticleRepository, RepositoryError
from services.content_service import ContentService
from database.models import ArticleStatus
from services.media_service import MediaService


def _detect_category_language(category_name: str) -> str:
    """Detect category language from name. Tiếng Trung if contains CJK characters, else Tiếng Việt."""
    cjk_pattern = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
    if cjk_pattern.search(category_name):
        return "Tiếng Trung Giản Thể"
    return "Tiếng Việt"


def _filter_categories_by_language(categories: list[dict], article_language: str | None) -> list[dict]:
    """Filter categories to match article language."""
    if not article_language:
        return categories
    
    filtered = []
    for cat in categories:
        cat_lang = _detect_category_language(cat.get("name", ""))
        if cat_lang == article_language:
            filtered.append(cat)
    
    return filtered if filtered else categories  # Fallback: return all if no match


def _build_category_label_map(categories: list[dict]) -> dict[str, dict[str, Any]]:
    return {
        f"{item['name']} | slug: {item.get('slug', '')} (ID:{item['id']})": item
        for item in categories
    }


def _render_publish_panel_styles() -> None:
    st.markdown(
        """
        <style>
        .publish-row-title {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            line-height: 1.25;
            font-weight: 700;
            margin-bottom: 0;
        }
        .publish-row-meta {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-size: 0.78rem;
            opacity: 0.72;
            margin-top: 0.15rem;
        }
        div[data-testid="stFileUploaderDropzoneInstructions"] {
            display: none !important;
        }
        section[data-testid="stFileUploaderDropzone"] {
            min-height: 0 !important;
            padding-top: 0.35rem !important;
            padding-bottom: 0.35rem !important;
        }
        section[data-testid="stFileUploaderDropzone"] p {
            margin: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _extract_inline_image_assets_from_markdown(content_markdown: str) -> list[dict[str, Any]]:
    if not content_markdown:
        return []

    assets: list[dict[str, Any]] = []
    pattern = getattr(MediaService, "INLINE_DATA_IMAGE_PATTERN", None)
    if pattern is None:
        return assets

    for index, match in enumerate(pattern.finditer(content_markdown), start=1):
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


def _inject_raw_blocks_into_markdown(content_markdown: str, blocks: List[str]) -> str:
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
    usable_paragraphs = max(2, faq_start_idx)  # Ensure at least a few points
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


def render_publishing_panel_component(
    *,
    is_locked: bool,
    active_site: str | None,
    orchestrator,
    load_wp_categories_callback,
    build_thumbnail_upload_payload_callback,
    build_inline_image_alt_texts_callback,
    upload_inline_images_and_replace_sources_callback,
) -> None:
    """Render post publishing panel with preview/edit flow."""
    st.subheader("Thêm bài viết mới (Xuất bản lên WP)")

    if "bulk_publish_success" in st.session_state:
        st.success(st.session_state["bulk_publish_success"])
        del st.session_state["bulk_publish_success"]

    if "bulk_publish_errors" in st.session_state:
        st.error("Một số bài đăng thất bại:")
        st.text("\n".join(st.session_state["bulk_publish_errors"][:20]))
        del st.session_state["bulk_publish_errors"]

    if "bulk_publish_links" in st.session_state:
        st.info("Link các bài đã publish thành công:")
        st.markdown("\n".join([f"- {url}" for url in st.session_state["bulk_publish_links"]]))
        del st.session_state["bulk_publish_links"]

    try:
        wp_categories = load_wp_categories_callback()
    except Exception as e:
        wp_categories = []
        st.warning(f"Không đọc được danh mục từ WP Admin: {str(e)}")

    try:
        publishable_options = ArticleRepository.get_publishable_options()
    except RepositoryError as e:
        st.error(str(e))
        return

    selected_publish_list = st.multiselect(
        "Chọn bài viết để đăng hàng loạt",
        options=list(publishable_options.keys()),
        default=[],
        disabled=is_locked,
        help="Mỗi bài sẽ có category và thumbnail riêng trong bảng bên dưới.",
    )

    publish_rows: list[dict[str, Any]] = []

    if selected_publish_list:
        _render_publish_panel_styles()
        st.markdown("### Bảng cấu hình từng bài")
        st.caption("Mỗi dòng có danh mục và thumbnail riêng. Bạn có thể để trống thumbnail nếu không cần ảnh đại diện.")

        header_cols = st.columns([4.0, 3.0, 3.0])
        header_cols[0].markdown("**Bài viết**")
        header_cols[1].markdown("**Danh mục WP**")
        header_cols[2].markdown("**Thumbnail**")

        for index, selected_publish in enumerate(selected_publish_list, start=1):
            article_id = publishable_options[selected_publish]
            try:
                article = ArticleRepository.get_article_by_id(article_id)
            except RepositoryError as e:
                article = None
                st.error(f"{selected_publish}: {str(e)}")

            article_language = getattr(article, "language", None) if article else None
            filtered_wp_categories = _filter_categories_by_language(wp_categories, article_language)
            category_label_map = _build_category_label_map(filtered_wp_categories)
            category_labels = list(category_label_map.keys())
            category_options = ["No options to select"] + category_labels

            category_key = f"publish_category_{article_id}"
            if category_options:
                current_category_value = st.session_state.get(category_key)
                if current_category_value not in category_options:
                    st.session_state[category_key] = category_options[1] if len(category_options) > 1 else category_options[0]

            row_cols = st.columns([4.0, 3.0, 3.0])
            with row_cols[0]:
                article_language_label = article.language or "Chưa gán" if article else "Chưa gán"
                title_text = f"{index}. {selected_publish} | ID:{article_id} | {article_language_label}"
                escaped_title = html.escape(title_text)
                st.markdown(
                    f"<div class='publish-row-title' title='{escaped_title}'>{escaped_title}</div>",
                    unsafe_allow_html=True,
                )
                if article:
                    escaped_meta = html.escape(f"SEO: {article.seo_score if getattr(article, 'seo_score', None) is not None else 'N/A'}")
                    st.markdown(f"<div class='publish-row-meta'>{escaped_meta}</div>", unsafe_allow_html=True)

            with row_cols[1]:
                if category_labels:
                    selected_category_label = st.selectbox(
                        "",
                        category_options,
                        key=category_key,
                        label_visibility="collapsed",
                        disabled=is_locked,
                    )
                else:
                    selected_category_label = "No options to select"
                    st.selectbox(
                        "",
                        ["No options to select"],
                        key=category_key,
                        label_visibility="collapsed",
                        disabled=True,
                    )

            with row_cols[2]:
                thumb_uploader_key = f"publish_thumb_uploader_{article_id}"
                uploaded_thumbnail = st.file_uploader(
                    "",
                    accept_multiple_files=False,
                    type=["png", "jpg", "jpeg", "webp"],
                    disabled=is_locked,
                    key=thumb_uploader_key,
                    label_visibility="collapsed",
                )

            publish_rows.append(
                {
                    "article_id": article_id,
                    "selected_publish": selected_publish,
                    "article": article,
                    "category_label": selected_category_label,
                    "category_map": category_label_map,
                    "thumbnail": uploaded_thumbnail,
                }
            )

        if any((row["category_label"] == "No options to select") for row in publish_rows):
            st.warning("Một số bài chưa có danh mục khả dụng. Hãy chọn lại bài hoặc kiểm tra dữ liệu category từ WP.")

    thumbnail_alt_label = st.selectbox(
        "Cách tạo ALT cho thumbnail",
        options=["AI viết ALT", "Dùng title bài làm ALT", "Keyword + local"],
        index=2,
        disabled=is_locked,
    )
    thumbnail_alt_map = {
        "AI viết ALT": "ai",
        "Dùng title bài làm ALT": "title",
        "Keyword + local": "keyword_local",
    }
    publish_status = st.radio("Trạng thái", ["Draft (Bản nháp)", "Publish (Công khai)"], horizontal=True, disabled=is_locked)
    regenerate_clicked = st.button(
        "Tạo lại content cho các bài đã chọn (giữ ảnh)",
        disabled=is_locked,
        help="Viết lại title/meta/content theo site hiện tại nhưng giữ các ảnh inline đang có trong bài.",
    )

    if regenerate_clicked:
        if not selected_publish_list:
            st.warning("Vui lòng chọn ít nhất một bài viết để tạo lại content.")
            return

        if not active_site:
            st.warning("Vui lòng chọn site trước khi tạo lại content.")
            return

        with st.spinner("Đang viết lại content và giữ ảnh hiện có..."):
            failures: list[str] = []
            updated_count = 0
            progress = st.progress(0)

            for index, selected_publish in enumerate(selected_publish_list):
                article_id = publishable_options[selected_publish]
                try:
                    article = ArticleRepository.get_article_by_id(article_id)
                    if not article:
                        failures.append(f"{selected_publish}: Không tìm thấy bài viết.")
                        progress.progress((index + 1) / len(selected_publish_list))
                        continue

                    existing_assets = _extract_inline_image_assets_from_markdown(article.content_markdown or "")
                    regenerated = orchestrator.agent.generate_article(
                        keyword=article.keyword,
                        context=article.context or "",
                        language=article.language or "Vietnamese",
                        site_name=active_site,
                    )

                    regenerated_content = str(regenerated.get("content_markdown") or "")
                    if existing_assets:
                        alt_texts = build_inline_image_alt_texts_callback(
                            article,
                            existing_assets,
                            article.language or "Tiếng Việt",
                            "AI viết ALT",
                        )
                        image_blocks = [
                            MediaService.build_responsive_image_tag(
                                asset["bytes"],
                                asset["mime_type"],
                                asset["file_name"],
                                custom_alt_text=alt_texts[idx] if idx < len(alt_texts) else asset.get("alt_text") or None,
                            )
                            for idx, asset in enumerate(existing_assets)
                        ]
                        regenerated_content = _inject_raw_blocks_into_markdown(regenerated_content, image_blocks)

                    seo_metadata = regenerated.get("seo_metadata") or {}
                    ArticleRepository.update_article_fields(
                        article_id,
                        title=seo_metadata.get("title", article.title),
                        meta_description=seo_metadata.get("meta_description", article.meta_description),
                        slug=seo_metadata.get("slug", article.slug),
                        content_markdown=regenerated_content,
                    )
                    ArticleRepository.update_processing_state(article_id, ArticleStatus.GENERATED)
                    updated_count += 1
                except Exception as e:
                    failures.append(f"{selected_publish}: {str(e)}")

                progress.progress((index + 1) / len(selected_publish_list))

            if updated_count:
                st.success(f"Đã viết lại content cho {updated_count}/{len(selected_publish_list)} bài. Giữ ảnh inline hiện có.")
            if failures:
                st.session_state["bulk_publish_errors"] = failures
            st.rerun()

    publish_clicked = st.button("Đăng lên Website", type="primary", disabled=is_locked)

    if publish_clicked:
        if not selected_publish_list:
            st.warning("Vui lòng chọn ít nhất một bài viết để đăng.")
            return

        status_val = "draft" if "Draft" in publish_status else "publish"

        if not publish_rows:
            st.warning("Không có dòng cấu hình hợp lệ để đăng.")
            return

        invalid_rows = [row["selected_publish"] for row in publish_rows if row["category_label"] == "No options to select"]
        if invalid_rows:
            st.warning("Vui lòng chọn danh mục cho từng bài trước khi đăng.")
            return

        total_posts = len(publish_rows)

        with st.spinner("Đang đẩy dữ liệu qua WordPress REST API..."):
            success_count = 0
            failed_posts: list[str] = []
            published_links: list[str] = []
            progress = st.progress(0)

            for index, row in enumerate(publish_rows):
                article_id = int(row["article_id"])
                selected_publish = str(row["selected_publish"])
                article = row["article"]
                category_label = str(row["category_label"])
                category = row["category_map"].get(category_label)
                selected_category_id = category["id"] if category else None
                selected_category_name = category["name"] if category else None

                if not article:
                    failed_posts.append(f"{selected_publish}: Không tìm thấy bài viết.")
                    progress.progress((index + 1) / total_posts)
                    continue

                try:
                    thumbnail_bytes = None
                    thumbnail_name = None
                    thumbnail_details = None
                    image_file = row["thumbnail"]
                    if image_file:
                        upload_file_name, media_details = build_thumbnail_upload_payload_callback(
                            article,
                            image_file,
                            0,
                            thumbnail_alt_strategy=thumbnail_alt_map[thumbnail_alt_label],
                        )
                        thumbnail_bytes = image_file.getvalue()
                        thumbnail_name = upload_file_name
                        thumbnail_details = media_details

                    content_markdown_processed = upload_inline_images_and_replace_sources_callback(
                        article.content_markdown,
                        article,
                        index,
                    )

                    is_success, error_message, published_url = orchestrator.publish_single_article(
                        article_id=article_id,
                        status_val=status_val,
                        category_id=selected_category_id,
                        category_name=selected_category_name,
                        thumbnail_bytes=thumbnail_bytes,
                        thumbnail_name=thumbnail_name,
                        thumbnail_details=thumbnail_details,
                        content_markdown_processed=content_markdown_processed,
                    )

                    if is_success:
                        success_count += 1
                        if status_val == "publish" and published_url:
                            published_links.append(published_url)
                    else:
                        failed_posts.append(f"{selected_publish}: {error_message}")
                except Exception as e:
                    failed_posts.append(f"{selected_publish}: {str(e)}")

                progress.progress((index + 1) / total_posts)

            if success_count:
                st.session_state["bulk_publish_success"] = f"Đăng thành công {success_count}/{total_posts} bài viết."
            if failed_posts:
                st.session_state["bulk_publish_errors"] = failed_posts
            if published_links:
                st.session_state["bulk_publish_links"] = published_links
            st.rerun()

    preview_candidates = selected_publish_list if selected_publish_list else list(publishable_options.keys())
    if preview_candidates:
        with st.expander("Xem trước bài viết", expanded=False):
            preview_key = st.selectbox(
                "Chọn bài để xem trước",
                options=preview_candidates,
                key="preview_publish_article",
                disabled=is_locked,
            )
            preview_article_id = publishable_options.get(preview_key)
            if preview_article_id:
                try:
                    preview_article = ArticleRepository.get_article_by_id(preview_article_id)
                    if preview_article:
                        st.caption(
                            f"Ngôn ngữ: {preview_article.language or 'Chưa gán'} | "
                            f"Slug: {preview_article.slug or 'Chưa có'}"
                        )
                        tab_view, tab_edit = st.tabs(["👁️ Xem trước", "✏️ Chỉnh sửa"])

                        with tab_view:
                            st.text_input("Tiêu đề preview", value=preview_article.title or "", disabled=True)
                            st.text_area(
                                "Meta description preview",
                                value=preview_article.meta_description or "",
                                height=80,
                                disabled=True,
                            )
                            render_preview_now = st.checkbox(
                                "Hiển thị nội dung preview",
                                value=False,
                                key=f"preview_render_toggle_{preview_article_id}",
                                disabled=is_locked,
                                help="Tắt mặc định để tránh đơ khi bài có nhiều ảnh base64.",
                            )
                            if render_preview_now:
                                lightweight_markdown = ContentService.build_lightweight_preview_markdown(
                                    preview_article.content_markdown or ""
                                )
                                tab_rendered, tab_markdown = st.tabs(["Nội dung render (light)", "Markdown gốc (light)"])
                                with tab_rendered:
                                    st.markdown(lightweight_markdown, unsafe_allow_html=True)
                                with tab_markdown:
                                    st.code(lightweight_markdown, language="markdown")

                        with tab_edit:
                            edit_title = st.text_input(
                                "Tiêu đề",
                                value=preview_article.title or "",
                                key=f"edit_title_{preview_article_id}",
                                disabled=is_locked,
                            )
                            edit_meta = st.text_area(
                                "Meta description",
                                value=preview_article.meta_description or "",
                                height=80,
                                key=f"edit_meta_{preview_article_id}",
                                disabled=is_locked,
                            )
                            edit_content = st.text_area(
                                "Nội dung (Markdown)",
                                value=preview_article.content_markdown or "",
                                height=500,
                                key=f"edit_content_{preview_article_id}",
                                disabled=is_locked,
                            )
                            if st.button(
                                "💾 Lưu thay đổi",
                                key=f"save_edit_{preview_article_id}",
                                disabled=is_locked,
                            ):
                                try:
                                    ArticleRepository.update_article_fields(
                                        preview_article_id,
                                        title=edit_title,
                                        meta_description=edit_meta,
                                        content_markdown=edit_content,
                                    )
                                    st.success("Đã lưu thay đổi thành công!")
                                    st.rerun()
                                except RepositoryError as e:
                                    st.error(f"Lỗi lưu: {str(e)}")
                    else:
                        st.info("Không tìm thấy dữ liệu preview cho bài viết này.")
                except RepositoryError as e:
                    st.warning(f"Không tải được preview: {str(e)}")