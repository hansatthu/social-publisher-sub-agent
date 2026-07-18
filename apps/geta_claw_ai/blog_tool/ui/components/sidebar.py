import re
from typing import Any

import streamlit as st

from services.article_repository import ArticleRepository, RepositoryError


def render_sidebar_component(
    *,
    is_locked: bool,
    agent,
    sheets,
    clear_previous_result_messages_callback,
) -> None:
    quota_snapshot = agent.get_quota_snapshot()
    with st.sidebar.container(border=True):
        st.markdown("### Quota Gemini (hôm nay)")
        st.caption(f"Ngày: {quota_snapshot.get('date', '-')}")
        st.write(f"Requests đã dùng: {quota_snapshot['requests_used']}")
        st.write(f"Tokens đã dùng: {quota_snapshot['tokens_used']}")


    # --- Chọn Site ---
    from ui.state import get_site_options
    site_options = get_site_options()
    current_site = st.session_state.get("active_site", site_options[0] if site_options else "")
    site_index = site_options.index(current_site) if current_site in site_options else 0
    site = st.sidebar.selectbox(
        "Chọn site",
        site_options,
        index=site_index,
        key="active_site_select",
        label_visibility="collapsed",
        disabled=is_locked or not site_options,
    )
    st.session_state["active_site"] = site

    if st.sidebar.button("🔌 Chọn lại website khác", use_container_width=True, disabled=is_locked):
        st.session_state["active_site"] = None
        if "active_site_select" in st.session_state:
            del st.session_state["active_site_select"]
        st.rerun()

    st.sidebar.markdown("### Chọn tính năng")
    feature_options = ["Post Automation", "Auto Pilot", "Product Automation"]
    current_feature = st.session_state.get("active_feature", "Post Automation")
    feature_index = feature_options.index(current_feature) if current_feature in feature_options else 0
    feature = st.sidebar.selectbox(
        "Tính năng",
        feature_options,
        index=feature_index,
        key="active_feature_select",
        label_visibility="collapsed",
        disabled=is_locked,
    )
    st.session_state["active_feature"] = feature

    if feature == "Post Automation":
        with st.sidebar.container(border=True):
            st.markdown("### AI đề xuất từ khóa")
            topic_input = st.text_input("Chủ đề muốn viết", disabled=is_locked)
            keyword_language = st.selectbox(
                "Ngôn ngữ từ khóa",
                options=["Tiếng Việt", "Tiếng Trung Giản Thể"],
                index=0,
                disabled=is_locked,
            )
            num_primary_keywords = st.number_input(
                "Số keyword CHÍNH muốn tạo (mỗi keyword = 1 bài viết)", 
                min_value=1, 
                max_value=20, 
                value=2, 
                step=1, 
                disabled=is_locked,
                help="AI sẽ tạo N keyword chính + N×5 keyword phụ (tự động chia)"
            )

            keyword_language_map = {
                "Tiếng Việt": "Vietnamese",
                "Tiếng Trung Giản Thể": "Chinese (Simplified)",
            }

            if st.button("AI tạo từ khóa", disabled=is_locked):
                if not topic_input.strip():
                    st.warning("Vui lòng nhập chủ đề trước khi tạo từ khóa.")
                else:
                    try:
                        suggested_keywords = agent.generate_related_keywords(
                            topic=topic_input.strip(),
                            language=keyword_language_map[keyword_language],
                            count=int(num_primary_keywords),
                        )
                        st.session_state["ai_keyword_suggestions"] = suggested_keywords
                        if suggested_keywords:
                            primary_count = len(suggested_keywords.get("primary_keywords", []))
                            longtail_count = len(suggested_keywords.get("long_tail_keywords", []))
                            st.success(f"AI đã tạo {primary_count} keyword chính + {longtail_count} keyword phụ.")
                            
                            # Tự động điền xuống ô nhập liệu bên dưới
                            st.session_state["input_primary_keywords"] = "\n".join(suggested_keywords.get("primary_keywords", []))
                            st.session_state["input_longtail_keywords"] = "\n".join(suggested_keywords.get("long_tail_keywords", []))
                            st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi AI gợi ý từ khóa: {str(e)}")

            suggestions = st.session_state.get("ai_keyword_suggestions", {})
            if suggestions:
                st.divider()
                if isinstance(suggestions, dict):
                    primary_kws = suggestions.get("primary_keywords", [])
                    long_tail_kws = suggestions.get("long_tail_keywords", [])

                    if primary_kws:
                        st.markdown("##### 🔑 Primary Keywords")
                        st.code(", ".join(primary_kws), language="text")

                    if long_tail_kws:
                        st.markdown("##### 🎯 Long-tail Keywords")
                        st.caption(f"Tổng {len(long_tail_kws)} keywords phụ (sẽ chia đều cho mỗi primary)")
                        st.code(", ".join(long_tail_kws), language="text")

                    if not primary_kws and not long_tail_kws:
                        st.info("AI không tìm thấy từ khóa phù hợp.")
                else:
                    st.markdown("##### 🔑 Keywords")
                    st.code(", ".join(suggestions), language="text")

        st.sidebar.divider()

        st.sidebar.markdown("##### 📦 Nhập từ khóa + Long-tail")
        st.sidebar.caption("Step 1: Paste keywords chính (mỗi dòng/phẩy = 1 keyword). Step 2: Paste keywords phụ. Tool tự gom 1 primary + 5 long-tail/bài.")

        primary_keywords_raw = st.sidebar.text_area(
            "Keywords chính (Primary)",
            value=st.session_state.get("input_primary_keywords", ""),
            height=80,
            help="Mỗi dòng hoặc dấu phẩy = 1 từ khóa chính. VD: bảng hiệu quảng cáo, sách menu nhà hàng",
            disabled=is_locked,
            key="input_primary_keywords_area",
        )
        st.session_state["input_primary_keywords"] = primary_keywords_raw

        longtail_keywords_raw = st.sidebar.text_area(
            "Keywords phụ (Long-tail)",
            value=st.session_state.get("input_longtail_keywords", ""),
            height=100,
            help="Mỗi dòng hoặc dấu phẩy = 1 từ khóa phụ. VD: bảng hiệu neon giá rẻ, menu bìa cứng, lắp đặt bảng hiệu",
            disabled=is_locked,
            key="input_longtail_keywords_area",
        )
        st.session_state["input_longtail_keywords"] = longtail_keywords_raw

        enable_topic_cluster = st.sidebar.checkbox("Tạo Cụm Bài (Topic Cluster) - 1 Chính + 5 Vệ Tinh", value=st.session_state.get("enable_topic_cluster_checkbox", True), key="enable_topic_cluster_checkbox", help="Sẽ tạo 1 bài Pillar và 5 bài Satellite (mỗi bài phụ chèn 1 backlink về bài chính).")

        if st.sidebar.button("🔄 Gom nhóm từ khóa", type="primary", disabled=is_locked):
            try:
                if not primary_keywords_raw.strip() or not longtail_keywords_raw.strip():
                    st.sidebar.warning("Vui lòng nhập cả keywords chính và keywords phụ.")
                else:
                    clear_previous_result_messages_callback()
                    
                    # Parse primary keywords
                    primary_list = [kw.strip() for kw in re.split(r"[,;\n]+", primary_keywords_raw) if kw.strip()]
                    
                    # Parse long-tail keywords
                    longtail_list = [kw.strip() for kw in re.split(r"[,;\n]+", longtail_keywords_raw) if kw.strip()]
                    
                    if not primary_list or not longtail_list:
                        st.sidebar.warning("Vui lòng nhập ít nhất 1 keyword chính và 1 keyword phụ.")
                    else:
                        from unidecode import unidecode
                        def make_slug(text):
                            return re.sub(r'[^a-z0-9]+', '-', unidecode(str(text).lower())).strip('-')

                        keywords_per_primary = 5
                        created_count = 0
                        
                        for idx, primary_kw in enumerate(primary_list):
                            start_idx = idx * keywords_per_primary
                            end_idx = min(start_idx + keywords_per_primary, len(longtail_list))
                            chunk = longtail_list[start_idx:end_idx]
                            
                            longtail_str = ", ".join(chunk) if chunk else ""
                            
                            if not enable_topic_cluster:
                                # Luồng cũ: 1 bài chính gom tất cả từ khoá phụ
                                new_article = ArticleRepository.add_keyword(primary_kw)
                                ArticleRepository.update_article_fields(
                                    new_article.id,
                                    context=f"Hãy viết bài bao gồm các từ khóa phụ sau: {longtail_str}",
                                    long_tail_keywords=longtail_str,
                                )
                                
                                if sheets:
                                    refreshed = ArticleRepository.get_article_by_id(new_article.id)
                                    sheets.upsert_article_row(refreshed)
                                created_count += 1
                            else:
                                # Luồng mới (Topic Cluster): 1 Bài Pillar + 5 Bài Satellite
                                pillar_article = ArticleRepository.add_keyword(primary_kw)
                                pillar_context = f"Bạn đang viết Bài Chính (Pillar Article). BẮT BUỘC phải sử dụng tất cả các từ khóa phụ sau đây vào trong các đoạn văn của bài viết một cách tự nhiên nhất: {longtail_str}"
                                ArticleRepository.update_article_fields(
                                    pillar_article.id,
                                    context=pillar_context,
                                    long_tail_keywords=longtail_str,
                                )
                                created_count += 1
                                if sheets:
                                    sheets.upsert_article_row(ArticleRepository.get_article_by_id(pillar_article.id))

                                # Tạo bài vệ tinh
                                primary_slug = make_slug(primary_kw)
                                for satellite_kw in chunk:
                                    satellite_article = ArticleRepository.add_keyword(satellite_kw)
                                    backlink_instruction = f"Đây là bài viết vệ tinh (Satellite Article) hỗ trợ cho bài viết chính (Pillar) có chủ đề '{primary_kw}'. BẮT BUỘC chèn 1 internal link tự nhiên trong bài viết (dùng Markdown link, CÓ IN ĐẬM) trỏ về bài chính với cấu trúc như sau: **[{primary_kw}](/{primary_slug})**."
                                    
                                    ArticleRepository.update_article_fields(
                                        satellite_article.id,
                                        context=backlink_instruction,
                                        long_tail_keywords="",
                                    )
                                    created_count += 1
                                    if sheets:
                                        sheets.upsert_article_row(ArticleRepository.get_article_by_id(satellite_article.id))
                        
                        st.sidebar.success(f"✅ Đã tạo {created_count} bài viết!")
                        st.session_state["input_primary_keywords"] = ""
                        st.session_state["input_longtail_keywords"] = ""
                        st.rerun()
            except RepositoryError as e:
                st.sidebar.error(str(e))
            except Exception as ex:
                st.sidebar.error(f"Lỗi xử lý: {str(ex)}")

        st.sidebar.divider()
        st.sidebar.markdown("⏱️ **Hẹn Giờ Viết Bài**")
        st.sidebar.selectbox("Chọn các bài muốn share", ["Choose options"], disabled=is_locked)
        st.sidebar.selectbox("Chọn các Page", ["Choose options"], disabled=is_locked)
        st.sidebar.selectbox("Chọn nhóm để chia sẻ", ["No options to select"], disabled=is_locked)

        if st.sidebar.button("🔄 Làm mới dữ liệu", disabled=is_locked):
            st.rerun()