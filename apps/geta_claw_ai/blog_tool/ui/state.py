import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).parent.parent
ENV_FILE_PATH = ROOT_DIR / ".env"


def load_sites_config():
    config_path = ROOT_DIR / "sites.json"
    with open(config_path, encoding="utf-8-sig") as f:
        return json.load(f)


def _normalize_env_suffix(value: str) -> str:
    # Support both `site.com` and `site_com` suffix styles for env keys.
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def _resolve_site_env_value(site: dict, base_key: str) -> str:
    # Reload .env on read so updated credentials are picked up after edits.
    load_dotenv(dotenv_path=ENV_FILE_PATH, override=True)

    env_prefix = str(site.get("env_prefix") or site.get("name") or "").strip()
    if env_prefix:
        scoped_candidates = [
            f"{base_key}_{env_prefix}",
            f"{base_key}_{_normalize_env_suffix(env_prefix)}",
        ]
        for scoped_key in scoped_candidates:
            scoped_value = os.getenv(scoped_key)
            if scoped_value:
                return str(scoped_value).strip()

    fallback_value = os.getenv(base_key)
    return str(fallback_value).strip() if fallback_value else ""


def resolve_site_runtime_config(site: dict | None) -> dict | None:
    if not site:
        return None

    resolved = dict(site)
    resolved["wp_site_url"] = str(site.get("wp_site_url") or _resolve_site_env_value(site, "WP_SITE_URL") or "").strip()
    resolved["wp_username"] = str(site.get("wp_username") or _resolve_site_env_value(site, "WP_USERNAME") or "").strip()
    resolved["wp_app_password"] = str(site.get("wp_app_password") or _resolve_site_env_value(site, "WP_APP_PASSWORD") or "").strip()
    resolved["wc_consumer_key"] = str(site.get("wc_consumer_key") or _resolve_site_env_value(site, "WC_CONSUMER_KEY") or "").strip()
    resolved["wc_consumer_secret"] = str(site.get("wc_consumer_secret") or _resolve_site_env_value(site, "WC_CONSUMER_SECRET") or "").strip()
    return resolved

def get_site_options():
    sites = load_sites_config()
    return [site["name"] for site in sites]


def get_site_config_by_name(name):
    sites = load_sites_config()
    for site in sites:
        if site["name"] == name:
            return resolve_site_runtime_config(site)
    return None


def get_default_site_config():
    sites = load_sites_config()
    if not sites:
        return None
    return resolve_site_runtime_config(sites[0])
import threading

import streamlit as st


class TaskStateManager:
    """Singleton quản lý state an toàn luồng, tách biệt khỏi Streamlit widgets."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TaskStateManager, cls).__new__(cls)
                cls._instance._state_lock = threading.Lock()
                cls._instance._state = {
                    "is_running": False,
                    "should_stop": False,
                    "completed": 0,
                    "total": 1,
                    "success": 0,
                    "errors": [],
                    "feature": None,
                    "success_msg": "",
                    "success_ids": [],
                    "failed_ids": [],
                }
        return cls._instance

    def update(self, **kwargs):
        with self._state_lock:
            self._state.update(kwargs)

    def append_error(self, error_msg: str):
        with self._state_lock:
            self._state["errors"].append(error_msg)

    def append_success_id(self, article_id: int):
        with self._state_lock:
            success_ids = self._state.setdefault("success_ids", [])
            if article_id not in success_ids:
                success_ids.append(article_id)

    def append_failed_id(self, article_id: int):
        with self._state_lock:
            failed_ids = self._state.setdefault("failed_ids", [])
            if article_id not in failed_ids:
                failed_ids.append(article_id)

    def increment(self, success: bool = False):
        with self._state_lock:
            self._state["completed"] += 1
            if success:
                self._state["success"] += 1

    def get_snapshot(self) -> dict:
        with self._state_lock:
            return self._state.copy()


@st.cache_resource
def get_task_manager(cache_version: str = "2026-03-18-task-state-v3"):
    _ = cache_version
    return TaskStateManager()


def get_global_task_state() -> dict:
    """Return mutable GLOBAL_TASK_STATE stored in Streamlit session."""
    if "GLOBAL_TASK_STATE" not in st.session_state:
        st.session_state["GLOBAL_TASK_STATE"] = {
            "is_running": False,
            "should_stop": False,
            "completed": 0,
            "total": 1,
            "success": 0,
            "errors": [],
            "feature": None,
            "success_msg": "",
            "wc_last_result": None,
            "wc_success_links": [],
            "wc_failed_rows": [],
        }
    return st.session_state["GLOBAL_TASK_STATE"]


def reset_generate_result_state(task_manager: TaskStateManager) -> None:
    task_manager.update(
        feature=None,
        errors=[],
        success=0,
        success_msg="",
        success_ids=[],
        failed_ids=[],
        completed=0,
        total=1,
        should_stop=False,
        is_running=False,
    )


def reset_wc_result_state(global_task_state: dict) -> None:
    global_task_state["feature"] = None
    global_task_state["errors"] = []
    global_task_state["success"] = 0
    global_task_state["success_msg"] = ""
    global_task_state["wc_success_links"] = []
    global_task_state["wc_failed_rows"] = []
    global_task_state["wc_last_result"] = None
