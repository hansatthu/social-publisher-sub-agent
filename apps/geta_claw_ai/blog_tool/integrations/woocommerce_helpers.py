import re
from typing import Any


def looks_like_chinese_text(*values: str) -> bool:
    merged = " ".join(str(value or "") for value in values)
    return bool(re.search(r"[\u4e00-\u9fff]", merged))


def build_sku_candidates_for_existing_lookup(sku: str) -> list[str]:
    normalized = str(sku or "").strip()
    if not normalized:
        return []

    def add_unique(candidates: list[str], seen: set[str], value: str) -> None:
        item = str(value or "").strip()
        if not item:
            return
        key = item.lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(item)

    suffix_pattern = re.compile(r"-(vi|zh|intl)$", re.IGNORECASE)
    base = suffix_pattern.sub("", normalized).strip()

    candidate_values: list[str] = []
    seen: set[str] = set()

    add_unique(candidate_values, seen, normalized)
    add_unique(candidate_values, seen, base)

    if base:
        add_unique(candidate_values, seen, f"{base}-VI")
        add_unique(candidate_values, seen, f"{base}-ZH")
        add_unique(candidate_values, seen, f"{base}-INTL")

    if normalized and not suffix_pattern.search(normalized):
        add_unique(candidate_values, seen, f"{normalized}-VI")
        add_unique(candidate_values, seen, f"{normalized}-ZH")

    return candidate_values


def normalize_image_urls(image_urls: list[str]) -> list[dict[str, Any]]:
    normalized_images: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()

    for raw_value in image_urls or []:
        token = str(raw_value or "").strip()
        if not token:
            continue

        compact_token = token.strip().strip("/")
        id_match = re.fullmatch(
            r"(?:(?:https?://)?)?(?:id\s*[:#-]?\s*)?(\d+)(?:\.0+)?",
            compact_token,
            flags=re.IGNORECASE,
        )
        if id_match:
            media_id = int(id_match.group(1))
            key = f"id:{media_id}"
            if key in seen_tokens:
                continue
            seen_tokens.add(key)
            normalized_images.append({"id": media_id})
            continue

        key = f"src:{token}"
        if key in seen_tokens:
            continue
        seen_tokens.add(key)
        normalized_images.append({"src": token})

    return normalized_images