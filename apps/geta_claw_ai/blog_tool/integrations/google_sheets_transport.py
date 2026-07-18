from __future__ import annotations

import json
import time
from typing import Any

import gspread
import requests
from google.oauth2.service_account import Credentials

from integrations.google_sheets_mapping import HEADERS, article_to_row, article_to_row_dict


def column_letter(column_number: int) -> str:
    letters = ""
    current = max(1, int(column_number))
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


class WebhookSheetsTransport:
    def __init__(
        self,
        *,
        webhook_url: str,
        webhook_secret: str,
        worksheet_name: str,
        webhook_timeout_seconds: int,
        webhook_max_retries: int,
    ) -> None:
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.worksheet_name = worksheet_name
        self.webhook_timeout_seconds = webhook_timeout_seconds
        self.webhook_max_retries = webhook_max_retries

    def _post_webhook(self, action: str, payload: dict) -> None:
        from integrations.google_sheets import GoogleSheetsIntegrationError

        if not self.webhook_url:
            raise GoogleSheetsIntegrationError("Thiếu GOOGLE_APPS_SCRIPT_WEBHOOK_URL trong .env")

        request_payload = {
            "secret": self.webhook_secret,
            "action": action,
            "worksheet_name": payload.get("worksheet_name", self.worksheet_name),
        }
        request_payload.update(payload)

        headers = {
            "X-Webhook-Secret": self.webhook_secret,
            "X-API-Key": self.webhook_secret,
            "Authorization": f"Bearer {self.webhook_secret}",
        }

        payload_variants = [
            dict(request_payload),
            {**request_payload, "apiKey": self.webhook_secret},
            {**request_payload, "token": self.webhook_secret},
            {**request_payload, "webhook_secret": self.webhook_secret},
        ]

        last_error: str | None = None
        for variant in payload_variants:
            params = {
                "secret": self.webhook_secret,
                "apiKey": self.webhook_secret,
                "token": self.webhook_secret,
                "action": action,
                "worksheet_name": variant.get("worksheet_name", self.worksheet_name),
            }

            response = None
            last_request_exception: Exception | None = None
            for attempt in range(self.webhook_max_retries):
                try:
                    response = requests.post(
                        self.webhook_url,
                        json=variant,
                        headers=headers,
                        params=params,
                        timeout=self.webhook_timeout_seconds,
                    )
                    response.raise_for_status()
                    last_request_exception = None
                    break
                except requests.RequestException as error:
                    last_request_exception = error
                    if attempt >= (self.webhook_max_retries - 1):
                        break
                    time.sleep(1.2 * (attempt + 1))

            if last_request_exception is not None or response is None:
                raise GoogleSheetsIntegrationError(
                    f"Lỗi gọi Apps Script webhook: {str(last_request_exception)}"
                ) from last_request_exception

            if not response.text:
                return

            try:
                data = response.json()
            except ValueError:
                return

            if isinstance(data, dict) and data.get("ok") is False:
                error_text = str(data.get("error") or data).lower()
                last_error = str(data.get("error") or data)
                if "unauthorized" in error_text:
                    continue
                raise GoogleSheetsIntegrationError(f"Apps Script trả lỗi: {data.get('error') or data}")

            return

        if (last_error or "").lower() == "unauthorized":
            raise GoogleSheetsIntegrationError(
                "Apps Script trả lỗi: unauthorized. Kiểm tra SECRET trong Apps Script có khớp GOOGLE_APPS_SCRIPT_SECRET,"
                " đã Deploy phiên bản mới nhất, và URL deployment trong GOOGLE_APPS_SCRIPT_WEBHOOK_URL là URL mới nhất."
            )

        raise GoogleSheetsIntegrationError(
            f"Apps Script trả lỗi: {last_error or 'unknown error'}"
        )

    def upsert_article_row(self, article: Any, worksheet_name: str | None = None) -> None:
        row_dict = article_to_row_dict(article)
        self._post_webhook(
            "upsert",
            {
                "worksheet_name": worksheet_name or self.worksheet_name,
                "row": row_dict,
                "rows": [row_dict],
            },
        )

    def append_article_row(self, worksheet_name: str, row_values: list[str]) -> None:
        row_dict = dict(zip(HEADERS, row_values))
        self._post_webhook(
            "append",
            {
                "worksheet_name": worksheet_name,
                "row": row_dict,
                "rows": [row_dict],
            },
        )

    def delete_rows_by_ids(self, article_ids: list[int], worksheet_name: str | None = None) -> int:
        normalized_ids = [int(article_id) for article_id in article_ids if article_id is not None]
        if not normalized_ids:
            return 0
        self._post_webhook(
            "delete_ids",
            {
                "worksheet_name": worksheet_name or self.worksheet_name,
                "article_ids": normalized_ids,
            },
        )
        return len(normalized_ids)

    def replace_all_articles(self, articles: list, worksheet_name: str | None = None) -> int:
        rows = [article_to_row_dict(article) for article in articles]
        target_worksheet = worksheet_name or self.worksheet_name

        self._post_webhook(
            "replace_all",
            {
                "worksheet_name": target_worksheet,
                "headers": HEADERS,
                "rows": rows,
            },
        )
        return len(rows)


class GspreadSheetsTransport:
    def __init__(self, *, sheet_id: str, worksheet_name: str, service_file: str, service_json: str) -> None:
        from integrations.google_sheets import GoogleSheetsIntegrationError

        self.sheet_id = sheet_id
        self.worksheet_name = worksheet_name

        if not self.sheet_id:
            raise GoogleSheetsIntegrationError("Thiếu GOOGLE_SHEET_ID trong .env")

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ]

        if service_file:
            creds = Credentials.from_service_account_file(service_file, scopes=scopes)
        elif service_json:
            info = json.loads(service_json)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        else:
            raise GoogleSheetsIntegrationError(
                "Thiếu GOOGLE_SERVICE_ACCOUNT_FILE hoặc GOOGLE_SERVICE_ACCOUNT_JSON trong .env"
            )

        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(self.sheet_id)

    def _get_or_create_worksheet(self, worksheet_name: str | None = None):
        target_name = worksheet_name or self.worksheet_name
        try:
            worksheet = self.spreadsheet.worksheet(target_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(title=target_name, rows=1000, cols=30)

        self._ensure_headers_and_filters(worksheet)
        return worksheet

    def _ensure_headers_and_filters(self, worksheet) -> None:
        current_headers = worksheet.row_values(1)
        end_column = column_letter(len(HEADERS))
        if current_headers != HEADERS:
            worksheet.update(f"A1:{end_column}1", [HEADERS], value_input_option="USER_ENTERED")

        worksheet.freeze(rows=1)
        worksheet.set_basic_filter()

    def upsert_article_row(self, article: Any, worksheet_name: str | None = None) -> None:
        worksheet = self._get_or_create_worksheet(worksheet_name)
        row_values = article_to_row(article)
        try:
            id_cell = worksheet.find(str(article.id), in_column=1)
        except gspread.exceptions.CellNotFound:
            id_cell = None

        if id_cell:
            row_index = id_cell.row
            end_column = column_letter(len(HEADERS))
            worksheet.update(f"A{row_index}:{end_column}{row_index}", [row_values], value_input_option="USER_ENTERED")
        else:
            worksheet.append_row(row_values, value_input_option="USER_ENTERED")

    def append_article_row(self, worksheet_name: str, row_values: list[str]) -> None:
        worksheet = self._get_or_create_worksheet(worksheet_name)
        worksheet.append_row(row_values, value_input_option="USER_ENTERED")

    def delete_rows_by_ids(self, article_ids: list[int], worksheet_name: str | None = None) -> int:
        worksheet = self._get_or_create_worksheet(worksheet_name)
        normalized_ids = {str(int(article_id)) for article_id in article_ids if article_id is not None}
        if not normalized_ids:
            return 0

        id_column_values = worksheet.col_values(1)
        if len(id_column_values) <= 1:
            return 0

        rows_to_delete: list[int] = []
        for row_index, row_id_value in enumerate(id_column_values[1:], start=2):
            row_id = (row_id_value or "").strip()
            if row_id in normalized_ids:
                rows_to_delete.append(row_index)

        if not rows_to_delete:
            return 0

        sorted_rows = sorted(rows_to_delete)
        ranges: list[tuple[int, int]] = []
        start = sorted_rows[0]
        end = sorted_rows[0]

        for row_index in sorted_rows[1:]:
            if row_index == end + 1:
                end = row_index
            else:
                ranges.append((start, end))
                start = row_index
                end = row_index
        ranges.append((start, end))

        requests = []
        for start_row, end_row in sorted(ranges, reverse=True):
            requests.append(
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "ROWS",
                            "startIndex": start_row - 1,
                            "endIndex": end_row,
                        }
                    }
                }
            )

        self.spreadsheet.batch_update({"requests": requests})

        return len(rows_to_delete)

    def replace_all_articles(self, articles: list, worksheet_name: str | None = None) -> int:
        worksheet = self._get_or_create_worksheet(worksheet_name)
        worksheet.clear()
        self._ensure_headers_and_filters(worksheet)

        rows = [article_to_row(article) for article in articles]
        if rows:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        return len(rows)