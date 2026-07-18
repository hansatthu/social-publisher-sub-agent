import queue
import threading
import time
from typing import Any
import re
from unidecode import unidecode
import streamlit as st

from services.article_repository import ArticleRepository, RepositoryError
from database.models import ArticleStatus

def render_auto_pilot_panel_component(
    *,
    is_locked: bool,
    agent,
    orchestrator,
    task_manager,
    active_site: str | None,
    sheets,
    alt_strategy_map: dict[str, str],
    language_prompt_map: dict[str, str],
    max_generate_workers: int,
    apply_images_to_ai_output_callback,
) -> None:
    st.subheader("🚀 1-Click Auto Pilot")
    st.markdown("Tự động hóa toàn bộ quy trình: Tạo từ khóa -> Tạo bài viết -> Chèn ảnh -> Đăng lên WordPress.")

    if not active_site:
        st.warning("Vui lòng chọn site ở Sidebar trước khi chạy Auto Pilot.")
        return

    # Khôi phục state
    current_state = task_manager.get_snapshot()
    if not is_locked and current_state.get("feature") == "auto_pilot":
        if current_state.get("success_msg"):
            st.success(current_state["success_msg"])
        if current_state.get("errors"):
            st.error("Một số lỗi xảy ra:")
            st.text("\n".join(current_state["errors"][:20]))

    if is_locked and current_state.get("feature") == "auto_pilot":
        st.info("⏳ Auto Pilot đang chạy...")
        progress_val = current_state["completed"] / max(1, current_state["total"])
        st.progress(progress_val)
        st.write(f"Tiến độ: {current_state['completed']} / {current_state['total']}")
        st.write(f"Trạng thái hiện tại: {current_state.get('current_step', 'Đang xử lý...')}")
        
        if st.button("🛑 Dừng Khẩn Cấp", type="primary"):
            if "global_cancel_event" in st.session_state:
                st.session_state["global_cancel_event"].set()
            task_manager.update(should_stop=True)
            st.warning("Đã gửi tín hiệu dừng. Vui lòng chờ...")
        
        time.sleep(1.5)
        st.rerun()
        return
    elif is_locked:
        st.info("⏳ Hệ thống đang xử lý tác vụ khác. Vui lòng chờ.")
        return

    # Form nhập liệu
    with st.container(border=True):
        topic = st.text_input("Chủ đề muốn viết", placeholder="Ví dụ: in túi giấy, bảng hiệu quảng cáo...")
        
        col1, col2 = st.columns(2)
        with col1:
            num_articles = st.number_input("Số lượng bài muốn tạo", min_value=1, max_value=50, value=5, step=1)
            language = st.selectbox("Ngôn ngữ", ["Tiếng Việt", "Tiếng Trung Giản Thể"])
            thumbnail_alt = st.selectbox("Cách tạo ALT cho ảnh", ["AI viết ALT", "Dùng title bài", "Keyword + local"], index=2)
            
        with col2:
            num_images = st.number_input("Số ảnh mỗi bài", min_value=0, max_value=10, value=3, step=1)
            try:
                from ui.app import load_wp_categories_cached
                wp_categories = load_wp_categories_cached(site_name=active_site)
                
                # Lọc danh mục theo ngôn ngữ
                from ui.components.publishing_panel import _filter_categories_by_language, _build_category_label_map
                filtered_wp_categories = _filter_categories_by_language(wp_categories, language)
                category_options = _build_category_label_map(filtered_wp_categories)
                
                category_label = st.selectbox("Danh mục đăng bài (WP)", options=list(category_options.keys()) if category_options else ["Không có danh mục"])
            except Exception as e:
                st.warning(f"Lỗi tải danh mục WP: {str(e)}")
                category_options = {}
                category_label = "Không có danh mục"

        st.markdown("**Upload kho ảnh dùng chung**")
        uploaded_images = st.file_uploader(
            "Hệ thống sẽ tự động phân bổ ảnh cho các bài viết. Nếu thiếu ảnh, sẽ tự quay vòng (lặp lại) ảnh đã upload.",
            accept_multiple_files=True,
            type=["png", "jpg", "jpeg", "webp"]
        )

    if st.button("🚀 Bắt Đầu Auto Pilot", type="primary", use_container_width=True):
        if not topic.strip():
            st.warning("Vui lòng nhập chủ đề.")
            return
            
        if num_images > 0 and not uploaded_images:
            st.warning("Vui lòng upload ảnh hoặc giảm số lượng ảnh mỗi bài xuống 0.")
            return
            
        if not category_options:
            st.warning("Vui lòng kiểm tra lại kết nối WP hoặc tạo danh mục trước.")
            return

        # Start Thread
        task_manager.update(
            is_running=True,
            should_stop=False,
            completed=0,
            total=num_articles * 2 + 1, # generate kw (1) + write (N) + publish (N)
            success=0,
            errors=[],
            feature="auto_pilot",
            success_msg="",
            current_step="Bắt đầu...",
        )
        
        if "global_cancel_event" not in st.session_state:
            st.session_state["global_cancel_event"] = threading.Event()
        else:
            st.session_state["global_cancel_event"].clear()

        def background_auto_pilot(cancel_event: threading.Event):
            try:
                # 1. Tạo từ khóa
                task_manager.update(current_step="Đang nhờ AI tạo từ khóa...")
                keyword_language_map = {"Tiếng Việt": "Vietnamese", "Tiếng Trung Giản Thể": "Chinese (Simplified)"}
                suggested_keywords = agent.generate_related_keywords(
                    topic=topic.strip(),
                    language=keyword_language_map[language],
                    count=int(num_articles)
                )
                
                primary_kws = suggested_keywords.get("primary_keywords", [])
                long_tail_kws = suggested_keywords.get("long_tail_keywords", [])
                
                if not primary_kws:
                    raise Exception("AI không tạo được từ khóa nào.")
                    
                task_manager.increment(success=True)

                # 2. Tạo bài viết trong DB
                task_manager.update(current_step="Đang lưu từ khóa vào Database...")
                def make_slug(text):
                    return re.sub(r'[^a-z0-9]+', '-', unidecode(str(text).lower())).strip('-')
                
                article_ids = []
                keywords_per_primary = 5
                
                for idx, primary_kw in enumerate(primary_kws):
                    start_idx = idx * keywords_per_primary
                    end_idx = min(start_idx + keywords_per_primary, len(long_tail_kws))
                    chunk = long_tail_kws[start_idx:end_idx]
                    longtail_str = ", ".join(chunk) if chunk else ""
                    
                    pillar_article = ArticleRepository.add_keyword(primary_kw)
                    pillar_context = f"Bạn đang viết Bài Chính (Pillar Article). BẮT BUỘC phải sử dụng tất cả các từ khóa phụ sau đây vào trong các đoạn văn của bài viết một cách tự nhiên nhất: {longtail_str}"
                    ArticleRepository.update_article_fields(
                        pillar_article.id,
                        context=pillar_context,
                        long_tail_keywords=longtail_str,
                    )
                    article_ids.append(pillar_article.id)
                    if sheets:
                        sheets.upsert_article_row(ArticleRepository.get_article_by_id(pillar_article.id))

                # 3. Phân bổ ảnh & Viết bài
                pool_uploaded = uploaded_images if uploaded_images else []
                from ui.app import load_wp_media_items_cached
                try:
                    # Truy vấn ảnh WP có liên quan đến chủ đề (topic) để tránh nhầm cate
                    wp_media_items = load_wp_media_items_cached(site_name=active_site, max_pages=3, search_term=topic.strip())
                    pool_wp = [m["url"] for m in wp_media_items if m.get("url")]
                except Exception:
                    pool_wp = []
                    
                cursor_upload = 0
                cursor_wp = 0
                
                category = category_options.get(category_label)
                selected_category_id = category["id"] if category else None
                selected_category_name = category["name"] if category else None
                
                alt_strat = alt_strategy_map.get(thumbnail_alt, "keyword_local")
                if alt_strat == "Dùng title bài làm ALT": alt_strat = "title"
                if alt_strat == "AI viết ALT": alt_strat = "ai"
                
                for article_id in article_ids:
                    if cancel_event.is_set():
                        break
                        
                    task_manager.update(current_step=f"Đang viết bài ID: {article_id}...")
                    
                    # Chọn ảnh cho bài này (Đồng nhất kiểu dữ liệu để không bị mix)
                    assigned_images = []
                    images_needed = int(num_images)
                    if images_needed > 0:
                        if cursor_upload + images_needed <= len(pool_uploaded):
                            assigned_images = pool_uploaded[cursor_upload:cursor_upload + images_needed]
                            cursor_upload += images_needed
                        else:
                            if pool_wp:
                                for _ in range(images_needed):
                                    assigned_images.append(pool_wp[cursor_wp % len(pool_wp)])
                                    cursor_wp += 1
                            else:
                                # Fallback nếu cả WP Media cũng trống
                                if pool_uploaded:
                                    for _ in range(images_needed):
                                        assigned_images.append(pool_uploaded[cursor_upload % len(pool_uploaded)])
                                        cursor_upload += 1
                            
                    def process_ai_output_images(ai_output, article, src_id=article_id, lang_label=language):
                        return apply_images_to_ai_output_callback(
                            ai_output,
                            article,
                            assigned_images,
                            images_needed,
                            lang_label,
                            False,
                            alt_strat,
                        )
                    
                    # Viết bài
                    is_success, message = orchestrator.generate_single_article(
                        article_id=article_id,
                        language_label=language,
                        language_prompt=language_prompt_map[language],
                        site_name=active_site,
                        ai_output_processor_callback=process_ai_output_images,
                        cancel_event=cancel_event,
                    )
                    
                    task_manager.increment(success=is_success)
                    if not is_success:
                        task_manager.append_error(f"Lỗi viết bài {article_id}: {message}")
                        task_manager.increment(success=False) # Skip publish step
                        continue
                        
                    # 4. Đăng bài
                    task_manager.update(current_step=f"Đang đăng bài ID: {article_id} lên WP...")
                    article = ArticleRepository.get_article_by_id(article_id)
                    
                    try:
                        thumbnail_bytes = None
                        thumbnail_name = None
                        thumbnail_id = None
                        
                        if assigned_images:
                            if not isinstance(assigned_images[0], str):
                                thumbnail_bytes = assigned_images[0].getvalue()
                                thumbnail_name = assigned_images[0].name
                            else:
                                first_url = assigned_images[0]
                                for m in wp_media_items:
                                    if m.get("url") == first_url:
                                        thumbnail_id = m.get("id")
                                        break
                                        
                        content_markdown_processed = article.content_markdown
                        
                        # Note: orchestrator.publish_single_article takes thumbnail_bytes and thumbnail_name.
                        # It will upload the bytes and get an ID. Since we already have the ID (thumbnail_id),
                        # we should either pass thumbnail_id to it, or it will create a new one.
                        # Wait, publish_single_article might not accept thumbnail_id.
                        # Let's check publish_single_article signature. We'll pass it as a kwarg if supported,
                        # but if not, we can manually call update_article_fields or bypass.
                        
                        pub_success, pub_error, published_url = orchestrator.publish_single_article(
                            article_id=article_id,
                            status_val="publish",
                            category_id=selected_category_id,
                            category_name=selected_category_name,
                            thumbnail_bytes=thumbnail_bytes,
                            thumbnail_name=thumbnail_name,
                            thumbnail_details=None,
                            content_markdown_processed=content_markdown_processed,
                        )
                        
                        # Override thumbnail if we used an existing WP Media ID
                        if pub_success and thumbnail_id and not thumbnail_bytes:
                            article_ref = ArticleRepository.get_article_by_id(article_id)
                            wp_post_id = article_ref.wp_post_id
                            if wp_post_id:
                                try:
                                    from ui.app import get_wp_publisher
                                    wp = get_wp_publisher(site_name=active_site)
                                    wp._request_with_retries("POST", f"{wp.api_endpoint}/{wp_post_id}", json={"featured_media": thumbnail_id})
                                except Exception as th_err:
                                    print(f"Không thể gán thumbnail cũ cho bài {article_id}: {th_err}")
                        
                        task_manager.increment(success=pub_success)
                        if not pub_success:
                            task_manager.append_error(f"Lỗi đăng bài {article_id}: {pub_error}")
                            
                    except Exception as pub_ex:
                        task_manager.increment(success=False)
                        task_manager.append_error(f"Lỗi publish {article_id}: {str(pub_ex)}")

            except Exception as e:
                task_manager.append_error(f"Lỗi hệ thống: {str(e)}")
            finally:
                final_state = task_manager.get_snapshot()
                task_manager.update(
                    is_running=False,
                    success_msg=f"Đã hoàn thành quy trình! (Thành công {final_state['success']} thao tác).",
                    current_step="Hoàn tất"
                )

        from streamlit.runtime.scriptrunner import add_script_run_ctx
        thread = threading.Thread(
            target=background_auto_pilot,
            args=(st.session_state["global_cancel_event"],),
            daemon=True,
        )
        add_script_run_ctx(thread)
        thread.start()
        st.rerun()
