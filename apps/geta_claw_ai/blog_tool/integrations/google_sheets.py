from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from integrations.google_sheets_mapping import HEADERS
from integrations.google_sheets_transport import GspreadSheetsTransport, WebhookSheetsTransport, column_letter


class GoogleSheetsIntegrationError(Exception):
    pass


@dataclass
class GoogleSheetsAppender:
    sheet_id: str | None = None
    worksheet_name: str = "Articles"
    webhook_batch_size: int = 50

    HEADERS = HEADERS

    @staticmethod
    def _column_letter(column_number: int) -> str:
        return column_letter(column_number)

    def __post_init__(self) -> None:
        load_dotenv()
        self.webhook_url = os.getenv("GOOGLE_APPS_SCRIPT_WEBHOOK_URL", "").strip()
        self.webhook_secret = os.getenv("GOOGLE_APPS_SCRIPT_SECRET", "").strip()
        self.worksheet_name = os.getenv("GOOGLE_SHEET_WORKSHEET_NAME", self.worksheet_name).strip() or self.worksheet_name
        self.webhook_batch_size = max(1, int(os.getenv("GOOGLE_APPS_SCRIPT_BATCH_SIZE", str(self.webhook_batch_size)) or self.webhook_batch_size))
        self.webhook_timeout_seconds = max(5, int(os.getenv("GOOGLE_APPS_SCRIPT_TIMEOUT_SECONDS", "15") or 15))
        self.webhook_max_retries = max(1, min(5, int(os.getenv("GOOGLE_APPS_SCRIPT_MAX_RETRIES", "2") or 2)))

        if self.webhook_url:
            self.mode = "webhook"
            self.transport = WebhookSheetsTransport(
                webhook_url=self.webhook_url,
                webhook_secret=self.webhook_secret,
                worksheet_name=self.worksheet_name,
                webhook_timeout_seconds=self.webhook_timeout_seconds,
                webhook_max_retries=self.webhook_max_retries,
            )
            return

        self.mode = "gspread"
        self.sheet_id = self.sheet_id or os.getenv("GOOGLE_SHEET_ID", "").strip()
        service_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        service_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

        self.transport = GspreadSheetsTransport(
            sheet_id=self.sheet_id,
            worksheet_name=self.worksheet_name,
            service_file=service_file,
            service_json=service_json,
        )

    def upsert_article_row(self, article, worksheet_name: str | None = None) -> None:
        self.transport.upsert_article_row(article, worksheet_name=worksheet_name)

    def append_article_row(self, worksheet_name: str, row_values: list[str]) -> None:
        self.transport.append_article_row(worksheet_name, row_values)

    def delete_rows_by_ids(self, article_ids: list[int], worksheet_name: str | None = None) -> int:
        return self.transport.delete_rows_by_ids(article_ids, worksheet_name=worksheet_name)

    def replace_all_articles(self, articles: list, worksheet_name: str | None = None) -> int:
        return self.transport.replace_all_articles(articles, worksheet_name=worksheet_name)

    def sync_all_articles(self, articles: list, worksheet_name: str | None = None) -> int:
        """Đồng bộ full dataset (full refresh) từ DB sang Google Sheets."""
        return self.replace_all_articles(articles, worksheet_name=worksheet_name)
