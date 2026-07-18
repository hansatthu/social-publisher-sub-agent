import streamlit as st

from services.media_service import MediaService


def detect_keyword_lang_from_option(option_label: str) -> str | None:
    parts = option_label.split(" - ", 1)
    if len(parts) <= 1:
        return None
    keyword_part = parts[1].rsplit(" [", 1)[0]
    return MediaService.detect_keyword_language(keyword_part)


def render_selected_keyword_lang_summary(selected_option_list: list[str]) -> None:
    detected_langs = [detect_keyword_lang_from_option(opt) for opt in selected_option_list]
    vi_count = sum(1 for lang in detected_langs if lang == "vi")
    zh_count = sum(1 for lang in detected_langs if lang == "zh")
    if selected_option_list:
        st.caption(f"Phát hiện từ khóa đã chọn: VI={vi_count} | ZH={zh_count}")
