import re
from typing import Any, Callable

import requests


class WooCategoryService:
    def __init__(
        self,
        *,
        request_func: Callable[..., requests.Response],
        categories_endpoint: str,
        integration_error_cls: type[Exception],
    ) -> None:
        self._request = request_func
        self.categories_endpoint = categories_endpoint
        self.integration_error_cls = integration_error_cls

    @staticmethod
    def _normalize_text(value: str) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _normalize_slug(value: str) -> str:
        text = WooCategoryService._normalize_text(value)
        text = re.sub(r"\s+", "-", text)
        return re.sub(r"-+", "-", text).strip("-")

    @staticmethod
    def _parse_path_segments(token: str) -> list[str]:
        raw = str(token or "").strip()
        if not raw:
            return []
        parts = [segment.strip() for segment in re.split(r"\s*>\s*|\s*›\s*|\s*/\s*", raw) if segment.strip()]
        return parts if parts else [raw]

    def _load_all_categories(self) -> list[dict[str, Any]]:
        all_categories: list[dict[str, Any]] = []
        page = 1
        while True:
            try:
                response = self._request(
                    "GET",
                    self.categories_endpoint,
                    params={"per_page": 100, "page": page, "hide_empty": "false"},
                )
            except requests.exceptions.RequestException as fetch_error:
                raise self.integration_error_cls(f"Không tải được danh sách categories WooCommerce: {fetch_error}")

            batch = response.json() or []
            if not batch:
                break
            all_categories.extend(batch)

            if len(batch) < 100:
                break
            page += 1

        return all_categories

    @staticmethod
    def _get_ancestor_chain(category_id: int, categories_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        visited: set[int] = set()
        current_id = int(category_id)

        while current_id and current_id not in visited and current_id in categories_by_id:
            visited.add(current_id)
            node = categories_by_id[current_id]
            parent_id = int(node.get("parent") or 0)
            if not parent_id or parent_id not in categories_by_id:
                break
            parent_node = categories_by_id[parent_id]
            chain.append(parent_node)
            current_id = parent_id

        return chain

    @staticmethod
    def _match_path(
        category_item: dict[str, Any],
        path_segments: list[str],
        categories_by_id: dict[int, dict[str, Any]],
    ) -> bool:
        if len(path_segments) <= 1:
            return True

        parent_segments = path_segments[:-1]
        ancestor_chain = WooCategoryService._get_ancestor_chain(int(category_item.get("id") or 0), categories_by_id)
        ancestor_tokens = [
            {
                WooCategoryService._normalize_text(str(node.get("name", "") or "")),
                WooCategoryService._normalize_slug(str(node.get("slug", "") or "")),
            }
            for node in ancestor_chain
        ]

        for expected in reversed(parent_segments):
            expected_name = WooCategoryService._normalize_text(expected)
            expected_slug = WooCategoryService._normalize_slug(expected)
            matched_index = next(
                (
                    idx
                    for idx, token_set in enumerate(ancestor_tokens)
                    if expected_name in token_set or expected_slug in token_set
                ),
                None,
            )
            if matched_index is None:
                return False
            ancestor_tokens = ancestor_tokens[matched_index + 1 :]

        return True

    def _resolve_existing_category_id(
        self,
        token: str,
        all_categories: list[dict[str, Any]],
        categories_by_id: dict[int, dict[str, Any]],
    ) -> int | None:
        normalized_token = str(token or "").strip()
        if not normalized_token:
            return None

        if normalized_token.isdigit():
            category_id = int(normalized_token)
            if category_id in categories_by_id:
                return category_id

        path_segments = self._parse_path_segments(normalized_token)
        leaf_token = path_segments[-1] if path_segments else normalized_token
        leaf_name = self._normalize_text(leaf_token)
        leaf_slug = self._normalize_slug(leaf_token)

        slug_matches = [
            item
            for item in all_categories
            if self._normalize_slug(str(item.get("slug", "") or "")) == leaf_slug
        ]
        if path_segments:
            slug_matches = [item for item in slug_matches if self._match_path(item, path_segments, categories_by_id)]
        if len(slug_matches) == 1 and slug_matches[0].get("id"):
            return int(slug_matches[0]["id"])

        name_matches = [
            item
            for item in all_categories
            if self._normalize_text(str(item.get("name", "") or "")) == leaf_name
        ]
        if path_segments:
            name_matches = [item for item in name_matches if self._match_path(item, path_segments, categories_by_id)]

        if len(name_matches) == 1 and name_matches[0].get("id"):
            return int(name_matches[0]["id"])

        if len(name_matches) > 1:
            matched_info = ", ".join(
                [
                    f"ID {item.get('id')} ({item.get('name')} / {item.get('slug')})"
                    for item in name_matches[:8]
                ]
            )
            raise self.integration_error_cls(
                "Category bị mơ hồ khi map từ dữ liệu upload: "
                f"'{normalized_token}'. Có nhiều term trùng tên. "
                f"Vui lòng dùng slug hoặc ID cụ thể. Matches: {matched_info}"
            )

        return None

    def find_existing_category_ids(self, category_names: list[str]) -> list[int]:
        category_ids: list[int] = []
        all_categories = self._load_all_categories()
        categories_by_id = {
            int(item.get("id")): item
            for item in all_categories
            if item.get("id")
        }

        for category_name in category_names:
            token = str(category_name or "").strip()
            if not token:
                continue

            matched_id = self._resolve_existing_category_id(token, all_categories, categories_by_id)
            if matched_id:
                category_ids.append(matched_id)
                continue

            raise self.integration_error_cls(
                "Không tìm thấy category WooCommerce khớp với giá trị: "
                f"'{token}'. Tool đã tắt tạo category mới. "
                "Vui lòng nhập đúng category ID hoặc slug đã tồn tại trên WordPress."
            )

        return category_ids

    def list_product_categories(self) -> list[dict[str, Any]]:
        categories: list[dict[str, Any]] = []
        page = 1

        while True:
            response = self._request(
                "GET",
                self.categories_endpoint,
                params={"per_page": 100, "page": page},
            )
            batch = response.json() or []
            if not batch:
                break

            for item in batch:
                category_id = item.get("id")
                category_name = str(item.get("name", "")).strip()
                if category_id and category_name:
                    categories.append(
                        {
                            "id": int(category_id),
                            "name": category_name,
                            "slug": str(item.get("slug", "")).strip(),
                        }
                    )

            if len(batch) < 100:
                break
            page += 1

        return categories