import os
import json
import re
import base64
import traceback
import time
from datetime import datetime
from unidecode import unidecode
from dotenv import load_dotenv
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception,
    retry_if_exception_type,
)
from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
from langchain_core.messages import SystemMessage, HumanMessage

from llm_engine.prompts import (
    build_seo_system_prompt,
    build_seo_user_prompt,
    build_service_link_pairs,
)

# Load các biến môi trường từ file .env
load_dotenv()

GEMINI_GENERATE_RETRY_ATTEMPTS = max(1, int(os.getenv("GEMINI_GENERATE_RETRY_ATTEMPTS", "3") or 3))

class OutputParsingError(Exception):
    """Custom Exception khi LLM trả về format không chuẩn"""
    pass

class SEOAgent:
    @staticmethod
    def _is_retryable_llm_exception(error: Exception) -> bool:
        """
        Retry cho lỗi tạm thời ở tầng model/network, gồm cả timeout và parse/schema từ model.
        Một số lỗi output malformed chỉ xảy ra ngẫu nhiên theo từng lần gọi.
        """
        normalized = str(error or "").lower()
        if isinstance(error, OutputParsingError):
            return True
        if isinstance(error, (json.JSONDecodeError, KeyError, TypeError, ValueError)):
            return False
        if isinstance(error, TimeoutError):
            return True
        if "resource_exhausted" in normalized or "quota exceeded" in normalized:
            return False
        if "429" in normalized and "rate" in normalized:
            return False
        if "deadline exceeded" in normalized or "timed out" in normalized or "timeout" in normalized:
            return True
        return True

    def __init__(self, model_name: str | None = None, temperature: float | None = None):
        """Khởi tạo AI Agent với cấu hình Gemini Model"""
        resolved_model = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        resolved_temperature = float(temperature if temperature is not None else os.getenv("GEMINI_TEMPERATURE", "0.35"))
        self.request_timeout_seconds = max(15, int(os.getenv("GEMINI_REQUEST_TIMEOUT_SECONDS", "50") or 50))

        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

        self._api_keys = self._load_google_api_keys()
        if not self._api_keys:
            raise ValueError(
                "Lỗi: Không tìm thấy API key. Hãy khai báo GOOGLE_API_KEY hoặc GOOGLE_API_KEYS / GOOGLE_API_KEY_1..N"
            )

        self._llm_clients = [
            ChatGoogleGenerativeAI(
                model=resolved_model,
                temperature=resolved_temperature,
                max_tokens=8192,
                google_api_key=api_key,
                safety_settings=safety_settings,
                timeout=self.request_timeout_seconds,
            )
            for api_key in self._api_keys
        ]
        self._active_llm_index = 0
        # Backward compatibility in case any code path still accesses self.llm directly.
        self.llm = self._llm_clients[self._active_llm_index]
        self.enable_article_review = str(os.getenv("GEMINI_ENABLE_ARTICLE_REVIEW", "false")).strip().lower() in {
            "1", "true", "yes", "on"
        }
        # Optional strict rewrite pass. Off by default to avoid long hidden extra LLM calls.
        self.enable_language_rewrite = str(os.getenv("GEMINI_ENABLE_LANGUAGE_REWRITE", "false")).strip().lower() in {
            "1", "true", "yes", "on"
        }
        self._quota_usage = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    @staticmethod
    def _load_google_api_keys() -> list[str]:
        keys: list[str] = []

        # 1) Single key style
        primary = str(os.getenv("GOOGLE_API_KEY", "") or "").strip()
        if primary:
            keys.append(primary)

        # 2) Comma/newline separated style
        raw_multi = str(os.getenv("GOOGLE_API_KEYS", "") or "")
        if raw_multi.strip():
            for item in re.split(r"[,;\n\r]+", raw_multi):
                value = str(item or "").strip()
                if value:
                    keys.append(value)

        # 3) Indexed style GOOGLE_API_KEY_1..GOOGLE_API_KEY_50
        for i in range(1, 51):
            value = str(os.getenv(f"GOOGLE_API_KEY_{i}", "") or "").strip()
            if value:
                keys.append(value)

        deduped: list[str] = []
        seen: set[str] = set()
        for key in keys:
            if key not in seen:
                seen.add(key)
                deduped.append(key)
        return deduped

    @staticmethod
    def _is_quota_rotation_error(error: Exception) -> bool:
        normalized = str(error or "").lower()
        markers = [
            "resource_exhausted",
            "quota exceeded",
            "quota",
            "rate limit",
            "429",
            "too many requests",
        ]
        return any(marker in normalized for marker in markers)

    def _invoke_llm(self, messages):
        total_clients = len(self._llm_clients)
        if total_clients <= 0:
            raise ValueError("Không có Gemini client khả dụng để gọi API.")

        last_error: Exception | None = None
        start_index = self._active_llm_index

        for step in range(total_clients):
            index = (start_index + step) % total_clients
            client = self._llm_clients[index]
            try:
                response = client.invoke(messages)
                if index != self._active_llm_index:
                    self._active_llm_index = index
                    self.llm = self._llm_clients[self._active_llm_index]
                    self._safe_log(f"[*] Switched Gemini API key to slot {index + 1}/{total_clients}")
                return response
            except Exception as error:
                last_error = error
                should_try_next = self._is_quota_rotation_error(error) and step < (total_clients - 1)
                if should_try_next:
                    self._safe_log(
                        f"[!] Gemini key slot {index + 1}/{total_clients} quota/rate limited. Trying next key..."
                    )
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Gemini invoke thất bại nhưng không có thông tin lỗi.")

    @staticmethod
    def _safe_log(message: str) -> None:
        text = str(message or "")
        try:
            print(text)
        except UnicodeEncodeError:
            fallback = text.encode("ascii", "ignore").decode("ascii", "ignore")
            print(fallback)

    def _reset_usage_if_new_day(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if self._quota_usage.get("date") != today:
            self._quota_usage = {
                "date": today,
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

    def _extract_usage(self, response) -> dict:
        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens = int(usage.get("input_tokens") or usage.get("prompt_token_count") or 0)
        output_tokens = int(usage.get("output_tokens") or usage.get("candidates_token_count") or 0)
        total_tokens = int(usage.get("total_tokens") or usage.get("total_token_count") or 0)

        if total_tokens <= 0:
            response_metadata = getattr(response, "response_metadata", {}) or {}
            token_usage = response_metadata.get("token_usage", {}) if isinstance(response_metadata, dict) else {}
            input_tokens = input_tokens or int(token_usage.get("prompt_tokens") or 0)
            output_tokens = output_tokens or int(token_usage.get("completion_tokens") or 0)
            total_tokens = int(token_usage.get("total_tokens") or 0)

        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens

        return {
            "input_tokens": max(0, input_tokens),
            "output_tokens": max(0, output_tokens),
            "total_tokens": max(0, total_tokens),
        }

    def _record_quota_usage(self, response):
        self._reset_usage_if_new_day()
        usage = self._extract_usage(response)
        self._quota_usage["requests"] += 1
        self._quota_usage["input_tokens"] += usage["input_tokens"]
        self._quota_usage["output_tokens"] += usage["output_tokens"]
        self._quota_usage["total_tokens"] += usage["total_tokens"]

    def get_quota_snapshot(self) -> dict:
        self._reset_usage_if_new_day()
        request_limit = int(os.getenv("GEMINI_DAILY_REQUEST_LIMIT", "0") or 0)
        token_limit = int(os.getenv("GEMINI_DAILY_TOKEN_LIMIT", "0") or 0)

        used_requests = int(self._quota_usage.get("requests", 0))
        used_tokens = int(self._quota_usage.get("total_tokens", 0))

        return {
            "date": self._quota_usage.get("date"),
            "requests_used": used_requests,
            "requests_limit": request_limit,
            "requests_remaining": max(0, request_limit - used_requests) if request_limit > 0 else None,
            "tokens_used": used_tokens,
            "tokens_limit": token_limit,
            "tokens_remaining": max(0, token_limit - used_tokens) if token_limit > 0 else None,
            "input_tokens": int(self._quota_usage.get("input_tokens", 0)),
            "output_tokens": int(self._quota_usage.get("output_tokens", 0)),
        }

    def _clean_json_output(self, text: str) -> str:
        """Hàm làm sạch output của LLM đề phòng model bọc JSON trong markdown code block (```json)"""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _extract_json_object(self, text: str) -> str:
        """Trích block JSON đầu tiên từ output nếu model kèm text thừa."""
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return text
        return text[start : end + 1]

    def _parse_llm_json(self, raw_text: str) -> dict:
        cleaned_text = self._clean_json_output(raw_text)

        # Lần 1: parse chuẩn
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass

        # Lần 2: parse với strict=False để chấp nhận control character trong string
        try:
            return json.loads(cleaned_text, strict=False)
        except json.JSONDecodeError:
            pass

        # Lần 3: trích khối JSON rồi parse lại
        extracted = self._extract_json_object(cleaned_text)
        try:
            return json.loads(extracted, strict=False)
        except json.JSONDecodeError as e:
            # Làm sạch thêm các control chars hiếm gặp trước khi báo lỗi cuối
            sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", extracted)
            try:
                return json.loads(sanitized, strict=False)
            except json.JSONDecodeError:
                raise OutputParsingError(f"Model không trả về chuẩn JSON: {str(e)}") from e

    def _parse_keyword_suggestions(self, raw_text: str) -> list[str]:
        cleaned_text = self._clean_json_output(raw_text)
        try:
            parsed = json.loads(cleaned_text, strict=False)
        except json.JSONDecodeError:
            extracted = self._extract_json_object(cleaned_text)
            parsed = json.loads(extracted, strict=False)

        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

        if isinstance(parsed, dict):
            keywords = parsed.get("keywords", [])
            if isinstance(keywords, list):
                return [str(item).strip() for item in keywords if str(item).strip()]

        raise OutputParsingError("Output gợi ý từ khóa không đúng định dạng JSON.")

    def _parse_string_list(self, raw_text: str, list_key: str) -> list[str]:
        cleaned_text = self._clean_json_output(raw_text)
        try:
            parsed = json.loads(cleaned_text, strict=False)
        except json.JSONDecodeError:
            extracted = self._extract_json_object(cleaned_text)
            parsed = json.loads(extracted, strict=False)

        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

        if isinstance(parsed, dict):
            values = parsed.get(list_key, [])
            if isinstance(values, list):
                return [str(item).strip() for item in values if str(item).strip()]

        return []

    def _review_generated_article(self, keyword: str, language: str, article_payload: dict, site_name: str | None = None) -> dict:
        site_name_lower = str(site_name or "").strip().lower()
        if site_name_lower == "innhanhgeta.com":
            local_rule = (
                "2) Must be relevant to printing products, materials, finishing, and product categories for GETA's printing site; "
                "internal links should point to a relevant category or product on the current site."
            )
            style_rule = (
                "6) Style: Vietnamese must be practical and consultative for in ấn; Simplified Chinese must stay professional and B2B."
            )
            conversion_rule = (
                "8) Reflect printing-consultation positioning with relevant product/category cross-sell opportunities when appropriate."
            )
        elif site_name_lower == "quangcao.getagroup.vn":
            local_rule = (
                "2) Must be relevant to advertising, brand visibility, materials, and product categories for GETA's advertising site; "
                "internal links should point to a relevant category or product on the current site."
            )
            style_rule = (
                "6) Style: Vietnamese must be practical and consultative for quảng cáo/in ấn; Simplified Chinese must stay professional and B2B."
            )
            conversion_rule = (
                "8) Reflect advertising-consultation positioning with relevant product/category cross-sell opportunities when appropriate."
            )
        else:
            local_rule = "2) Must be relevant to the selected site and its taxonomy only."
            style_rule = (
                "6) Style: Vietnamese must be technically clear; Simplified Chinese must be professional B2B and remain aligned with the selected site."
            )
            conversion_rule = (
                "8) Reflect the selected site's positioning with relevant cross-sell opportunities when appropriate."
            )

        review_system = (
            "You are an SEO content quality reviewer. "
            "Return ONLY JSON with this exact schema: "
            "{\"pass\": true/false, \"issues\": [\"...\"], \"fix_instructions\": [\"...\"]}."
        )
        review_user = (
            f"Focus keyword: {keyword}\n"
            f"Language: {language}\n"
            "Checklist:\n"
            "1) Target audience must fit mainstream Vietnamese, mainstream Simplified Chinese, SMEs.\n"
            f"{local_rule}\n"
            "3) Chinese output: title 25-30 chars, meta 75-80 chars, pinyin hyphen slug; Vietnamese output: title 50-60 chars, meta 120-155 chars.\n"
            "4) Body should be >= 900 words with H1 + 3-6 H2 + practical H3 and a short FAQ section.\n"
            "5) Include at least 1 internal relative link and 1 trustworthy external https link.\n"
            f"{style_rule}\n"
            "7) Strict language purity: Vietnamese output must be only Vietnamese; Simplified Chinese output must be only Simplified Chinese. No mixed-language phrases except URLs, phone numbers, and proper nouns (Telegram/WeChat/Zalo/Google).\n"
            f"{conversion_rule}\n"
            "9) Avoid keyword stuffing and unverifiable claims.\n"
            "Article JSON:\n"
            f"{json.dumps(article_payload, ensure_ascii=False)}"
        )

        response = self._invoke_llm([
            SystemMessage(content=review_system),
            HumanMessage(content=review_user),
        ])
        self._record_quota_usage(response)
        parsed = self._parse_llm_json(response.content)
        return {
            "pass": bool(parsed.get("pass", False)),
            "issues": parsed.get("issues", []) if isinstance(parsed.get("issues", []), list) else [],
            "fix_instructions": (
                parsed.get("fix_instructions", []) if isinstance(parsed.get("fix_instructions", []), list) else []
            ),
        }

    def _regenerate_article_with_fixes(
        self,
        keyword: str,
        context: str,
        language: str,
        previous_article: dict,
        fix_instructions: list[str],
        site_name: str | None = None,
    ) -> dict:
        fix_system = build_seo_system_prompt(language=language, site_name=site_name)
        fix_user = (
            f"Focus Keyword: {keyword}\n"
            f"Additional Context/Tone: {context}\n"
            f"Output Language: {language}\n\n"
            "Previous JSON output to improve:\n"
            f"{json.dumps(previous_article, ensure_ascii=False)}\n\n"
            "Must fix these checklist issues:\n"
            + "\n".join([f"- {item}" for item in fix_instructions])
            + "\n\nReturn ONLY valid JSON with schema: seo_metadata + content_markdown."
        )

        response = self._invoke_llm([
            SystemMessage(content=fix_system),
            HumanMessage(content=fix_user),
        ])
        self._record_quota_usage(response)
        return self._parse_llm_json(response.content)

    def _repair_malformed_article_json(self, raw_output: str, language: str, site_name: str | None = None) -> dict:
        repair_system = (
            "You are a strict JSON repair assistant. "
            "Convert the provided text into valid JSON only, matching this schema exactly: "
            "{\"seo_metadata\":{\"title\":\"...\",\"meta_description\":\"...\",\"slug\":\"...\"},\"content_markdown\":\"...\"}. "
            "Do not add commentary."
        )
        repair_user = (
            f"Output language: {language}\n"
            "Malformed input to repair:\n"
            f"{raw_output}"
        )

        response = self._invoke_llm([
            SystemMessage(content=repair_system),
            HumanMessage(content=repair_user),
        ])
        self._record_quota_usage(response)
        return self._parse_llm_json(response.content)

    @staticmethod
    def _extract_primary_keyword(raw_keyword: str) -> str:
        normalized = (raw_keyword or "").strip()
        if not normalized:
            return ""
        parts = [part.strip() for part in re.split(r"[,;\n\|、，；]+", normalized) if part.strip()]
        return parts[0] if parts else normalized

    @staticmethod
    def _fit_text_length(text: str, min_len: int, max_len: int, pad_fragment: str, separator: str = " ") -> str:
        value = (text or "").strip()
        if len(value) < min_len:
            joiner = separator if value else ""
            while len(value) < min_len:
                value = f"{value}{joiner}{pad_fragment}".strip()
                joiner = separator
        if len(value) > max_len:
            clipped = value[:max_len]
            if separator == " " and " " in clipped:
                by_word = clipped.rsplit(" ", 1)[0].strip()
                if len(by_word) >= max(min_len - 5, 8):
                    clipped = by_word
            value = clipped.rstrip(" ,;:-&|/")
        return value

    @staticmethod
    def _normalize_chinese_locales(text: str) -> str:
        value = str(text or "")
        locale_patterns = [
            (r"m[ộo]c\s*b[àa]i", "木牌"),
            (r"bavet", "巴域"),
            (r"xa\s*m[aá]t", "下马"),
        ]
        for pattern, replacement in locale_patterns:
            value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
        return value

    @staticmethod
    def _strip_cjk_characters(text: str) -> str:
        value = str(text or "")
        value = re.sub(r"[\u4e00-\u9fff]", " ", value)
        # Preserve newlines by only deduplicating horizontal whitespace
        value = re.sub(r"[ \t]+", " ", value).strip()
        return value

    @staticmethod
    def _build_pinyin_slug(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return "seo-article"
        romanized = unidecode(raw)
        slug = romanized.lower()
        slug = re.sub(r"[^a-z0-9\s-]", " ", slug)
        slug = re.sub(r"[_\s]+", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug[:75] if slug else "seo-article"

    @staticmethod
    def _normalize_vietnamese_style_phrases(text: str) -> str:
        value = str(text or "")
        replacements = {
            "mô hình dịch vụ một cửa": "dịch vụ trọn gói, đồng bộ",
            "dịch vụ một cửa": "dịch vụ trọn gói",
            "một cửa": "trọn gói",
        }
        for source, target in replacements.items():
            value = re.sub(re.escape(source), target, value, flags=re.IGNORECASE)
        return value

    @staticmethod
    def _count_markdown_links(markdown_text: str) -> tuple[int, int]:
        links = re.findall(r"\[[^\]]+\]\(([^\)]+)\)", markdown_text or "")
        internal = 0
        external = 0
        for url in links:
            lower_url = (url or "").strip().lower()
            if lower_url.startswith("http://") or lower_url.startswith("https://"):
                external += 1
            elif lower_url.startswith("/"):
                internal += 1
        return internal, external

    @staticmethod
    def _normalize_search_text(text: str) -> str:
        normalized = unidecode(str(text or "")).lower()
        normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _detect_service_slug_from_intent(self, keyword: str) -> str:
        normalized_keyword = self._normalize_search_text(keyword)
        raw_keyword = str(keyword or "").lower()
        if not normalized_keyword and not raw_keyword:
            return ""

        def _has_any(patterns: list[str]) -> bool:
            for pattern in patterns:
                normalized_pattern = self._normalize_search_text(pattern)
                if normalized_pattern and normalized_pattern in normalized_keyword:
                    return True
                raw_pattern = str(pattern).strip().lower()
                if raw_pattern and any(ord(ch) > 127 for ch in raw_pattern) and raw_pattern in raw_keyword:
                    return True
            return False

        # Priority order for disambiguation: choose the most specific commercial intent first.
        intent_rules: list[tuple[str, list[str]]] = [
            ("menu-design", [
                "menu", "thuc don", "menu nha hang", "menu quan cafe", "菜单", "菜谱", "菜单设计", "菜单印刷",
            ]),
            ("interior-fit-out", [
                "thiet ke noi that", "trang tri noi that", "trang tri", "fit out", "interior design",
                "室内设计", "软装", "空间设计", "装饰",
            ]),
            ("restaurant-cafe-construction", [
                "thi cong quan", "thi cong nha hang", "quan cafe", "quan an", "quan bar",
                "咖啡厅", "餐厅", "台球厅", "店铺装修", "商业改造",
            ]),
            ("furniture-factory", [
                "do go", "go cong nghiep", "ban ghe", "tu bep", "giuong tu", "家具", "定制家具", "木工", "柜子",
            ]),
            ("professional-painting", [
                "son nuoc", "son tuong", "batch mat", "chong tham", "刷漆", "油漆", "批灰", "墙面", "防水",
            ]),
            ("mep-installation", [
                "he thong dien", "dien nuoc", "dien lanh", "mep", "电路", "水电", "机电", "安装维修",
            ]),
            ("renovation-repair", [
                "cai tao", "sua chua", "nha cu", "renovation", "repair", "翻新", "维修", "旧房", "改造",
            ]),
            ("advertising-signboards", [
                "bang hieu", "quang cao", "chu noi", "hop den", "招牌", "广告牌", "发光字", "灯箱",
            ]),
        ]

        for slug, patterns in intent_rules:
            if _has_any(patterns):
                return slug
        return ""

    def _select_service_link_pair(self, keyword: str, content_markdown: str) -> dict[str, str]:
        pairs = build_service_link_pairs()
        if not pairs:
            return {}

        slug_lookup = {str(item.get("slug") or "").lower(): item for item in pairs}

        # Prefer deterministic intent-based routing from keyword/category phrase.
        detected_slug = self._detect_service_slug_from_intent(keyword)
        if detected_slug:
            resolved = slug_lookup.get(detected_slug)
            if resolved:
                return resolved

        # Fallback to existing model-inserted link only when no clear intent is detected.
        url_slug_matches = re.findall(
            r"https?://mocbaibavet\.com(?:/vi)?/services/([a-z0-9-]+)",
            str(content_markdown or ""),
            flags=re.IGNORECASE,
        )
        for matched_slug in url_slug_matches:
            resolved = slug_lookup.get(str(matched_slug).lower())
            if resolved:
                return resolved

        normalized_keyword = self._normalize_search_text(keyword)
        normalized_content = self._normalize_search_text(str(content_markdown or "")[:4000])
        scoring_text = f"{normalized_keyword} {normalized_content}".strip()
        raw_text = str(keyword or "").lower()

        service_hints: dict[str, list[str]] = {
            "advertising-signboards": [
                "bang hieu", "quang cao", "led", "chu noi", "hop den",
                "招牌", "广告牌", "发光字", "灯箱", "招牌制作",
            ],
            "mep-installation": [
                "he thong dien", "dien nuoc", "dien lanh", "co dien", "mep",
                "电路", "电线", "机电", "水电", "安装维修",
            ],
            "menu-design": [
                "menu", "thuc don", "menu mica", "menu nha hang", "in menu",
                "菜单", "菜谱", "菜单设计", "菜单印刷",
            ],
            "furniture-factory": [
                "ban ghe", "tu bep", "giuong tu", "go cong nghiep",
                "家具", "定制家具", "木工", "柜子", "沙发",
            ],
            "professional-painting": [
                "son nuoc", "son tuong", "batch mat", "tram trat", "chong tham",
                "刷漆", "油漆", "批灰", "墙面", "防水",
            ],
            "renovation-repair": [
                "cai tao", "sua chua", "nha cu", "nang cap", "hoan thien",
                "翻新", "维修", "旧房", "改造", "修缮",
            ],
            "restaurant-cafe-construction": [
                "thi cong quan", "cafe", "nha hang", "quan an", "bar",
                "咖啡厅", "餐厅", "台球厅", "店铺装修", "商业改造",
            ],
            "interior-fit-out": [
                "thiet ke noi that", "trang tri", "fit out", "bo tri khong gian", "decor",
                "室内设计", "软装", "空间设计", "装饰", "陈列",
            ],
        }

        if not normalized_keyword:
            return pairs[0]

        best_pair = pairs[0]
        best_score = -1
        for pair in pairs:
            score = 0
            tokens = set()
            for source in (pair.get("slug", ""), pair.get("vi_name", ""), pair.get("zh_name", "")):
                normalized_source = self._normalize_search_text(source)
                for token in normalized_source.split():
                    if len(token) >= 2:
                        tokens.add(token)

            slug_text = self._normalize_search_text(pair.get("slug", ""))
            if slug_text and slug_text in scoring_text:
                score += 5

            for token in tokens:
                if token in scoring_text:
                    score += 1

            for hint in service_hints.get(str(pair.get("slug") or ""), []):
                normalized_hint = self._normalize_search_text(hint)
                if normalized_hint and normalized_hint in scoring_text:
                    score += 3
                raw_hint = str(hint).strip().lower()
                if raw_hint and any(ord(ch) > 127 for ch in raw_hint) and raw_hint in raw_text:
                    score += 3

            if score > best_score:
                best_score = score
                best_pair = pair

        return best_pair

    def _ensure_service_backlink_pair(self, content_markdown: str, keyword: str, is_chinese: bool) -> str:
        content = str(content_markdown or "").rstrip()
        if not content:
            return content

        pair = self._select_service_link_pair(keyword=keyword, content_markdown=content)
        if not pair:
            return content

        vi_url = pair.get("vi_url", "")
        zh_url = pair.get("zh_url", "")
        if not vi_url or not zh_url:
            return content

        vi_anchor_text, zh_anchor_text = self._build_service_anchor_labels(pair, is_chinese=is_chinese)
        content, matched_link_count = self._normalize_whitelisted_service_links(
            content=content,
            vi_url=vi_url,
            zh_url=zh_url,
            vi_anchor_text=vi_anchor_text,
            zh_anchor_text=zh_anchor_text,
            is_chinese=is_chinese,
        )

        if matched_link_count >= 2 and vi_url in content and zh_url in content:
            return content

        if is_chinese:
            addition = f"配套服务参考：[{zh_anchor_text}]({zh_url}) | [{vi_anchor_text}]({vi_url})。"
        else:
            addition = f"Dich vu lien quan theo cap: [{vi_anchor_text}]({vi_url}) | [{zh_anchor_text}]({zh_url})."

        return self._insert_links_into_body_section(content=content, links_line=addition)

    @staticmethod
    def _insert_links_into_body_section(content: str, links_line: str) -> str:
        if not content or not links_line:
            return content

        lines = content.splitlines()
        first_h2_index = -1
        for idx, line in enumerate(lines):
            if re.match(r"^##\s+", line.strip()):
                first_h2_index = idx
                break

        if first_h2_index < 0:
            return f"{content}\n\n{links_line}".strip()

        first_content_line = -1
        for idx in range(first_h2_index + 1, len(lines)):
            stripped = lines[idx].strip()
            if not stripped:
                continue
            if re.match(r"^##\s+", stripped):
                break
            first_content_line = idx
            break

        if first_content_line < 0:
            insert_at = min(first_h2_index + 1, len(lines))
            lines.insert(insert_at, "")
            lines.insert(insert_at + 1, links_line)
            return "\n".join(lines).rstrip()

        insert_at = first_content_line + 1
        while insert_at < len(lines):
            stripped = lines[insert_at].strip()
            if not stripped:
                break
            if re.match(r"^##\s+", stripped):
                break
            insert_at += 1

        lines.insert(insert_at, "")
        lines.insert(insert_at + 1, links_line)
        return "\n".join(lines).rstrip()

    @staticmethod
    def _build_service_anchor_labels(pair: dict[str, str], is_chinese: bool) -> tuple[str, str]:
        vi_name = str(pair.get("vi_name") or "Dich vu tieng Viet").strip()
        zh_name = str(pair.get("zh_name") or "中文服务页面").strip()
        if is_chinese:
            return f"{zh_name}（越南语）", zh_name
        return vi_name, f"{vi_name} - tiếng Trung"

    @classmethod
    def _normalize_anchor_text_for_url(cls, content: str, url: str, replacement_text: str) -> str:
        if not content or not url or not replacement_text:
            return content

        escaped_url = re.escape(url)

        markdown_anchor = re.compile(
            rf"\[[^\]]*\]\(\s*{escaped_url}\s*\)",
            flags=re.IGNORECASE,
        )
        content = markdown_anchor.sub(f"[{replacement_text}]({url})", content)

        html_anchor = re.compile(
            rf"(<a\b[^>]*href=[\"']{escaped_url}[\"'][^>]*>).*?(</a>)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        content = html_anchor.sub(rf"\1{replacement_text}\2", content)

        return content

    @classmethod
    def _normalize_whitelisted_service_links(
        cls,
        content: str,
        vi_url: str,
        zh_url: str,
        vi_anchor_text: str,
        zh_anchor_text: str,
        is_chinese: bool,
    ) -> tuple[str, int]:
        if not content:
            return content, 0

        service_link_pattern = re.compile(
            r"<a\b[^>]*href=[\"']https://mocbaibavet\.com(?:/vi)?/services/[a-z0-9-]+[\"'][^>]*>.*?</a>|\[[^\]]*\]\(\s*https://mocbaibavet\.com(?:/vi)?/services/[a-z0-9-]+\s*\)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        matches = list(service_link_pattern.finditer(content))
        if not matches:
            return content, 0

        ordered_replacements = (
            [f"[{zh_anchor_text}]({zh_url})", f"[{vi_anchor_text}]({vi_url})"]
            if is_chinese
            else [f"[{vi_anchor_text}]({vi_url})", f"[{zh_anchor_text}]({zh_url})"]
        )

        parts: list[str] = []
        cursor = 0
        applied = 0
        for index, match in enumerate(matches):
            parts.append(content[cursor:match.start()])
            if index < 2:
                parts.append(ordered_replacements[index])
                applied += 1
            else:
                plain_text = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", match.group(0), flags=re.IGNORECASE | re.DOTALL)
                plain_text = re.sub(r"\[([^\]]*)\]\(\s*https://mocbaibavet\.com(?:/vi)?/services/[a-z0-9-]+\s*\)", r"\1", plain_text, flags=re.IGNORECASE)
                parts.append(plain_text)
            cursor = match.end()

        parts.append(content[cursor:])
        return "".join(parts), applied

    @staticmethod
    def _repair_empty_anchor_text(content: str, url: str, replacement_text: str) -> str:
        if not content or not url or not replacement_text:
            return content

        escaped_url = re.escape(url)

        # Markdown empty anchor: [](url) or [   ](url)
        markdown_empty_anchor = re.compile(
            rf"\[\s*\]\(\s*{escaped_url}\s*\)",
            flags=re.IGNORECASE,
        )
        content = markdown_empty_anchor.sub(f"[{replacement_text}]({url})", content)

        # HTML empty anchor: <a ... href="url" ...>   </a>
        html_empty_anchor = re.compile(
            rf"(<a\b[^>]*href=[\"']{escaped_url}[\"'][^>]*>)\s*(</a>)",
            flags=re.IGNORECASE,
        )
        content = html_empty_anchor.sub(rf"\1{replacement_text}\2", content)

        return content

    @staticmethod
    def _contact_footer(is_chinese: bool) -> str:
        if is_chinese:
            return (
                "## 联系方式\n"
                "- 木牌 - 巴域工厂地址: 柬埔寨巴域市 333X+GHG\n"
                "- 服务热线 / Zalo: 0919 511 911 - 076 7711 532\n"
                "- Telegram: [@mocbaibavet6789](https://t.me/mocbaibavet6789)\n"
                "- 微信: [cuongeta](https://u.wechat.com/kIr2BhnkmQGx9e5WQNjvXdA?s=2)（点击链接联系）"
            )
        return (
            "## Thông tin liên hệ\n"
            "- Địa chỉ xưởng tại Mộc Bài: 333X+GHG, Krong Bavet, Cambodia\n"
            "- Hotline/Zalo: 0919 511 911 - 076 7711 532\n"
            "- Telegram: [@mocbaibavet6789](https://t.me/mocbaibavet6789)\n"
            "- WeChat: [cuonggeta](https://u.wechat.com/kIr2BhnkmQGx9e5WQNjvXdA?s=2)"
        )

    def _ensure_contact_footer(self, content_markdown: str, is_chinese: bool) -> str:
        content = str(content_markdown or "").rstrip()
        footer = self._contact_footer(is_chinese=is_chinese)
        if not content:
            return footer
        normalized_content = re.sub(r"\s+", " ", content).lower()
        marker = "333x+ghg"
        if marker in normalized_content and content.endswith(footer):
            return content
        return f"{content}\n\n{footer}"

    def _post_optimize_article_payload(self, payload: dict, keyword: str, language: str, site_name: str | None = None) -> dict:
        data = dict(payload or {})
        seo_metadata = dict(data.get("seo_metadata") or {})
        content_markdown = str(data.get("content_markdown") or "").strip()

        primary_keyword = self._extract_primary_keyword(keyword)
        language_lower = (language or "").lower()
        is_chinese = "chinese" in language_lower or "giản thể" in language_lower or "简体" in language_lower

        title_seed = seo_metadata.get("title") or primary_keyword
        meta_seed = seo_metadata.get("meta_description") or primary_keyword

        if is_chinese:
            title_seed = self._normalize_chinese_locales(str(title_seed))
            meta_seed = self._normalize_chinese_locales(str(meta_seed))
            primary_keyword = self._normalize_chinese_locales(primary_keyword)

        title_pad = primary_keyword or ("专业服务指南" if is_chinese else "dịch vụ chuyên nghiệp")
        site_name_lower = str(site_name or "").strip().lower()
        if site_name_lower == "mocbaibavet.com":
            meta_pad = (
                f"{primary_keyword} 木牌 巴域 下马 专业咨询与服务。" if is_chinese else f"{primary_keyword} Mộc Bài Bavet Xa Mát tư vấn và báo giá nhanh."
            )
        elif site_name_lower == "innhanhgeta.com":
            meta_pad = (
                f"{primary_keyword} dịch vụ in ấn GETA tư vấn và báo giá nhanh."
                if not is_chinese
                else f"{primary_keyword} GETA印刷服务 专业咨询与报价。"
            )
        elif site_name_lower == "quangcao.getagroup.vn":
            meta_pad = (
                f"{primary_keyword} dịch vụ quảng cáo GETA tư vấn và báo giá nhanh."
                if not is_chinese
                else f"{primary_keyword} GETA广告服务 专业咨询与报价。"
            )
        else:
            meta_pad = (
                f"{primary_keyword} tư vấn và báo giá nhanh."
                if not is_chinese
                else f"{primary_keyword} 专业咨询与报价。"
            )

        min_title, max_title = (30, 45) if is_chinese else (70, 160)
        min_meta, max_meta = (75, 80) if is_chinese else (120, 155)

        if is_chinese:
            if primary_keyword and primary_keyword not in str(title_seed):
                title_seed = f"{primary_keyword}{title_seed}".strip()
            if not re.search(r"\d", str(title_seed)):
                title_seed = f"{title_seed}2026攻略".strip()
            if not any(token in str(title_seed) for token in ["攻略", "避坑", "丝滑"]):
                title_seed = f"{title_seed}避坑".strip()
            if not any(token in str(title_seed) for token in ["立即咨询", "获取报价"]):
                title_seed = f"{title_seed}立即咨询".strip()

            if primary_keyword and primary_keyword not in str(meta_seed):
                meta_seed = f"{primary_keyword}，{meta_seed}".strip("，")
            if "木牌" not in str(meta_seed):
                meta_seed = f"{meta_seed} 覆盖木牌、巴域、下马。".strip()
            if not any(token in str(meta_seed) for token in ["立即咨询", "获取报价", "在线咨询"]):
                meta_seed = f"{meta_seed} 立即咨询获取报价。".strip()

        seo_metadata["title"] = self._fit_text_length(
            str(title_seed), min_title, max_title, title_pad, separator="" if is_chinese else " "
        )
        seo_metadata["meta_description"] = self._fit_text_length(
            str(meta_seed), min_meta, max_meta, meta_pad, separator="" if is_chinese else " "
        )

        if not is_chinese:
            seo_metadata["title"] = self._strip_cjk_characters(str(seo_metadata.get("title") or ""))
            seo_metadata["meta_description"] = self._strip_cjk_characters(str(seo_metadata.get("meta_description") or ""))
            seo_metadata["title"] = self._normalize_vietnamese_style_phrases(str(seo_metadata.get("title") or ""))
            seo_metadata["meta_description"] = self._normalize_vietnamese_style_phrases(
                str(seo_metadata.get("meta_description") or "")
            )
            # Strip "chủ đầu tư" and surrounding connectors from the title
            seo_metadata["title"] = re.sub(
                r",?\s*(dành )?cho\s+chủ\s+đầu\s+tư",
                "",
                str(seo_metadata.get("title") or ""),
                flags=re.IGNORECASE,
            ).strip()
            seo_metadata["title"] = re.sub(
                r"\bchủ\s+đầu\s+tư\b",
                "",
                str(seo_metadata.get("title") or ""),
                flags=re.IGNORECASE,
            ).strip().strip(",").strip()

        if is_chinese:
            slug_source = primary_keyword or title_seed or seo_metadata.get("slug") or "seo-article"
            seo_metadata["slug"] = self._build_pinyin_slug(slug_source)
        elif not seo_metadata.get("slug"):
            slug_source = primary_keyword or title_seed or "seo-article"
            slug = str(slug_source).lower()
            slug = re.sub(r"[^a-z0-9\u4e00-\u9fff\s-]", " ", slug)
            slug = re.sub(r"\s+", "-", slug).strip("-")
            seo_metadata["slug"] = slug[:75] if slug else "seo-article"

        if content_markdown:
            h2_count = len(re.findall(r"(?m)^##\s+", content_markdown))
            if h2_count < 3:
                if is_chinese:
                    content_markdown += (
                        "\n\n## 常见问题\n"
                        "### 菜单设计多久可以交付？\n一般会根据需求在约定周期内交付。\n"
                        "### 如何获取报价？\n可通过在线咨询提交需求后快速获取报价。\n"
                    )
                else:
                    content_markdown += (
                        "\n\n## Câu hỏi thường gặp\n"
                        "### Thiết kế menu mất bao lâu?\nThời gian triển khai tùy quy mô và sẽ được báo rõ theo từng gói.\n"
                        "### Làm sao nhận báo giá nhanh?\nGửi yêu cầu qua form tư vấn để nhận báo giá theo nhu cầu thực tế.\n"
                    )

            site_name_lower = str(site_name or "").strip().lower()
            if site_name_lower == "mocbaibavet.com":
                content_markdown = self._ensure_service_backlink_pair(
                    content_markdown=content_markdown,
                    keyword=primary_keyword,
                    is_chinese=is_chinese,
                )

                if primary_keyword:
                    current_occurrences = content_markdown.lower().count(primary_keyword.lower())
                    target_occurrences = 6 if is_chinese else 3
                    if current_occurrences < target_occurrences:
                        if is_chinese:
                            content_markdown += (
                                f"\n\n> **联系我们**：如果您对 {primary_keyword} 有任何疑问，欢迎随时咨询，我们为您提供木牌、巴域区域的专属定制方案。"
                            )
                        else:
                            content_markdown += (
                                f"\n\n> **Liên hệ tư vấn**: Nếu bạn có nhu cầu về {primary_keyword}, hãy liên hệ với chúng tôi để nhận báo giá chi tiết và lộ trình triển khai tại Mộc Bài - Bavet."
                            )

                if not is_chinese:
                    content_markdown = self._normalize_vietnamese_style_phrases(content_markdown)

                content_markdown = self._ensure_contact_footer(content_markdown, is_chinese=is_chinese)
            else:
                if primary_keyword and primary_keyword.lower() not in content_markdown.lower():
                    if is_chinese:
                        content_markdown += (
                            f"\n\n> **联系我们**：如果您对 {primary_keyword} 有任何疑问，欢迎联系 GETA 获取更合适的选型建议和报价。"
                        )
                    else:
                        content_markdown += (
                            f"\n\n> **Tư vấn đặt in**: Nếu bạn đang cân nhắc {primary_keyword}, hãy liên hệ GETA để được gợi ý quy cách, chất liệu và báo giá phù hợp."
                        )

        data["seo_metadata"] = seo_metadata
        data["content_markdown"] = content_markdown
        return data

    @staticmethod
    def _is_simplified_chinese_target(language: str) -> bool:
        language_lower = (language or "").lower()
        return "chinese" in language_lower or "giản thể" in language_lower or "简体" in language_lower

    @staticmethod
    def _strip_urls_for_language_checks(text: str) -> str:
        value = str(text or "")
        value = re.sub(r"https?://\S+", " ", value, flags=re.IGNORECASE)
        value = re.sub(r"www\.\S+", " ", value, flags=re.IGNORECASE)
        # Ignore link anchor labels in language purity checks so paired VI/ZH backlinks are allowed.
        value = re.sub(r"\[[^\]]*\]\(\s*[^\)]+\)", " ", value)
        value = re.sub(r"<a\b[^>]*>.*?</a>", " ", value, flags=re.IGNORECASE | re.DOTALL)
        return value

    @staticmethod
    def _count_english_function_words(text: str) -> int:
        sample = str(text or "").lower()
        tokens = re.findall(r"\b[a-z]{2,}\b", sample)
        stopwords = {
            "the", "and", "with", "for", "from", "to", "of", "in", "on", "at", "by", "as",
            "is", "are", "be", "this", "that", "these", "those", "your", "our", "you", "we",
            "it", "an", "a", "or", "if", "when", "while", "into", "about", "through", "more",
        }
        return sum(1 for token in tokens if token in stopwords)

    @staticmethod
    def _extract_language_sample(article_payload: dict) -> str:
        payload = dict(article_payload or {})
        metadata = dict(payload.get("seo_metadata") or {})
        title = str(metadata.get("title") or "")
        meta_description = str(metadata.get("meta_description") or "")
        content_markdown = str(payload.get("content_markdown") or "")
        content_excerpt = content_markdown[:2500]
        return f"{title}\n{meta_description}\n{content_excerpt}".strip()

    def _is_output_language_mismatch(self, article_payload: dict, language: str) -> bool:
        sample = self._extract_language_sample(article_payload)
        if not sample:
            return False

        sanitized = self._strip_urls_for_language_checks(sample)
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", sanitized))
        latin_count = len(re.findall(r"[A-Za-zÀ-ỹ]", sanitized))
        english_function_word_count = self._count_english_function_words(sanitized)
        target_is_chinese = self._is_simplified_chinese_target(language)

        if target_is_chinese:
            return (cjk_count < 40 and latin_count > cjk_count) or english_function_word_count >= 4

        # Allow a small amount of CJK tokens for mandatory paired backlinks in Vietnamese articles.
        return cjk_count > 30 or english_function_word_count >= 3

    def _enforce_output_language(
        self,
        keyword: str,
        context: str,
        language: str,
        article_payload: dict,
    ) -> dict:
        current_payload = dict(article_payload or {})
        if not self.enable_language_rewrite:
            return current_payload
        if not self._is_output_language_mismatch(current_payload, language):
            return current_payload

        target_label = "Simplified Chinese" if self._is_simplified_chinese_target(language) else "Vietnamese"
        if self._is_simplified_chinese_target(language):
            fix_instructions = [
                f"Rewrite the entire article strictly in {target_label}.",
                "Use only Simplified Chinese in all normal sentences.",
                "Do not include Vietnamese or English phrases, except URLs, phone numbers, and proper nouns (Telegram/WeChat/Zalo/Google).",
                "Ensure seo_metadata.title, seo_metadata.meta_description, and content_markdown are all in Simplified Chinese.",
            ]
        else:
            fix_instructions = [
                f"Rewrite the entire article strictly in {target_label}.",
                "Use only Vietnamese in all normal sentences.",
                "Do not include any English or Chinese words/phrases in normal paragraphs, except URLs, phone numbers, proper nouns (Telegram/WeChat/Zalo/Google), and paired service-link anchor text.",
                "Ensure seo_metadata.title, seo_metadata.meta_description, and content_markdown are all in Vietnamese.",
            ]

        for _ in range(2):
            repaired = self._regenerate_article_with_fixes(
                keyword=keyword,
                context=context,
                language=language,
                previous_article=current_payload,
                fix_instructions=fix_instructions,
            )
            if "seo_metadata" in repaired and "content_markdown" in repaired:
                current_payload = repaired
            if not self._is_output_language_mismatch(current_payload, language):
                break

        return current_payload

    @retry(
        # Đợi tối thiểu 2s, tăng dần theo hàm mũ, dừng sau 3 lần thử thất bại
        wait=wait_exponential(multiplier=1, min=2, max=10), 
        stop=stop_after_attempt(GEMINI_GENERATE_RETRY_ATTEMPTS),
        retry=retry_if_exception(_is_retryable_llm_exception),
        reraise=True,
    )
    def generate_article(
        self,
        keyword: str,
        context: str = "",
        language: str = "Vietnamese",
        site_name: str | None = None,
    ) -> dict:
        """
        Thực thi prompt chain và trả về dictionary chuẩn hóa.
        """
        self._safe_log(f"[*] Generating article for keyword: '{keyword}'...")
        
        # 1. Chuẩn bị Messages cho LangChain
        messages = [
            SystemMessage(content=build_seo_system_prompt(language=language, site_name=site_name)),
            HumanMessage(content=build_seo_user_prompt(keyword=keyword, context=context, language=language, site_name=site_name))
        ]
        
        # 2. Gọi API (Inference)
        invoke_started = time.perf_counter()
        try:
            response = self._invoke_llm(messages)
            self._record_quota_usage(response)
            elapsed = time.perf_counter() - invoke_started
            self._safe_log(
                f"[*] Gemini response received in {elapsed:.1f}s (timeout={self.request_timeout_seconds}s)"
            )
        except Exception as e:
            elapsed = time.perf_counter() - invoke_started
            self._safe_log(f"[!] Gemini invoke error for keyword='{keyword}': {type(e).__name__}: {e}")
            self._safe_log(f"[!] Gemini invoke elapsed before error: {elapsed:.1f}s")
            self._safe_log(traceback.format_exc())
            raise
        
        # 3. Parsing và Validate Output data
        self._safe_log("[*] Parsing Gemini output...")
        try:
            parsed_data = self._parse_llm_json(response.content)
        except OutputParsingError:
            self._safe_log("[*] Gemini output malformed, running JSON repair pass...")
            parsed_data = self._repair_malformed_article_json(response.content, language=language, site_name=site_name)

        # Validate cấu trúc Data Schema
        if "seo_metadata" not in parsed_data or "content_markdown" not in parsed_data:
            self._safe_log(f"[!] Invalid LLM schema output: {response.content}")
            raise OutputParsingError("JSON trả về thiếu các keys bắt buộc (seo_metadata, content_markdown).")

        if self.enable_article_review:
            self._safe_log("[*] Running article review pass...")
            review = self._review_generated_article(
                keyword=keyword,
                language=language,
                article_payload=parsed_data,
                site_name=site_name,
            )
            if not review.get("pass"):
                fix_instructions = review.get("fix_instructions", [])
                if fix_instructions:
                    self._safe_log("[*] Review failed, running regeneration pass with fix instructions...")
                    repaired = self._regenerate_article_with_fixes(
                        keyword=keyword,
                        context=context,
                        language=language,
                        previous_article=parsed_data,
                        fix_instructions=fix_instructions,
                        site_name=site_name,
                    )
                    if "seo_metadata" in repaired and "content_markdown" in repaired:
                        parsed_data = repaired

                parsed_data = self._post_optimize_article_payload(
                    parsed_data,
                    keyword=keyword,
                    language=language,
                    site_name=site_name,
                )
        else:
            parsed_data = self._post_optimize_article_payload(
                parsed_data,
                keyword=keyword,
                language=language,
                site_name=site_name,
            )

        if self.enable_language_rewrite:
            self._safe_log("[*] Running strict language rewrite enforcement pass...")
        parsed_data = self._enforce_output_language(
            keyword=keyword,
            context=context,
            language=language,
            article_payload=parsed_data,
        )

        self._safe_log("[*] Article generation pipeline finished.")

        return parsed_data

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(2),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    def generate_alt_texts(
        self,
        title: str,
        keywords: list[str],
        locales: list[str],
        language: str,
        count: int,
    ) -> list[str]:
        system_prompt = (
            "You generate SEO image alt texts. "
            "Return ONLY JSON: {\"alts\": [\"...\"]}."
        )
        keywords_text = ", ".join([item.strip() for item in keywords if item.strip()])
        locales_text = ", ".join([item.strip() for item in locales if item.strip()])
        user_prompt = (
            f"Article title: {title}\n"
            f"Keywords: {keywords_text}\n"
            f"Locales: {locales_text}\n"
            f"Language: {language}\n"
            f"Count: {count}\n"
            "Rules: Each item must be a complete, natural sentence (maximum 14 words). "
            "ALL sentences must be completely distinct from each other in meaning and phrasing. "
            "They will be used as image filenames and SEO alt texts. "
            "Include keywords naturally without stuffing."
        )

        response = self._invoke_llm([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        self._record_quota_usage(response)

        alts = self._parse_string_list(response.content, "alts")
        deduped: list[str] = []
        seen: set[str] = set()
        for alt in alts:
            normalized = alt.lower().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(alt.strip())
        return deduped[: max(1, int(count))]

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    def generate_related_keywords(self, topic: str, language: str, count: int) -> dict:
        """
        Returns dict: {"primary_keywords": [...], "long_tail_keywords": [...]}
        primary_keywords: head terms, moderate-high volume (qty: count)
        long_tail_keywords: 3-6 word phrases, low competition, high conversion intent (qty: count × 5)
        """
        system_prompt = (
            "You are an SEO keyword strategist specializing in Vietnamese and Simplified Chinese B2B markets. "
            "Return ONLY JSON with this exact schema: "
            "{\"primary_keywords\": [\"...\"], \"long_tail_keywords\": [\"...\"]}. "
            "Do not include explanations or markdown."
        )
        required_longtail_count = count * 5
        user_prompt = (
            f"Topic: {topic}\n"
            f"Language: {language}\n"
            f"Primary keywords requested: {count}\n"
            f"Long-tail keywords requested: {required_longtail_count}\n\n"
            "Task:\n"
            f"1. Generate EXACTLY {count} primary/head keywords (broad, moderate-high search volume) relevant to the topic.\n"
            f"2. Generate EXACTLY {required_longtail_count} long-tail keywords (3-6 words each, low competition, high purchase intent). "
            "Long-tail examples: 'báo giá X tại Y', 'X giá rẻ uy tín', 'dịch vụ X cho Z', 'X trọn gói bao nhiêu tiền'. "
            "These should reflect specific buyer intent: pricing, location, comparison, or problem-solving queries.\n"
            "All keywords must be non-duplicate, diverse, and natural in the target language. "
            f"Ensure you provide EXACTLY {required_longtail_count} unique long-tail keywords for grouping into {count} groups of 5."
        )

        response = self._invoke_llm([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        self._record_quota_usage(response)

        return self._parse_keyword_suggestions_structured(response.content)

    def _parse_keyword_suggestions_structured(self, raw_text: str) -> dict:
        """Parse structured keyword output returning {primary_keywords, long_tail_keywords}."""
        cleaned_text = self._clean_json_output(raw_text)
        try:
            parsed = json.loads(cleaned_text, strict=False)
        except json.JSONDecodeError:
            extracted = self._extract_json_object(cleaned_text)
            parsed = json.loads(extracted, strict=False)

        def _dedup(items) -> list[str]:
            seen: set[str] = set()
            result: list[str] = []
            for item in (items or []):
                normalized = str(item).strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    result.append(str(item).strip())
            return result

        # Handle new structured format
        if isinstance(parsed, dict):
            primary = _dedup(parsed.get("primary_keywords", []))
            long_tail = _dedup(parsed.get("long_tail_keywords", []))
            # Fallback: old format {"keywords": [...]}
            if not primary and not long_tail:
                flat = _dedup(parsed.get("keywords", []))
                return {"primary_keywords": flat, "long_tail_keywords": []}
            return {"primary_keywords": primary, "long_tail_keywords": long_tail}

        if isinstance(parsed, list):
            return {"primary_keywords": _dedup(parsed), "long_tail_keywords": []}

        raise OutputParsingError("Output gợi ý từ khóa không đúng định dạng JSON.")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(2),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    def translate_keyword_to_english_filename(self, keyword: str) -> str:
        system_prompt = (
            "You are a translation helper for file naming. "
            "Return ONLY a short English phrase in lowercase letters and spaces. "
            "No punctuation, no quotes, no markdown."
        )
        user_prompt = (
            f"Translate this keyword to natural English for an image filename: {keyword}\n"
            "Keep it concise (2-6 words)."
        )

        response = self._invoke_llm([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        self._record_quota_usage(response)

        text = str(response.content or "").strip().lower()
        text = re.sub(r"[^a-z\s-]", " ", text)
        text = re.sub(r"\s+", " ", text).strip(" -")
        return text

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(2),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    def suggest_image_groups(self, topic: str, language: str, max_groups: int = 5) -> list[str]:
        system_prompt = (
            "You are an image taxonomy assistant for blog posts. "
            "Return ONLY JSON: {\"groups\": [\"...\"]}. No markdown."
        )
        user_prompt = (
            f"Topic: {topic}\n"
            f"Language: {language}\n"
            f"Max groups: {max_groups}\n"
            "Generate practical image groups/categories for this blog topic."
        )

        response = self._invoke_llm([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        self._record_quota_usage(response)

        groups = self._parse_string_list(response.content, "groups")
        deduped: list[str] = []
        seen: set[str] = set()
        for group in groups:
            normalized = group.lower()
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(group)
        return deduped[: max(1, int(max_groups))]

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(2),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    def classify_image_group(
        self,
        image_bytes: bytes,
        mime_type: str,
        groups: list[str],
        language: str,
    ) -> str:
        if not groups:
            return "other"

        encoded = base64.b64encode(image_bytes).decode("utf-8")
        groups_text = ", ".join(groups)

        system_prompt = (
            "You are an image classifier for blog workflow. "
            "Return ONLY JSON: {\"group\": \"one of given groups or other\"}."
        )
        text_prompt = (
            f"Language: {language}\n"
            f"Allowed groups: {groups_text}\n"
            "Pick the single best group for this image. If unclear, return 'other'."
        )

        response = self._invoke_llm([
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=[
                    {"type": "text", "text": text_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                ]
            ),
        ])
        self._record_quota_usage(response)

        parsed = self._parse_llm_json(response.content)
        selected = str(parsed.get("group", "other")).strip()
        if not selected:
            return "other"

        selected_lower = selected.lower()
        for group in groups:
            if selected_lower == group.lower():
                return group
        return "other"