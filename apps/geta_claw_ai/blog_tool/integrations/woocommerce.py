import os
import time
from typing import Any

import requests
from dotenv import load_dotenv
from integrations.woocommerce_api_client import WooCommerceApiClient
from integrations.woocommerce_category_service import WooCategoryService
from integrations.woocommerce_constants import WCMetaKeys
from integrations.woocommerce_helpers import (
    build_sku_candidates_for_existing_lookup,
    looks_like_chinese_text,
    normalize_image_urls,
)
from services.dtos import WooCommerceProductDTO

load_dotenv()


class WooCommerceIntegrationError(Exception):
    pass


class WooCommercePublisher:
    def __init__(self, base_url=None, consumer_key=None, consumer_secret=None):
        self.base_url = (base_url or os.getenv("WC_API_URL") or os.getenv("WP_SITE_URL") or "").rstrip("/")
        self.consumer_key = (consumer_key or os.getenv("WC_CONSUMER_KEY", "")).strip()
        self.consumer_secret = (consumer_secret or os.getenv("WC_CONSUMER_SECRET", "")).strip()

        if not self.base_url:
            raise WooCommerceIntegrationError("Thiếu WC_API_URL hoặc WP_SITE_URL trong .env hoặc truyền vào constructor")
        if not self.consumer_key or not self.consumer_secret:
            raise WooCommerceIntegrationError("Thiếu WC_CONSUMER_KEY hoặc WC_CONSUMER_SECRET trong .env hoặc truyền vào constructor")

        self.products_endpoint = f"{self.base_url}/wp-json/wc/v3/products"
        self.categories_endpoint = f"{self.base_url}/wp-json/wc/v3/products/categories"
        self.auth = (self.consumer_key, self.consumer_secret)
        self.request_timeout_seconds = max(20, int(os.getenv("WC_REQUEST_TIMEOUT_SECONDS", "75") or 75))
        self.api_client = WooCommerceApiClient(auth=self.auth, timeout_seconds=self.request_timeout_seconds)
        self.category_service = WooCategoryService(
            request_func=self._request,
            categories_endpoint=self.categories_endpoint,
            integration_error_cls=WooCommerceIntegrationError,
        )

    @staticmethod
    def _sanitize_error_text(value: str) -> str:
        return WooCommerceApiClient.sanitize_error_text(value)

    @staticmethod
    def _build_readable_error_detail(response: requests.Response | None) -> str:
        return WooCommerceApiClient.build_readable_error_detail(response)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        return self.api_client.request(method=method, url=url, **kwargs)

    def _find_or_create_category_ids(self, category_names: list[str]) -> list[int]:
        return self.category_service.find_existing_category_ids(category_names)

    def list_product_categories(self) -> list[dict[str, Any]]:
        return self.category_service.list_product_categories()

    def get_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        normalized_sku = str(sku or "").strip()
        if not normalized_sku:
            return None

        def match_exact_product(items: list[dict[str, Any]]) -> dict[str, Any] | None:
            for item in items:
                product_sku = str(item.get("sku", "")).strip()
                if product_sku.lower() == normalized_sku.lower():
                    return item
            return None

        lookup_params_list = [
            {"sku": normalized_sku, "status": "any", "per_page": 100},
            {"search": normalized_sku, "status": "any", "per_page": 100},
        ]

        for lookup_params in lookup_params_list:
            page = 1
            while True:
                params = dict(lookup_params)
                params["page"] = page
                response = self._request("GET", self.products_endpoint, params=params)
                products = response.json() or []
                if not products:
                    break

                matched = match_exact_product(products)
                if matched:
                    return matched

                if len(products) < int(params.get("per_page", 100)):
                    break
                page += 1

        return None

    def find_existing_skus(self, sku_values: list[str]) -> dict[str, dict[str, Any]]:
        existing_map: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()

        for raw_sku in sku_values:
            normalized_sku = str(raw_sku or "").strip()
            if not normalized_sku:
                continue

            normalized_key = normalized_sku.lower()
            if normalized_key in seen:
                continue
            seen.add(normalized_key)

            product = self.get_product_by_sku(normalized_sku)
            if product:
                existing_map[normalized_sku] = product

        return existing_map

    @staticmethod
    def _looks_like_chinese_text(*values: str) -> bool:
        return looks_like_chinese_text(*values)

    @staticmethod
    def _build_sku_candidates_for_existing_lookup(sku: str) -> list[str]:
        return build_sku_candidates_for_existing_lookup(sku)

    def find_existing_product_for_chinese_update(self, sku: str) -> dict[str, Any] | None:
        for candidate_sku in self._build_sku_candidates_for_existing_lookup(sku):
            product = self.get_product_by_sku(candidate_sku)
            if product and product.get("id"):
                return product
        return None

    def _build_zh_meta_updates(
        self,
        name: str,
        short_description: str,
        description: str,
        name_zh: str = "",
        short_desc_zh: str = "",
        desc_zh: str = "",
        product_name_zh: str = "",
        product_short_desc_zh: str = "",
        product_desc_zh: str = "",
    ) -> dict[str, str]:
        normalized_name_zh = str(name_zh or product_name_zh or "").strip() or str(name or "").strip()
        normalized_short_zh = str(short_desc_zh or product_short_desc_zh or "").strip() or str(short_description or "").strip()
        normalized_desc_zh = str(desc_zh or product_desc_zh or "").strip() or str(description or "").strip()

        updates: dict[str, str] = {}
        if normalized_name_zh:
            updates[WCMetaKeys.PRODUCT_ZH_TITLE] = normalized_name_zh
        if normalized_short_zh:
            updates[WCMetaKeys.PRODUCT_ZH_SHORT_DESC] = normalized_short_zh
        if normalized_desc_zh:
            updates[WCMetaKeys.PRODUCT_ZH_CONTENT] = normalized_desc_zh
        return updates

    def _update_product_meta_data(self, product_id: int, meta_updates: dict[str, str]) -> dict[str, Any]:
        normalized_updates = [
            {"key": key, "value": value}
            for key, value in (meta_updates or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        ]
        if not normalized_updates:
            raise WooCommerceIntegrationError("Không có dữ liệu ZH để cập nhật vào meta sản phẩm.")

        payload = {"meta_data": normalized_updates}
        self._request("PUT", f"{self.products_endpoint}/{int(product_id)}", json=payload)
        verified = self._request("GET", f"{self.products_endpoint}/{int(product_id)}").json() or {}
        if not verified.get("id"):
            raise WooCommerceIntegrationError(
                f"Cập nhật ZH meta cho product {product_id} xong nhưng không đọc lại được sản phẩm."
            )
        return verified

    def _update_category_zh_meta(self, category_id: int, category_name_zh: str = "", category_desc_zh: str = "") -> None:
        meta_updates: list[dict[str, str]] = []
        if str(category_name_zh or "").strip():
            meta_updates.append({"key": WCMetaKeys.TERM_ZH_NAME, "value": str(category_name_zh).strip()})
        if str(category_desc_zh or "").strip():
            meta_updates.append({"key": WCMetaKeys.TERM_ZH_DESC, "value": str(category_desc_zh).strip()})

        if not meta_updates:
            return

        try:
            self._request(
                "PUT",
                f"{self.categories_endpoint}/{int(category_id)}",
                json={"meta_data": meta_updates},
            )
        except requests.exceptions.RequestException:
            return

    @staticmethod
    def _normalize_image_urls(image_urls: list[str]) -> list[dict[str, Any]]:
        return normalize_image_urls(image_urls)

    def create_product(
        self,
        product_data: WooCommerceProductDTO | None = None,
        *,
        name: str = "",
        regular_price: str = "",
        description: str = "",
        short_description: str = "",
        name_zh: str = "",
        short_desc_zh: str = "",
        desc_zh: str = "",
        sku: str = "",
        stock_quantity: int | None = None,
        category_names: list[str] | None = None,
        image_urls: list[str] | None = None,
        status: str = "draft",
        update_zh_existing: bool = False,
        category_zh: str = "",
        category_desc_zh: str = "",
        product_name_zh: str = "",
        product_short_desc_zh: str = "",
        product_desc_zh: str = "",
        category_name_zh: str = "",
    ) -> dict[str, Any]:
        if product_data is not None:
            dto_kwargs = product_data.to_create_product_kwargs(status=status)
            name = str(dto_kwargs.get("name") or "")
            regular_price = str(dto_kwargs.get("regular_price") or "")
            description = str(dto_kwargs.get("description") or "")
            short_description = str(dto_kwargs.get("short_description") or "")
            name_zh = str(dto_kwargs.get("name_zh") or "")
            short_desc_zh = str(dto_kwargs.get("short_desc_zh") or "")
            desc_zh = str(dto_kwargs.get("desc_zh") or "")
            sku = str(dto_kwargs.get("sku") or "")
            stock_quantity = dto_kwargs.get("stock_quantity")
            category_names = dto_kwargs.get("category_names") or []
            category_zh = str(dto_kwargs.get("category_zh") or "")
            category_desc_zh = str(dto_kwargs.get("category_desc_zh") or "")
            image_urls = dto_kwargs.get("image_urls") or []
            status = str(dto_kwargs.get("status") or status or "draft")
            update_zh_existing = bool(dto_kwargs.get("update_zh_existing", update_zh_existing))

        payload: dict[str, Any] = {
            "name": name,
            "description": description,
            "short_description": short_description,
            "status": status,
        }
        normalized_price = str(regular_price or "").strip()
        if normalized_price:
            payload["regular_price"] = normalized_price

        if sku:
            payload["sku"] = sku
        if stock_quantity is not None:
            payload["manage_stock"] = True
            payload["stock_quantity"] = int(stock_quantity)

        categories = self._find_or_create_category_ids(category_names or [])
        if categories:
            payload["categories"] = [{"id": category_id} for category_id in categories]
            normalized_category_zh = str(category_zh or category_name_zh or "").strip()
            if self._looks_like_chinese_text(normalized_category_zh, category_desc_zh):
                for category_id in categories:
                    self._update_category_zh_meta(
                        category_id=int(category_id),
                        category_name_zh=normalized_category_zh,
                        category_desc_zh=category_desc_zh,
                    )

        normalized_images = self._normalize_image_urls(image_urls or [])
        if normalized_images:
            payload["images"] = normalized_images

        has_explicit_zh_fields = any(
            str(value or "").strip()
            for value in [name_zh, short_desc_zh, desc_zh, product_name_zh, product_short_desc_zh, product_desc_zh]
        )
        if update_zh_existing and (has_explicit_zh_fields or self._looks_like_chinese_text(name, short_description, description)):
            existing_for_zh = self.find_existing_product_for_chinese_update(sku)
            if existing_for_zh and existing_for_zh.get("id"):
                meta_updates = self._build_zh_meta_updates(
                    name=name,
                    short_description=short_description,
                    description=description,
                    name_zh=name_zh,
                    short_desc_zh=short_desc_zh,
                    desc_zh=desc_zh,
                    product_name_zh=product_name_zh,
                    product_short_desc_zh=product_short_desc_zh,
                    product_desc_zh=product_desc_zh,
                )
                updated_product = self._update_product_meta_data(int(existing_for_zh["id"]), meta_updates)
                return {
                    "product_id": int(updated_product.get("id")),
                    "product_url": updated_product.get("permalink"),
                    "product_name": updated_product.get("name"),
                    "updated_existing": True,
                    "update_mode": "zh_meta",
                }

        max_create_retries = max(1, min(4, int(os.getenv("WC_CREATE_PRODUCT_RETRIES", "3") or 3)))
        retry_delay_seconds = max(0.5, float(os.getenv("WC_CREATE_PRODUCT_RETRY_DELAY_SECONDS", "1.5") or 1.5))

        def _verify_or_recover_existing_product() -> dict[str, Any] | None:
            normalized_sku = str(sku or "").strip()
            if not normalized_sku:
                return None
            try:
                existing_product = self.get_product_by_sku(normalized_sku)
            except requests.exceptions.RequestException:
                return None
            if not existing_product or not existing_product.get("id"):
                return None
            return {
                "product_id": int(existing_product.get("id")),
                "product_url": existing_product.get("permalink"),
                "product_name": existing_product.get("name"),
                "already_exists": True,
            }

        def _is_duplicate_sku_error(request_error: requests.exceptions.RequestException) -> bool:
            response = getattr(request_error, "response", None)
            if response is None:
                return False
            try:
                payload = response.json() or {}
            except Exception:
                payload = {}
            code_text = str(payload.get("code", "") or "").strip().lower()
            message_text = str(payload.get("message", "") or "").strip().lower()
            if "product_not_created" in code_text and "sku" in message_text and (
                "tồn tại" in message_text or "already" in message_text or "exists" in message_text
            ):
                return True
            if response.status_code == 400 and "sku" in message_text and (
                "tồn tại" in message_text or "already" in message_text or "exists" in message_text
            ):
                return True
            return False

        try:
            response: requests.Response | None = None
            last_error: requests.exceptions.RequestException | None = None

            for attempt in range(1, max_create_retries + 1):
                try:
                    response = self._request("POST", self.products_endpoint, json=payload)
                    last_error = None
                    break
                except requests.exceptions.RequestException as post_error:
                    last_error = post_error

                    recoverable_timeout = isinstance(post_error, requests.exceptions.Timeout)
                    if recoverable_timeout:
                        recovered = _verify_or_recover_existing_product()
                        if recovered:
                            return recovered

                    if attempt >= max_create_retries:
                        raise

                    should_retry = isinstance(post_error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))
                    if not should_retry:
                        raise
                    time.sleep(retry_delay_seconds * attempt)

            if response is None and last_error is not None:
                raise last_error

            data = response.json()
            product_id = data.get("id")
            if not product_id:
                raise WooCommerceIntegrationError(
                    "WooCommerce không trả về product ID sau khi tạo sản phẩm. "
                    f"Phản hồi: {data}"
                )

            try:
                verified_product = self._request("GET", f"{self.products_endpoint}/{int(product_id)}").json() or {}
            except requests.exceptions.RequestException as verify_error:
                recovered = _verify_or_recover_existing_product()
                if recovered:
                    return recovered
                raise WooCommerceIntegrationError(
                    f"Tạo sản phẩm có ID {product_id} nhưng không đọc lại được từ WooCommerce: {self._sanitize_error_text(str(verify_error))}"
                )

            if not verified_product.get("id"):
                raise WooCommerceIntegrationError(
                    f"Không xác minh được product vừa tạo (ID {product_id})."
                )

            # Với sản phẩm tạo mới, vẫn cần ghi meta tiếng Trung nếu có dữ liệu ZH.
            if has_explicit_zh_fields or self._looks_like_chinese_text(name_zh, short_desc_zh, desc_zh):
                meta_updates = self._build_zh_meta_updates(
                    name=name,
                    short_description=short_description,
                    description=description,
                    name_zh=name_zh,
                    short_desc_zh=short_desc_zh,
                    desc_zh=desc_zh,
                    product_name_zh=product_name_zh,
                    product_short_desc_zh=product_short_desc_zh,
                    product_desc_zh=product_desc_zh,
                )
                if meta_updates:
                    try:
                        verified_product = self._update_product_meta_data(int(product_id), meta_updates)
                    except Exception:
                        # Không fail toàn bộ job nếu bước update meta ZH gặp lỗi tạm thời.
                        pass

            return {
                "product_id": int(product_id),
                "product_url": verified_product.get("permalink") or data.get("permalink"),
                "product_name": verified_product.get("name") or data.get("name"),
            }
        except requests.exceptions.RequestException as error:
            if _is_duplicate_sku_error(error):
                recovered_existing = _verify_or_recover_existing_product()
                if recovered_existing:
                    return recovered_existing

            message = f"Lỗi WooCommerce API: {self._sanitize_error_text(str(error))}"
            if hasattr(error, "response") and error.response is not None:
                detail = self._build_readable_error_detail(error.response)
                message += f" | Chi tiết: {self._sanitize_error_text(detail or error.response.text)}"
            raise WooCommerceIntegrationError(message)
