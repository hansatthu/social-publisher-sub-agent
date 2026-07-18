from typing import Any

import streamlit as st


def render_post_media_picker(is_locked: bool, load_wp_media_items_callback) -> tuple[str, list[Any], list[str]]:
    post_image_source_mode = st.radio(
        "Nguồn ảnh chèn bài",
        ["Upload local", "WP Media (đã có sẵn)"],
        horizontal=True,
        key="post_image_source_mode",
        disabled=is_locked,
        help="Upload local: upload như cũ. WP Media: chọn ảnh có sẵn trên WordPress để tránh tạo file trùng.",
    )

    uploaded_images: list[Any] = []
    selected_wp_media_urls: list[str] = []

    if post_image_source_mode == "Upload local":
        if "post_images_uploader_nonce" not in st.session_state:
            st.session_state["post_images_uploader_nonce"] = 0

        uploader_col, clear_col = st.columns([12, 1])
        with clear_col:
            # Align icon button with uploader dropzone (avoid sticking to the label row)
            st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
            if st.button(
                "🗑️",
                key="clear_post_uploaded_images_btn",
                help="Loại bỏ tất cả ảnh đã chọn",
                disabled=is_locked,
                use_container_width=True,
            ):
                st.session_state["post_images_uploader_nonce"] = int(
                    st.session_state.get("post_images_uploader_nonce", 0)
                ) + 1
                st.rerun()

        with uploader_col:
            uploader_key = f"post_images_uploader_{int(st.session_state.get('post_images_uploader_nonce', 0))}"
            uploaded_images = st.file_uploader(
                "Chọn hình ảnh để chèn vào bài",
                accept_multiple_files=True,
                type=["png", "jpg", "webp"],
                disabled=is_locked,
                key=uploader_key,
            )
    else:
        try:
            wp_media_items = load_wp_media_items_callback()
        except Exception as media_error:
            wp_media_items = []
            st.warning(f"Không tải được danh sách WP Media: {media_error}")

        media_map = {item["label"]: item for item in wp_media_items}
        selected_media_labels = st.multiselect(
            "Chọn ảnh từ WP Media",
            options=list(media_map.keys()),
            default=[],
            disabled=is_locked,
            help="Bạn có thể chọn lại các ảnh đã upload trước đó, hệ thống sẽ chèn URL trực tiếp vào bài.",
        )
        selected_wp_media_urls = [str(media_map[label]["url"]) for label in selected_media_labels if label in media_map]
        if not wp_media_items:
            st.caption("Chưa có dữ liệu WP Media hoặc không đủ quyền đọc thư viện ảnh.")

    return post_image_source_mode, uploaded_images, selected_wp_media_urls
