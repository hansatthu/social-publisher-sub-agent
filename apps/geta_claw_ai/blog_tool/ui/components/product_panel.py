import queue
import threading
import time
from typing import Any

import pandas as pd
import streamlit as st

from ui.components.wc_status import render_wc_result_messages


def render_product_automation_panel_component(
    *,
    is_locked: bool,
    wc_publisher,
    orchestrator,
    global_task_state: dict[str, Any],
    reset_wc_result_state_callback,
    load_wc_product_categories_callback,
    read_products_input_file_callback,
    parse_csv_like_values_callback,
    build_auto_product_id_callback,
    detect_language_suffix_for_product_callback,
    append_sku_suffix_if_missing_callback,
    find_existing_skus_safe_callback,
    attach_local_images_to_rows_callback,
    attach_wp_media_to_rows_callback,
    sanitize_wc_error_message_callback,
    max_wc_workers: int,
    max_wc_media_workers: int,
    max_wc_media_retries: int,
    max_wc_media_retry_delay_seconds: float,
) -> None:
    is_geta_catalog = "innhanhgeta.com" in (orchestrator.wp_publisher.site_url or "")
    is_zh_supported = "mocbaibavet.com" in (orchestrator.wp_publisher.site_url or "")

    st.subheader(f"Product Automation ({'Geta Catalog' if is_geta_catalog else 'WooCommerce'})")
    if not wc_publisher and not is_geta_catalog:
        st.warning("Thiếu cấu hình WooCommerce trong .env.")
        return

    # Define columns dynamically
    if is_zh_supported:
        allowed_columns = [
            "name", "description", "short_description",
            "name_zh", "short_desc_zh", "desc_zh",
            "sku", "regular_price", "stock_quantity",
            "categories", "category_zh",
            "local_images", "wp_media",
        ]
    else:
        allowed_columns = [
            "name", "description", "short_description",
            "sku", "regular_price", "stock_quantity",
            "categories",
            "local_images", "wp_media",
        ]

    with st.expander("Xem chuẩn cột CSV", expanded=True):
        st.markdown("- Bắt buộc: `name`")
        st.markdown("- Tùy chọn: " + ", ".join(f"`{col}`" for col in allowed_columns if col != "name"))
        st.markdown("- `product_id` được hệ thống tự sinh nội bộ khi upload, không cần nhập")
        st.markdown("- `regular_price`: có thể để trống (phù hợp B2B/cần ẩn giá)")
        st.markdown("- `categories`: ngăn cách bằng dấu phẩy (ví dụ: `Áo thun, Đồ Nam`)")
        st.markdown("- Mode `Local images`: dùng cột `local_images` để nhập tên file local (jpg/jpeg/png/webp) đã chọn ở uploader")
        st.markdown("- Mode `WP Media`: dùng cột `wp_media` để nhập URL ảnh đã có sẵn hoặc media ID (số)")
        st.markdown("- Với CSV thô: nếu một ô có nhiều giá trị chứa dấu phẩy thì đặt trong nháy kép, ví dụ: `\"a.jpg,b.jpg\"`")
        st.markdown("- Với bảng chỉnh sửa trong UI: chỉ cần nhập `a.jpg,b.jpg` hoặc `a.jpg;b.jpg` (không cần nháy kép)")

        sample_csv = (
            "name,description,short_description,name_zh,short_desc_zh,desc_zh,sku,regular_price,stock_quantity,categories,category_zh,local_images,wp_media\n"
            "Bật lửa họa tiết Vân đá & Cẩm thạch,Dòng bật lửa họa tiết vân đá và cẩm thạch tinh tế.,Bật lửa họa tiết vân đá sang trọng.,,,,LGT-STONE-02-VI,199000,30,disposable-lighters,,bat-lua-stone-01.jpg,\n"
            "Bật lửa họa tiết Vân đá & Cẩm thạch,,,石纹与大理石纹艺术打火机,大理石纹高颜值打火机，质感出众。,精选高质感石纹与大理石图案，外观大气端庄。,LGT-STONE-02,,,disposable-lighters,一次性打火机,,\"2456,stone-02-zh.jpg\"\n"
            "Bật lửa phổ thông (Loại tốt),Dòng bật lửa nhựa phổ thông bền bỉ.,Bật lửa phổ thông giá tốt.,,,,LGT-STD-05-VI,159000,50,disposable-lighters,,\"bat-lua-std-01.jpg,bat-lua-std-02.jpg\",\n"
        )
        sample_csv_path = "data/woocommerce_products_sample.csv"
        try:
            with open(sample_csv_path, "r", encoding="utf-8") as sample_file:
                sample_csv = sample_file.read()
        except Exception:
            pass
        st.download_button(
            "Tải CSV mẫu",
            data=sample_csv,
            file_name="woocommerce_products_sample.csv",
            mime="text/csv",
            disabled=is_locked,
        )

    with st.expander("Hướng dẫn nhập trực tiếp trên bảng", expanded=False):
        st.markdown("- Chọn nguồn dữ liệu **Nhập trực tiếp trên bảng** rồi điền từng dòng sản phẩm.")
        st.markdown("- Cột bắt buộc phải có dữ liệu: `name`.")
        st.markdown("- `product_id` sẽ được hệ thống tự sinh nội bộ khi upload.")
        st.markdown("- Cột `regular_price` có thể để trống nếu bạn muốn ẩn giá (B2B).")
        st.markdown("- Cột `categories` dùng dropdown từ danh mục đã có trên WordPress (nếu tải được danh mục).")
        st.markdown("- Chọn mode ảnh: `Local images` hoặc `WP Media`.")
        st.markdown("- Nếu mode `Local images`: dùng cột `local_images` (tên file) + chọn file ở uploader.")
        st.markdown("- Nếu mode `WP Media`: dùng cột `wp_media` (URL hoặc media ID), không cần upload file local.")
        st.markdown("- Ví dụ nhanh:")
        st.code(
            "name=Ao khoac gio | regular_price= | sku=AK-009 | "
            "categories=Thoi trang Nam | "
            "local_images=ao-khoac-1.jpg,ao-khoac-2.jpg | wp_media=1234,https://site/wp-content/uploads/a.jpg"
        )

    should_show_wc_result = bool(
        global_task_state.get("wc_last_result")
        or global_task_state.get("wc_success_links")
        or global_task_state.get("wc_failed_rows")
        or global_task_state.get("success_msg")
    )
    if should_show_wc_result:
        render_wc_result_messages(
            global_task_state=global_task_state,
            reset_callback=reset_wc_result_state_callback,
        )

    if is_locked and global_task_state.get("feature") == "woocommerce":
        st.info("⏳ Hệ thống đang đẩy sản phẩm lên WooCommerce. UI đã được khóa an toàn.")
        progress_val = global_task_state["completed"] / max(1, global_task_state["total"])
        st.progress(progress_val)
        st.caption(f"Tiến độ: {progress_val * 100:.1f}%")
        st.write(f"Đã đẩy: {global_task_state['completed']} / {global_task_state['total']} sản phẩm")
        if st.button("🛑 Dừng khẩn cấp upload sản phẩm", type="primary"):
            global_task_state["should_stop"] = True
            st.warning("Đã gửi tín hiệu dừng, luồng sẽ hủy các tác vụ chờ.")
        time.sleep(1.2)
        st.rerun()
        return

    if is_locked:
        st.info("⏳ Hệ thống đang xử lý tính năng khác. Vui lòng đợi hoàn tất.")
        return

    input_mode = st.radio(
        "Nguồn dữ liệu sản phẩm",
        ["Upload CSV", "Nhập trực tiếp trên bảng"],
        horizontal=True,
        key="wc_input_mode",
        disabled=is_locked,
    )

    wp_product_categories: list[str] = []
    try:
        wp_categories = load_wc_product_categories_callback()
        category_tokens: set[str] = set()
        for item in (wp_categories or []):
            name = str(item.get("name", "") or "").strip()
            slug = str(item.get("slug", "") or "").strip()
            if name:
                category_tokens.add(name)
            if slug:
                category_tokens.add(slug)
        wp_product_categories = sorted(category_tokens, key=lambda value: value.lower())
    except Exception:
        wp_product_categories = []

    normalized_df = pd.DataFrame([])
    if input_mode == "Upload CSV":
        uploaded_file = st.file_uploader("Tải file sản phẩm (CSV/XLSX)", type=["csv", "xlsx"], disabled=is_locked)
        if uploaded_file is None:
            st.info("Hãy upload CSV/XLSX để bắt đầu bước Validate & Preview.")
            return

        try:
            products_df, detected_encoding = read_products_input_file_callback(uploaded_file)
        except Exception as e:
            st.error(f"Lỗi đọc CSV: {e}")
            return

        if detected_encoding == "xlsx":
            st.caption("Đã đọc file Excel `.xlsx` (không qua decode CSV).")
        else:
            st.caption(f"Encoding CSV đã nhận: `{detected_encoding}`")

        normalized_df = products_df.copy()

        object_columns = normalized_df.select_dtypes(include=["object"]).columns.tolist()
        if object_columns:
            text_blob = "\n".join(
                str(value)
                for column_name in object_columns
                for value in normalized_df[column_name].fillna("").astype(str).tolist()[:1000]
            )
            if text_blob:
                question_ratio = text_blob.count("?") / max(1, len(text_blob))
                if question_ratio > 0.03:
                    st.warning(
                        "Dữ liệu có nhiều ký tự '?'. Khả năng cao file CSV đã mất Unicode từ bước export. "
                        "Khuyến nghị: upload file `.xlsx` gốc hoặc export lại dạng CSV UTF-8."
                    )
    else:
        st.caption("Nhập dữ liệu trực tiếp vào bảng bên dưới. Có thể thêm/xóa dòng tự do.")
        if "wc_manual_products_df" not in st.session_state or set(st.session_state["wc_manual_products_df"].columns) != set(allowed_columns):
            st.session_state["wc_manual_products_df"] = pd.DataFrame(
                [{col: "" for col in allowed_columns}]
            )

        data_editor_kwargs = {
            "num_rows": "dynamic",
            "width": "stretch",
            "hide_index": True,
            "key": "wc_manual_products_editor",
            "disabled": is_locked,
        }

        if wp_product_categories:
            category_options = [""] + sorted(set(wp_product_categories), key=lambda value: value.lower())
            data_editor_kwargs["column_config"] = {
                "categories": st.column_config.SelectboxColumn(
                    "categories",
                    options=category_options,
                    help="Chọn category đã có trên WordPress.",
                )
            }
            st.caption("Cột `categories` đang dùng dropdown lấy từ WordPress.")
        else:
            st.caption("Không tải được danh mục WordPress, cột `categories` giữ chế độ nhập tay.")

        edited_df = st.data_editor(
            st.session_state["wc_manual_products_df"].reset_index(drop=True),
            **data_editor_kwargs,
        )
        st.session_state["wc_manual_products_df"] = edited_df.reset_index(drop=True).copy()
        normalized_df = edited_df.reset_index(drop=True).copy()

        if normalized_df.empty:
            st.info("Hãy nhập ít nhất 1 dòng sản phẩm để bắt đầu Validate & Preview.")
            return

    normalized_df.columns = [str(col).strip().lower() for col in normalized_df.columns]

    legacy_column_aliases = {
        "product_name_zh": "name_zh",
        "product_short_desc_zh": "short_desc_zh",
        "product_desc_zh": "desc_zh",
        "category_name_zh": "category_zh",
    }
    for old_name, new_name in legacy_column_aliases.items():
        if old_name in normalized_df.columns and new_name not in normalized_df.columns:
            normalized_df = normalized_df.rename(columns={old_name: new_name})

    required_columns = ["name"]
    missing_columns = [col for col in required_columns if col not in normalized_df.columns]
    if missing_columns:
        st.error(
            "CSV thiếu cột bắt buộc: "
            + ", ".join(missing_columns)
            + ". Cần tối thiểu: name."
        )
        return

    for optional_col in allowed_columns:
        if optional_col not in normalized_df.columns:
            normalized_df[optional_col] = ""

    preferred_order = allowed_columns
    extra_columns = [column for column in normalized_df.columns if column not in preferred_order]
    normalized_df = normalized_df[preferred_order + extra_columns]

    drop_input_only_columns = ["images", "product_id"]
    for column_name in drop_input_only_columns:
        if column_name in normalized_df.columns:
            normalized_df = normalized_df.drop(columns=[column_name])

    text_columns = [
        "name",
        "description",
        "short_description",
        "name_zh",
        "short_desc_zh",
        "desc_zh",
        "sku",
        "regular_price",
        "categories",
        "category_zh",
        "category_desc_zh",
        "local_images",
        "wp_media",
    ]
    for column_name in text_columns:
        if column_name in normalized_df.columns:
            normalized_df[column_name] = (
                normalized_df[column_name]
                .fillna("")
                .astype(str)
                .replace({"nan": "", "None": "", "null": ""})
            )

    if input_mode == "Upload CSV":
        st.caption("Bạn có thể chỉnh dữ liệu CSV trước khi Validate & Upload.")
        csv_editor_kwargs = {
            "num_rows": "fixed",
            "width": "stretch",
            "hide_index": True,
            "key": "wc_csv_products_editor",
            "disabled": is_locked,
        }

        if wp_product_categories:
            category_options = [""] + sorted(set(wp_product_categories), key=lambda value: value.lower())
            csv_editor_kwargs["column_config"] = {
                "categories": st.column_config.SelectboxColumn(
                    "categories",
                    options=category_options,
                    help="Chọn category đã có trên WordPress.",
                )
            }
            st.caption("Cột `categories` trong CSV đang dùng dropdown từ WordPress.")
        else:
            st.caption("Không tải được danh mục WordPress, cột `categories` trong CSV giữ chế độ nhập tay.")

        normalized_df = st.data_editor(normalized_df, **csv_editor_kwargs).copy()

    image_source_mode = st.radio(
        "Nguồn ảnh sản phẩm",
        ["Local images", "WP Media"],
        horizontal=True,
        key="wc_image_source_mode",
        disabled=is_locked,
        help="Local images: upload file local. WP Media: dùng URL hoặc media ID đã có sẵn trên WordPress.",
    )

    uploaded_local_images = []
    if image_source_mode == "Local images":
        uploaded_local_images = st.file_uploader(
            "Ảnh local cho sản phẩm (tùy chọn, có thể chọn nhiều file)",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="wc_local_images_uploader",
            disabled=is_locked,
            help="Nếu dùng cột local_images, nhập đúng tên file (ví dụ: ao-thun-1.jpg). Hệ thống sẽ tự upload và gắn URL vào images.",
        )
    else:
        st.caption("Mode WP Media đang bật: dùng cột `wp_media` (URL hoặc media ID), không upload local file.")

    cleaned_df = normalized_df.copy()
    cleaned_df["name"] = cleaned_df["name"].astype(str).str.strip()
    cleaned_df["regular_price"] = cleaned_df["regular_price"].astype(str).str.strip()
    cleaned_df = cleaned_df[~cleaned_df["name"].str.lower().isin(["", "nan", "none", "null"])]

    invalid_rows_count = len(normalized_df) - len(cleaned_df)
    if invalid_rows_count > 0:
        st.warning(
            f"Đã tự loại {invalid_rows_count} dòng rỗng/không hợp lệ ở cột name."
        )

    st.caption("Preview 10 dòng đầu sau khi parse CSV")
    st.dataframe(cleaned_df.head(10), width="stretch", hide_index=True)

    if cleaned_df.empty:
        st.warning("Không còn dòng hợp lệ để upload sau bước kiểm định.")
        return

    publish_status = st.radio(
        "Trạng thái xuất bản",
        ["draft", "publish"],
        horizontal=True,
        key="wc_default",
        disabled=is_locked,
    )
    auto_suffix_sku = False
    enable_zh_update_existing = False
    if is_zh_supported:
        auto_suffix_sku = st.checkbox(
            "Tự động thêm hậu tố ngôn ngữ vào SKU (VI/ZH)",
            value=True,
            disabled=is_locked,
            help="Giúp tránh trùng SKU giữa dòng tiếng Việt và tiếng Trung. Ví dụ: LGT-001 -> LGT-001-VI hoặc LGT-001-ZH.",
        )
        enable_zh_update_existing = st.checkbox(
            "Dữ liệu tiếng Trung: cập nhật vào sản phẩm có sẵn theo SKU",
            value=True,
            disabled=is_locked,
            help=(
                "Nếu dòng dữ liệu chứa tiếng Trung, tool sẽ tìm sản phẩm hiện có theo SKU (bao gồm biến thể base/-VI/-ZH) "
                "và cập nhật meta ZH thay vì tạo product mới."
            ),
        )

    btn_label = "🚀 Đẩy lên Geta Catalog" if is_geta_catalog else "🚀 Đẩy lên WooCommerce"
    if st.button(btn_label, type="primary", disabled=is_locked):
        has_any_zh_payload = False
        for row in cleaned_df.itertuples(index=False):
            row_name_zh = str(getattr(row, "name_zh", "") or "").strip()
            row_short_zh = str(getattr(row, "short_desc_zh", "") or "").strip()
            row_desc_zh = str(getattr(row, "desc_zh", "") or "").strip()
            if row_name_zh or row_short_zh or row_desc_zh:
                has_any_zh_payload = True
                break

        effective_zh_update_existing = bool(enable_zh_update_existing or has_any_zh_payload)
        if has_any_zh_payload and not enable_zh_update_existing:
            st.warning(
                "Phát hiện dữ liệu tiếng Trung trong file. Tool tự bật chế độ cập nhật ZH theo SKU "
                "để đảm bảo đổ đúng vào các ô ZH trên WordPress."
            )

        valid_rows: list[dict] = []
        for idx, row in enumerate(cleaned_df.itertuples(index=False), start=1):
            auto_product_id = build_auto_product_id_callback(
                name=getattr(row, "name", ""),
                sku=getattr(row, "sku", ""),
                row_number=idx,
            )
            row_dict = {
                "product_id": auto_product_id,
                "name": getattr(row, "name", ""),
                "description": getattr(row, "description", ""),
                "short_description": getattr(row, "short_description", ""),
                "name_zh": getattr(row, "name_zh", ""),
                "short_desc_zh": getattr(row, "short_desc_zh", ""),
                "desc_zh": getattr(row, "desc_zh", ""),
                "sku": getattr(row, "sku", ""),
                "regular_price": getattr(row, "regular_price", ""),
                "stock_quantity": getattr(row, "stock_quantity", ""),
                "categories": getattr(row, "categories", ""),
                "category_zh": getattr(row, "category_zh", ""),
                "category_desc_zh": getattr(row, "category_desc_zh", ""),
                "images": "",
                "local_images": getattr(row, "local_images", ""),
                "wp_media": getattr(row, "wp_media", ""),
                "__update_zh_existing": effective_zh_update_existing,
                "__csv_row": idx,
            }
            valid_rows.append(row_dict)

        if effective_zh_update_existing:
            missing_sku_for_zh_rows: list[str] = []
            for row_data in valid_rows:
                has_row_zh = any(
                    str(row_data.get(field, "") or "").strip()
                    for field in ["name_zh", "short_desc_zh", "desc_zh"]
                )
                if not has_row_zh:
                    continue
                row_sku = str(row_data.get("sku", "") or "").strip()
                if not row_sku:
                    row_number = int(row_data.get("__csv_row", 0))
                    product_name = str(row_data.get("name", "")).strip() or f"row-{row_number}"
                    missing_sku_for_zh_rows.append(
                        f"Dòng {row_number} - {product_name}: thiếu SKU để cập nhật dữ liệu ZH vào sản phẩm có sẵn."
                    )

            if missing_sku_for_zh_rows:
                st.error("Có dòng tiếng Trung chưa có SKU. Không thể cập nhật ZH theo sản phẩm đích.")
                st.text("\n".join(missing_sku_for_zh_rows[:200]))
                return

        if auto_suffix_sku:
            modified_sku_count = 0
            for row_data in valid_rows:
                current_sku = str(row_data.get("sku", "") or "").strip()
                if not current_sku:
                    continue
                lang_suffix = detect_language_suffix_for_product_callback(row_data)
                normalized_sku = append_sku_suffix_if_missing_callback(current_sku, lang_suffix)
                if normalized_sku != current_sku:
                    modified_sku_count += 1
                row_data["sku"] = normalized_sku

            if modified_sku_count > 0:
                st.info(f"Đã tự thêm hậu tố ngôn ngữ cho {modified_sku_count} SKU trước bước validate.")

        sku_rows: dict[str, list[int]] = {}
        for row_data in valid_rows:
            sku_val = str(row_data.get("sku", "") or "").strip()
            if not sku_val:
                continue
            sku_rows.setdefault(sku_val, []).append(int(row_data.get("__csv_row", 0)))

        duplicate_sku_rows = {sku: rows for sku, rows in sku_rows.items() if len(rows) > 1}
        if duplicate_sku_rows:
            duplicate_lines = [
                f"SKU '{sku}' bị trùng ở các dòng: {', '.join(str(row_no) for row_no in row_numbers)}"
                for sku, row_numbers in duplicate_sku_rows.items()
            ]
            st.error(
                "Phát hiện SKU trùng trong file upload. WooCommerce yêu cầu SKU duy nhất cho mỗi sản phẩm. "
                "Vui lòng chỉnh lại SKU trước khi chạy."
            )
            st.text("\n".join(duplicate_lines[:200]))
            return

        sku_values = [str(row_data.get("sku", "") or "").strip() for row_data in valid_rows]
        sku_values = [sku for sku in sku_values if sku]
        if sku_values:
            try:
                with st.spinner("Đang validate SKU đã tồn tại trên WooCommerce..."):
                    existing_sku_map = find_existing_skus_safe_callback(sku_values)
            except Exception as sku_validate_error:
                st.error(f"Không validate được SKU với WooCommerce: {sku_validate_error}")
                return

            if existing_sku_map:
                if effective_zh_update_existing:
                    st.warning(
                        "Phát hiện SKU đã tồn tại trên WooCommerce. Vì bạn đang bật chế độ cập nhật dữ liệu tiếng Trung, "
                        "tool sẽ tiếp tục và cố gắng cập nhật vào sản phẩm có sẵn theo SKU."
                    )

                existing_lines: list[str] = []
                for sku_key, product in existing_sku_map.items():
                    product_id = product.get("id")
                    product_name = str(product.get("name", "") or "").strip()
                    product_link = str(product.get("permalink", "") or "").strip()
                    product_status = str(product.get("status", "") or "").strip()
                    line = f"SKU '{sku_key}' đã tồn tại"
                    if product_id:
                        line += f" | ID: {product_id}"
                    if product_name:
                        line += f" | Tên: {product_name}"
                    if product_status:
                        line += f" | Status: {product_status}"
                    if product_link:
                        line += f" | Link: {product_link}"
                    existing_lines.append(line)

                if not effective_zh_update_existing:
                    st.error(
                        "Phát hiện SKU đã tồn tại trên WooCommerce. Dừng xử lý trước bước upload ảnh để tránh tốn data."
                    )
                    st.text("\n".join(existing_lines[:200]))
                    return

                st.info("SKU đã tồn tại (sẽ dùng để cập nhật ZH nếu là dòng tiếng Trung):")
                st.text("\n".join(existing_lines[:200]))

        if image_source_mode == "Local images":
            has_local_image_refs = any(parse_csv_like_values_callback(row_data.get("local_images")) for row_data in valid_rows)
            if has_local_image_refs and not uploaded_local_images:
                st.error("Phát hiện cột local_images nhưng bạn chưa chọn file ảnh local ở uploader.")
                return

            if has_local_image_refs:
                try:
                    local_image_progress = st.progress(0)
                    local_image_status = st.empty()

                    def on_local_image_progress(done: int, total: int) -> None:
                        percent = int((done / max(1, total)) * 100)
                        local_image_progress.progress(percent)
                        local_image_status.caption(f"Đang upload ảnh local lên WordPress Media: {done}/{total} file")

                    valid_rows, local_image_errors = attach_local_images_to_rows_callback(
                        valid_rows,
                        uploaded_local_images,
                        progress_callback=on_local_image_progress,
                        max_workers=max_wc_media_workers,
                        max_retries=max_wc_media_retries,
                        retry_delay_seconds=max_wc_media_retry_delay_seconds,
                    )
                    local_image_progress.empty()
                    local_image_status.empty()

                    if local_image_errors:
                        missing_file_errors = [error for error in local_image_errors if str(error).startswith("MISSING_FILE |")] 
                        upload_failed_errors = [error for error in local_image_errors if str(error).startswith("UPLOAD_FAILED |")] 

                        if missing_file_errors:
                            st.error("Dữ liệu local_images chưa khớp file upload. Vui lòng kiểm tra lại:")
                            st.text("\n".join(missing_file_errors[:100]))

                        if upload_failed_errors:
                            st.error(
                                "Upload ảnh local lên WordPress bị timeout/kết nối không ổn định. "
                                f"Tool đã tự retry {max_wc_media_retries} lần nhưng vẫn thất bại ở một số file:"
                            )
                            st.text("\n".join(upload_failed_errors[:100]))

                        return
                except Exception as upload_error:
                    st.error(f"Lỗi upload ảnh local: {upload_error}")
                    return

        has_wp_media_refs = any(parse_csv_like_values_callback(row_data.get("wp_media")) for row_data in valid_rows)
        if has_wp_media_refs:
            try:
                wp_media_progress = st.progress(0)
                wp_media_status = st.empty()

                def on_wp_media_progress(done: int, total: int) -> None:
                    percent = int((done / max(1, total)) * 100)
                    wp_media_progress.progress(percent)
                    wp_media_status.caption(f"Đang xử lý WP Media cho sản phẩm: {done}/{total} dòng")

                valid_rows, wp_media_errors = attach_wp_media_to_rows_callback(
                    valid_rows,
                    progress_callback=on_wp_media_progress,
                )
                wp_media_progress.empty()
                wp_media_status.empty()
            except Exception as wp_media_error:
                st.error(f"Lỗi xử lý wp_media: {wp_media_error}")
                return

            if wp_media_errors:
                st.error("Dữ liệu wp_media chưa hợp lệ. Vui lòng kiểm tra lại URL/media ID:")
                st.text("\n".join(wp_media_errors[:100]))
                return

        total_products = len(valid_rows)

        global_task_state["is_running"] = True
        global_task_state["should_stop"] = False
        global_task_state["completed"] = 0
        global_task_state["total"] = total_products
        global_task_state["success"] = 0
        global_task_state["errors"] = []
        global_task_state["feature"] = "woocommerce"
        global_task_state["success_msg"] = ""
        global_task_state["wc_success_links"] = []
        global_task_state["wc_failed_rows"] = []
        global_task_state["wc_last_result"] = {
            "status": "running",
            "total": total_products,
            "started_at": time.time(),
        }

        def background_wc_worker() -> None:
            total_jobs = len(valid_rows)
            worker_count = min(max_wc_workers, total_jobs) if total_jobs > 0 else 1

            job_queue = queue.Queue()
            for row_data in valid_rows:
                job_queue.put(row_data)

            success_count = 0
            success_links: list[str] = []
            failed_rows: list[str] = []

            result_lock = threading.Lock()

            def wc_worker_thread():
                nonlocal success_count
                while not job_queue.empty():
                    if global_task_state.get("should_stop", False):
                        break

                    try:
                        row_data = job_queue.get_nowait()
                    except queue.Empty:
                        break

                    row_number = int(row_data.get("__csv_row", 0))
                    product_name = str(row_data.get("name", "")).strip() or f"row-{row_number}"

                    try:
                        is_success, message, product_url = orchestrator.publish_woocommerce_product(
                            row_data=row_data,
                            status_val=publish_status,
                        )
                        with result_lock:
                            if is_success:
                                success_count += 1
                                if product_url:
                                    link_msg = f"Dòng {row_number} - {product_name}: {product_url}"
                                else:
                                    link_msg = f"Dòng {row_number} - {product_name}: (không có permalink trả về)"
                                success_links.append(link_msg)
                            else:
                                safe_message = sanitize_wc_error_message_callback(message)
                                failed_rows.append(f"Dòng {row_number} - {product_name}: {safe_message}")
                            global_task_state["completed"] += 1

                    except Exception as e:
                        with result_lock:
                            safe_error = sanitize_wc_error_message_callback(str(e))
                            failed_rows.append(f"Dòng {row_number} - {product_name}: {safe_error}")
                            global_task_state["completed"] += 1
                    finally:
                        job_queue.task_done()

            threads = []
            for _ in range(worker_count):
                t = threading.Thread(target=wc_worker_thread, daemon=True)
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            if global_task_state.get("should_stop", False):
                failed_rows.append("🚫 Luồng upload sản phẩm bị dừng bởi người dùng.")

            failed_count = len(failed_rows)
            global_task_state["success"] = success_count
            global_task_state["success_msg"] = (
                f"Đã xử lý xong {total_jobs} sản phẩm | "
                f"Thành công: {success_count} | Thất bại: {failed_count}."
            )
            global_task_state["errors"] = failed_rows
            global_task_state["wc_success_links"] = success_links
            global_task_state["wc_failed_rows"] = failed_rows
            global_task_state["wc_last_result"] = {
                "status": "done",
                "total": total_jobs,
                "success": success_count,
                "failed": failed_count,
                "finished_at": time.time(),
            }
            global_task_state["is_running"] = False

        threading.Thread(target=background_wc_worker, daemon=True).start()
        st.rerun()