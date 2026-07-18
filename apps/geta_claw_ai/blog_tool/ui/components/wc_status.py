from typing import Any

import streamlit as st


def render_wc_result_messages(global_task_state: dict[str, Any], reset_callback: Any) -> None:
    summary_msg = str(global_task_state.get("success_msg") or "").strip()
    if summary_msg:
        if global_task_state.get("success", 0) > 0:
            st.success(summary_msg)
        else:
            st.warning(summary_msg)

    success_links = global_task_state.get("wc_success_links", []) or []
    if success_links:
        st.info("Danh sách sản phẩm upload thành công:")
        st.markdown("\n".join([f"- {item}" for item in success_links[:200]]))

    failed_rows = global_task_state.get("wc_failed_rows", []) or []
    if failed_rows:
        st.error("Danh sách dòng bị lỗi:")
        st.text("\n".join(failed_rows[:200]))

    if st.button("Xác nhận & Dọn dẹp kết quả Woo", key="clear_wc_msg"):
        reset_callback(global_task_state)
        st.rerun()
