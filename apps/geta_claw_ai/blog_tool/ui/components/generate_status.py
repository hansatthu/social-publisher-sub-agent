from typing import Any

import streamlit as st


def render_generate_result_messages(current_state: dict[str, Any], task_manager: Any) -> None:
    if current_state.get("success", 0) > 0:
        st.success(str(current_state.get("success_msg") or ""))

    success_ids = [int(item) for item in (current_state.get("success_ids") or [])]
    failed_ids = [int(item) for item in (current_state.get("failed_ids") or [])]

    if success_ids:
        st.info(f"ID generate thành công: {', '.join(str(item) for item in sorted(success_ids))}")
    if failed_ids:
        st.warning(f"ID generate thất bại: {', '.join(str(item) for item in sorted(failed_ids))}")

    if current_state.get("errors"):
        st.error("Một số bài viết generate thất bại / bị hủy:")
        st.text("\n".join((current_state.get("errors") or [])[:20]))

    if st.button("Xác nhận & Dọn dẹp Message", key="clear_gen_msg"):
        task_manager.update(
            feature=None,
            errors=[],
            success=0,
            success_ids=[],
            failed_ids=[],
        )
        st.rerun()
