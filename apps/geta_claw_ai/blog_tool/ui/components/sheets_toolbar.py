import html
import time

import streamlit as st


def render_sheets_sync_toolbar_component(
    *,
    df_articles,
    is_locked: bool,
    sheets,
    build_table_fingerprint_callback,
    sync_full_table_to_sheets_callback,
) -> None:
    left_col, right_col = st.columns([1, 4], gap="small")

    with left_col:
        auto_sync_enabled = st.checkbox(
            "Tự động đồng bộ lên sheet",
            value=st.session_state.get("sheets_auto_sync_enabled", False),
            disabled=is_locked,
            key="sheets_auto_sync_enabled_checkbox",
        )
        st.session_state["sheets_auto_sync_enabled"] = auto_sync_enabled

    if auto_sync_enabled and not is_locked:
        if not sheets:
            st.session_state["sheets_sync_message"] = "Chưa cấu hình Google Sheets (.env), nên không thể sync."
            st.session_state["sheets_sync_is_error"] = True
        else:
            current_fingerprint = build_table_fingerprint_callback(df_articles)
            last_fingerprint = st.session_state.get("sheets_last_fingerprint")
            next_retry_at = float(st.session_state.get("sheets_next_auto_sync_at", 0.0) or 0.0)
            now_ts = time.time()

            if current_fingerprint != last_fingerprint and now_ts >= next_retry_at:
                try:
                    synced_rows = sync_full_table_to_sheets_callback()
                    st.session_state["sheets_last_fingerprint"] = current_fingerprint
                    st.session_state["sheets_next_auto_sync_at"] = 0.0
                    st.session_state["sheets_sync_message"] = f"Sync thành công: {synced_rows} rows."
                    st.session_state["sheets_sync_is_error"] = False
                except Exception as e:
                    error_text = str(e)
                    if "unauthorized" in error_text.lower():
                        st.session_state["sheets_auto_sync_enabled"] = False
                        st.session_state["sheets_auto_sync_enabled_checkbox"] = False
                        st.session_state["sheets_next_auto_sync_at"] = 0.0
                        st.session_state["sheets_sync_message"] = "Auto-sync đã tắt do unauthorized. Vui lòng kiểm tra SECRET/Deploy URL rồi bật lại."
                        st.session_state["sheets_sync_is_error"] = True
                    else:
                        st.session_state["sheets_next_auto_sync_at"] = time.time() + 60
                        st.session_state["sheets_sync_message"] = f"Lỗi sync: {error_text}"
                        st.session_state["sheets_sync_is_error"] = True

    message = st.session_state.get("sheets_sync_message", "")
    is_error = bool(st.session_state.get("sheets_sync_is_error", False))
    with right_col:
        if message:
            safe_message = html.escape(message)
            if is_error:
                st.markdown(
                    (
                        "<div style='padding:8px 12px;border-radius:8px;"
                        "border:1px solid #dc2626;background:#450a0a;color:#fecaca;font-size:0.95rem;'>"
                        f"{safe_message}</div>"
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    (
                        "<div style='padding:8px 12px;border-radius:8px;"
                        "border:1px solid #16a34a;background:#052e16;color:#86efac;font-size:0.95rem;'>"
                        f"{safe_message}</div>"
                    ),
                    unsafe_allow_html=True,
                )