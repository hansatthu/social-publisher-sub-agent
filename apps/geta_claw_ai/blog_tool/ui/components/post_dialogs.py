import streamlit as st


def clear_language_confirm_state() -> None:
    st.session_state["generate_lang_confirm_needed"] = False
    st.session_state["generate_lang_confirm_label"] = ""
    st.session_state["generate_lang_confirm_mismatch_count"] = 0
    st.session_state["generate_lang_confirm_mismatch_preview"] = []


def render_language_confirm_dialog(language_label: str, start_generate_jobs_callback) -> None:
    @st.dialog("Xác nhận ngôn ngữ viết bài")
    def _dialog() -> None:
        chosen_language = str(st.session_state.get("generate_lang_confirm_label") or language_label)
        mismatch_count = int(st.session_state.get("generate_lang_confirm_mismatch_count", 0) or 0)
        preview_items = st.session_state.get("generate_lang_confirm_mismatch_preview", []) or []

        st.warning(f"bạn có chắc muốn dùng ngôn ngữ {chosen_language} để viết bài...")
        if mismatch_count > 0:
            st.caption(f"Có {mismatch_count} từ khóa khác ngôn ngữ bạn đã chọn.")
        if preview_items:
            st.caption("Ví dụ các dòng có thể lệch ngôn ngữ:")
            st.text("\n".join(preview_items))

        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("Tiếp tục viết", type="primary", key="confirm_generate_language_yes"):
                start_generate_jobs_callback(force_single_language=True)
        with col_cancel:
            if st.button("Hủy", key="confirm_generate_language_no"):
                clear_language_confirm_state()
                st.rerun()

    _dialog()
