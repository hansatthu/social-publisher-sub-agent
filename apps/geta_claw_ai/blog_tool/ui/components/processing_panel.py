import queue
import threading
import time
from typing import Any

import streamlit as st

from services.article_repository import ArticleRepository, RepositoryError
from ui.components.generate_status import render_generate_result_messages
from ui.components.post_dialogs import clear_language_confirm_state, render_language_confirm_dialog
from ui.components.post_language import detect_keyword_lang_from_option, render_selected_keyword_lang_summary


def render_processing_panel_component(
    *,
    is_locked: bool,
    agent,
    orchestrator,
    task_manager,
    active_site: str | None,
    load_wp_media_items_callback,
    apply_images_to_ai_output_callback,
    alt_strategy_map: dict[str, str],
    language_prompt_map: dict[str, str],
    max_generate_workers: int,
) -> None:
    st.subheader("Xử lý bài viết")

    current_state = task_manager.get_snapshot()

    if not is_locked and current_state["feature"] == "generate":
        render_generate_result_messages(current_state=current_state, task_manager=task_manager)

    try:
        processable_options = ArticleRepository.get_processable_options()
    except RepositoryError as e:
        st.error(str(e))
        return

    selected_option_list = st.multiselect(
        "Chọn bài viết để viết hàng loạt (PENDING/GENERATE_FAILED)",
        options=list(processable_options.keys()),
        default=[],
        disabled=is_locked,
    )

    render_selected_keyword_lang_summary(selected_option_list)

    post_image_source_mode = st.radio(
        "Nguồn ảnh chèn bài",
        ["Upload local", "WP Media (đã có sẵn)"],
        horizontal=True,
        key="post_image_source_mode",
        disabled=is_locked,
        help="Upload local: upload như cũ. WP Media: chọn ảnh có sẵn trên WordPress để tránh tạo file trùng.",
    )

    selected_article_ids = {
        selected_option: processable_options[selected_option]
        for selected_option in selected_option_list
    }

    images_by_source_article: dict[int, list[Any]] = {}
    wp_media_items: list[dict[str, Any]] = []

    assignment_mode = st.radio(
        "Cách gán ảnh cho bài",
        ["Theo từng bài (thủ công)", "Tự chia từ kho ảnh chung"],
        horizontal=True,
        key="post_image_assignment_mode",
        disabled=is_locked,
    )

    if post_image_source_mode == "WP Media (đã có sẵn)" and selected_option_list:
        try:
            wp_media_items = load_wp_media_items_callback()
        except Exception as media_error:
            wp_media_items = []
            st.warning(f"Không tải được danh sách WP Media: {media_error}")

    if selected_option_list:
        media_map = {item["label"]: item for item in wp_media_items}

        if assignment_mode == "Theo từng bài (thủ công)":
            st.markdown("### Ảnh theo từng bài")
            st.caption("Mỗi dòng là một bài. Bạn có thể chọn số lượng ảnh khác nhau cho từng bài.")

            for index, selected_option in enumerate(selected_option_list, start=1):
                source_article_id = int(selected_article_ids[selected_option])
                st.markdown(f"**{index}. {selected_option}**")

                if post_image_source_mode == "Upload local":
                    uploader_key = f"post_images_for_{source_article_id}"
                    uploaded_images = st.file_uploader(
                        f"Upload ảnh cho bài #{index}",
                        accept_multiple_files=True,
                        type=["png", "jpg", "jpeg", "webp"],
                        disabled=is_locked,
                        key=uploader_key,
                    )
                    images_by_source_article[source_article_id] = list(uploaded_images or [])
                else:
                    selected_media_labels = st.multiselect(
                        f"Chọn ảnh WP Media cho bài #{index}",
                        options=list(media_map.keys()),
                        default=[],
                        key=f"post_wp_media_for_{source_article_id}",
                        disabled=is_locked,
                        help="Hệ thống sẽ chèn URL ảnh trực tiếp vào bài.",
                    )
                    images_by_source_article[source_article_id] = [
                        str(media_map[label]["url"])
                        for label in selected_media_labels
                        if label in media_map
                    ]

                st.caption(f"Đã chọn {len(images_by_source_article[source_article_id])} ảnh")

        else:
            st.markdown("### Kho ảnh chung")
            st.caption("Upload/chọn một lần, hệ thống tự chia ảnh theo số lượng bạn đặt cho mỗi bài.")

            auto_images_per_article = st.number_input(
                "Số ảnh cho mỗi bài",
                min_value=0,
                max_value=10,
                value=3,
                step=1,
                disabled=is_locked,
                key="post_auto_images_per_article",
            )

            shared_pool: list[Any] = []

            if post_image_source_mode == "Upload local":
                shared_pool = list(
                    st.file_uploader(
                        "Upload kho ảnh dùng chung",
                        accept_multiple_files=True,
                        type=["png", "jpg", "jpeg", "webp"],
                        disabled=is_locked,
                        key="post_images_shared_pool",
                    )
                    or []
                )
            else:
                selected_media_labels = st.multiselect(
                    "Chọn kho ảnh từ WP Media",
                    options=list(media_map.keys()),
                    default=[],
                    key="post_wp_media_shared_pool",
                    disabled=is_locked,
                    help="Hệ thống sẽ chèn URL ảnh trực tiếp vào bài.",
                )
                shared_pool = [
                    str(media_map[label]["url"])
                    for label in selected_media_labels
                    if label in media_map
                ]

            post_count = len(selected_option_list)
            per_post = int(auto_images_per_article)
            required_total = post_count * per_post

            st.caption(
                f"Đã chọn {len(shared_pool)} ảnh trong kho chung. Cần {required_total} ảnh cho {post_count} bài "
                f"({per_post} ảnh/bài)."
            )

            if per_post == 0:
                for selected_option in selected_option_list:
                    source_article_id = int(selected_article_ids[selected_option])
                    images_by_source_article[source_article_id] = []
            elif not shared_pool:
                for selected_option in selected_option_list:
                    source_article_id = int(selected_article_ids[selected_option])
                    images_by_source_article[source_article_id] = []
            else:
                if len(shared_pool) < required_total:
                    st.warning(
                        "Số ảnh trong kho chung ít hơn nhu cầu. Hệ thống sẽ quay vòng ảnh để đủ số lượng cho mỗi bài."
                    )

                cursor = 0
                pool_size = len(shared_pool)
                for selected_option in selected_option_list:
                    source_article_id = int(selected_article_ids[selected_option])
                    assigned_images: list[Any] = []
                    for _ in range(per_post):
                        assigned_images.append(shared_pool[cursor % pool_size])
                        cursor += 1
                    images_by_source_article[source_article_id] = assigned_images

                with st.expander("Xem kết quả tự chia ảnh", expanded=False):
                    for index, selected_option in enumerate(selected_option_list, start=1):
                        source_article_id = int(selected_article_ids[selected_option])
                        st.caption(
                            f"{index}. {selected_option}: {len(images_by_source_article.get(source_article_id, []))} ảnh"
                        )
    elif post_image_source_mode == "WP Media (đã có sẵn)":
        st.caption("Hãy chọn bài viết trước để gán ảnh WP Media theo từng dòng.")

    if post_image_source_mode == "WP Media (đã có sẵn)" and selected_option_list and not wp_media_items:
        st.caption("Chưa có dữ liệu WP Media hoặc không đủ quyền đọc thư viện ảnh.")

    alt_strategy_label = st.selectbox(
        "Cách tạo ALT và Tên file Ảnh", options=["AI viết (Câu hoàn chỉnh max 14 từ)", "Dùng title bài", "Keyword + local"], index=0, disabled=is_locked
    )

    language_label = st.selectbox(
        "Ngôn ngữ cho tất cả bài được chọn",
        options=["Tự động phát hiện (Theo từ khóa)", "Tiếng Việt", "Tiếng Trung Giản Thể"],
        index=0,
        disabled=is_locked,
    )

    def start_generate_jobs(force_single_language: bool = False) -> None:
        if not selected_option_list:
            st.warning("Vui lòng chọn ít nhất một bài viết.")
            return

        generation_jobs: list[dict[str, Any]] = []

        target_lang_code = "vi" if language_label == "Tiếng Việt" else ("zh" if language_label == "Tiếng Trung Giản Thể" else "auto")
        mismatch_options: list[str] = []

        for selected_option in selected_option_list:
            detected_lang = detect_keyword_lang_from_option(selected_option)
            if target_lang_code != "auto" and detected_lang and detected_lang != target_lang_code:
                mismatch_options.append(selected_option)

        if mismatch_options and not force_single_language:
            st.session_state["generate_lang_confirm_needed"] = True
            st.session_state["generate_lang_confirm_label"] = language_label
            st.session_state["generate_lang_confirm_mismatch_count"] = len(mismatch_options)
            st.session_state["generate_lang_confirm_mismatch_preview"] = mismatch_options[:5]
            st.rerun()
            return

        for selected_option in selected_option_list:
            source_article_id = selected_article_ids[selected_option]

            if language_label == "Tự động phát hiện (Theo từ khóa)":
                detected_lang = detect_keyword_lang_from_option(selected_option)
                row_lang_label = "Tiếng Trung Giản Thể" if detected_lang == "zh" else "Tiếng Việt"
            else:
                row_lang_label = language_label

            generation_jobs.append(
                {
                    "article_id": source_article_id,
                    "source_article_id": source_article_id,
                    "language_label": row_lang_label,
                    "language_prompt": language_prompt_map[row_lang_label],
                    "display_label": selected_option,
                }
            )

        total_posts = len(generation_jobs)
        if total_posts <= 0:
            st.warning("Không có tác vụ generate hợp lệ để chạy.")
            return

        task_manager.update(
            is_running=True,
            should_stop=False,
            completed=0,
            total=total_posts,
            success=0,
            errors=[],
            feature="generate",
            success_msg="",
            success_ids=[],
            failed_ids=[],
        )

        if "global_cancel_event" not in st.session_state:
            st.session_state["global_cancel_event"] = threading.Event()
        else:
            st.session_state["global_cancel_event"].clear()

        def background_generate_worker(jobs: list[dict], cancel_event: threading.Event):
            job_queue = queue.Queue()
            for job in jobs:
                job_queue.put(job)

            def worker_thread():
                while not job_queue.empty() and not cancel_event.is_set():
                    try:
                        job = job_queue.get_nowait()
                    except queue.Empty:
                        break

                    source_article_id = int(job["source_article_id"])
                    job_language_label = str(job["language_label"])
                    display_label = str(job["display_label"])

                    def process_ai_output_images(ai_output, article, src_id=source_article_id, lang_label=job_language_label):
                        image_count_for_article = len(images_by_source_article.get(src_id, []))
                        safe_images_count = min(image_count_for_article, 10)
                        return apply_images_to_ai_output_callback(
                            ai_output,
                            article,
                            images_by_source_article.get(src_id, []),
                            safe_images_count,
                            lang_label,
                            False,
                            alt_strategy_map[alt_strategy_label],
                        )

                    try:
                        is_success, message = orchestrator.generate_single_article(
                            article_id=int(job["article_id"]),
                            language_label=job_language_label,
                            language_prompt=str(job["language_prompt"]),
                            site_name=active_site,
                            ai_output_processor_callback=process_ai_output_images,
                            cancel_event=cancel_event,
                        )
                        task_manager.increment(success=is_success)
                        current_article_id = int(job["article_id"])
                        if is_success:
                            task_manager.append_success_id(current_article_id)
                        else:
                            task_manager.append_failed_id(current_article_id)
                            task_manager.append_error(message)
                    except Exception as e:
                        task_manager.increment(success=False)
                        task_manager.append_failed_id(int(job["article_id"]))
                        task_manager.append_error(f"{display_label}: {str(e)}")
                    finally:
                        job_queue.task_done()

            threads = []
            worker_count = min(max_generate_workers, total_posts)
            for _ in range(worker_count):
                t = threading.Thread(target=worker_thread, daemon=True)
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            final_state = task_manager.get_snapshot()
            if cancel_event.is_set():
                task_manager.append_error("🚫 Luồng đã bị người dùng dừng khẩn cấp.")

            task_manager.update(
                is_running=False,
                success_msg=f"Đã hoàn thành Generate {final_state['success']}/{final_state['total']} bài.",
            )

        clear_language_confirm_state()
        threading.Thread(
            target=background_generate_worker,
            args=(generation_jobs, st.session_state["global_cancel_event"]),
            daemon=True,
        ).start()
        st.rerun()

    if st.session_state.get("generate_lang_confirm_needed", False):
        render_language_confirm_dialog(
            language_label=language_label,
            start_generate_jobs_callback=start_generate_jobs,
        )

    current_state = task_manager.get_snapshot()

    try:
        db_processing = ArticleRepository.has_processing_articles()
    except Exception:
        db_processing = False

    is_locked = current_state["is_running"] or db_processing or is_locked

    if is_locked and current_state["feature"] == "generate":
        st.info("⏳ AI đang trong tiến trình Generate. Các tính năng khác đã bị khóa an toàn.")

        progress_val = current_state["completed"] / max(1, current_state["total"])
        st.progress(progress_val)
        st.write(f"Đã xử lý: {current_state['completed']} / {current_state['total']} bài")

        if st.button("🛑 Dừng Generate Khẩn Cấp", type="primary"):
            if "global_cancel_event" in st.session_state:
                st.session_state["global_cancel_event"].set()
            task_manager.update(should_stop=True)
            st.warning("Đã gửi tín hiệu dừng khẩn cấp đến các Workers. Hệ thống đang nhả tài nguyên, vui lòng chờ...")

        time.sleep(1.5)
        st.rerun()
    elif is_locked:
        st.info(
            "⏳ Phát hiện bài viết đang ở trạng thái PROCESSING trong Database. "
            "UI tạm khóa để tránh thao tác chồng chéo khi hệ thống đang generate."
        )
        if st.button("🔄 Kiểm tra lại trạng thái xử lý"):
            st.rerun()

    else:
        if st.button("Viết bài", type="primary", disabled=is_locked):
            start_generate_jobs(force_single_language=False)