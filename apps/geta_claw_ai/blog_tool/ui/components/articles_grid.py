import streamlit as st
import pandas as pd


def _build_display_dataframe(df_articles: pd.DataFrame) -> pd.DataFrame:
    if df_articles is None or df_articles.empty:
        return pd.DataFrame([])

    display_df = pd.DataFrame(
        {
            "ID": df_articles.get("id"),
            "Loại": df_articles.get("type").fillna("📄 Đơn Lẻ") if "type" in df_articles.columns else "📄 Đơn Lẻ",
            "Tiêu đề": df_articles.get("title").fillna("None") if "title" in df_articles.columns else "None",
            "Mô tả": df_articles.get("meta_description").fillna("None") if "meta_description" in df_articles.columns else "None",
            "Từ khóa": df_articles.get("keyword"),
            "Danh mục": df_articles.get("category_name").fillna("Chưa gán") if "category_name" in df_articles.columns else "Chưa gán",
            "Ngôn ngữ": df_articles.get("language").fillna("Chưa gán") if "language" in df_articles.columns else "Chưa gán",
            "Ngày tạo": "",
            "Trạng thái": df_articles.get("status"),
            "SEO Score": pd.to_numeric(df_articles.get("seo_score"), errors="coerce") if "seo_score" in df_articles.columns else None,
        }
    )

    if "created_at" in df_articles.columns:
        created_at = pd.to_datetime(df_articles["created_at"], errors="coerce")
        display_df["Ngày tạo"] = created_at.dt.strftime("%Y-%m-%d %H:%M").fillna("")

    return display_df


def render_articles_grid_component(
    *,
    df_articles,
    is_locked: bool,
    delete_rows_callback,
) -> None:
    display_df = _build_display_dataframe(df_articles)
    st.dataframe(display_df, width="stretch", hide_index=True, height=300)

    if not df_articles.empty and "id" in df_articles.columns:
        selected_delete_ids = st.multiselect("Xóa rows", options=df_articles["id"].tolist(), disabled=is_locked)
        if st.button("Xóa các rows đã chọn", type="secondary", disabled=is_locked):
            try:
                deleted_count = delete_rows_callback(selected_delete_ids)
                st.success(f"Đã xóa {deleted_count} bài.")
                st.rerun()
            except Exception as e:
                st.error(str(e))