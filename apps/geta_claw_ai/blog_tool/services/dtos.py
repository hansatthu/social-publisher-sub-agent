import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WooCommerceProductDTO:
    name: str
    regular_price: str
    description: str
    short_description: str
    name_zh: str
    short_desc_zh: str
    desc_zh: str
    sku: str
    stock_quantity: int | None
    category_names: list[str]
    category_zh: str
    category_desc_zh: str
    image_urls: list[str]
    update_zh_existing: bool

    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.lower() in {"nan", "none", "null"} else text

    @staticmethod
    def _normalize_media_token(token: str) -> str:
        normalized = str(token or "").strip().strip("\"'")
        if not normalized:
            return ""

        compact = normalized.strip().strip("/")
        media_id_match = re.fullmatch(
            r"(?:(?:https?://)?)?(?:id\s*[:#-]?\s*)?(\d+)(?:\.0+)?",
            compact,
            flags=re.IGNORECASE,
        )
        if media_id_match:
            return str(int(media_id_match.group(1)))

        return normalized

    @classmethod
    def _parse_csv_cells(cls, value: Any, *, for_images: bool = False) -> list[str]:
        text = cls._as_text(value)
        if not text:
            return []

        values = [item.strip() for item in text.split(",") if item.strip()]
        if not for_images:
            return values

        normalized_values: list[str] = []
        seen_values: set[str] = set()
        for item in values:
            normalized_item = cls._normalize_media_token(item)
            if not normalized_item or normalized_item in seen_values:
                continue
            seen_values.add(normalized_item)
            normalized_values.append(normalized_item)
        return normalized_values

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WooCommerceProductDTO":
        normalized_name = cls._as_text(data.get("name"))
        normalized_price = cls._as_text(data.get("regular_price"))

        stock_raw = cls._as_text(data.get("stock_quantity"))
        stock_quantity: int | None = None
        if stock_raw:
            stock_quantity = int(float(stock_raw))

        return cls(
            name=normalized_name,
            regular_price=normalized_price,
            description=cls._as_text(data.get("description")),
            short_description=cls._as_text(data.get("short_description")),
            name_zh=cls._as_text(data.get("name_zh") or data.get("product_name_zh")),
            short_desc_zh=cls._as_text(data.get("short_desc_zh") or data.get("product_short_desc_zh")),
            desc_zh=cls._as_text(data.get("desc_zh") or data.get("product_desc_zh")),
            sku=cls._as_text(data.get("sku")),
            stock_quantity=stock_quantity,
            category_names=cls._parse_csv_cells(data.get("categories")),
            category_zh=cls._as_text(data.get("category_zh") or data.get("category_name_zh")),
            category_desc_zh=cls._as_text(data.get("category_desc_zh")),
            image_urls=cls._parse_csv_cells(data.get("images"), for_images=True),
            update_zh_existing=bool(data.get("__update_zh_existing", False)),
        )

    def to_create_product_kwargs(self, *, status: str = "draft") -> dict[str, Any]:
        return {
            "name": self.name,
            "regular_price": self.regular_price,
            "description": self.description,
            "short_description": self.short_description,
            "name_zh": self.name_zh,
            "short_desc_zh": self.short_desc_zh,
            "desc_zh": self.desc_zh,
            "sku": self.sku,
            "stock_quantity": self.stock_quantity,
            "category_names": self.category_names,
            "category_zh": self.category_zh,
            "category_desc_zh": self.category_desc_zh,
            "image_urls": self.image_urls,
            "status": status,
            "update_zh_existing": self.update_zh_existing,
        }
