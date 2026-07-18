from __future__ import annotations

import json
from pathlib import Path

SERVICE_INTERNAL_LINKS = [
    {"vi": "Bảng hiệu quảng cáo", "zh": "广告招牌制作", "slug": "advertising-signboards"},
    {"vi": "Lắp đặt hệ thống điện", "zh": "电路安装与维修", "slug": "mep-installation"},
    {"vi": "Thiết kế menu hàng quán", "zh": "菜单、菜谱设计与印刷", "slug": "menu-design"},
    {"vi": "Sản xuất nội thất", "zh": "家具定制生产", "slug": "furniture-factory"},
    {"vi": "Sơn nước", "zh": "墙面刷漆、批灰处理", "slug": "professional-painting"},
    {"vi": "Sửa chữa và cải tạo nhà", "zh": "旧房翻新与家庭维修", "slug": "renovation-repair"},
    {"vi": "Thi công quán cafe, nhà hàng", "zh": "咖啡厅、台球厅装修施工", "slug": "restaurant-cafe-construction"},
    {"vi": "Thiết kế – trang trí nội thất", "zh": "室内设计与装饰", "slug": "interior-fit-out"},
]

ROOT_DIR = Path(__file__).resolve().parent.parent
SITES_CONFIG_PATH = ROOT_DIR / "sites.json"


SEO_AGENT_SYSTEM_PROMPT = """
You are an elite SEO Content Expert and Conversion Copywriter.
Target Language: __LANGUAGE__

### ROLE & MINDSET
- __VALUE_PROP_RULE__
- **Customer Psychology**: Drive conversion through trust and practical implementation advice.
- **Narrative Arc**: Hook (pain point) -> Context -> Solution -> Trust Signal -> Natural CTA.
- **Target Area**: __TARGET_AREA_RULE__
- **Site Isolation**: __SITE_ISOLATION_RULE__
- **Site-Specific Rules**:
{site_rules}

### METADATA & SEO RULES (STRICT)
- **Vietnamese SEO**:
  - Title: 70-130 characters, must be a complete, natural sentence. NEVER use "chủ đầu tư" in the title.
  - Meta Description: 120-155 characters.
  - URL Slug: Standard Vietnamese non-accented slug.
- **Chinese SEO (Simplified)**:
  - Title: 30-45 Chinese characters, must be a complete sentence.
  - Meta Description: 75-80 Chinese characters.
  - URL Slug: Lowercase Pinyin with hyphens (e.g., "zhuang-xiu-fu-wu").

### CONTENT STRUCTURE
- **Heading Structure**: H1, 3-6 H2 sections, and practical H3 subsections.
- **Length**: 1200-1800 words (NOT too long; quality over quantity).
- **Keyword Usage**: Intersperse the focus keyword naturally throughout the body (target 8-15 mentions for optimal SEO density).
- **Sentence Length**: Break long sentences into 2-3 shorter ones for better readability and engagement.
- **Formatting**: Bold key concepts, use bullet points for scannability.
- **FAQ**: 2-4 practical Q&As at the end (No images in FAQ).

### INTERNAL LINKING & FORBIDDEN ITEMS (CRITICAL)
{internal_link_rules}

### OUTPUT FORMAT
The output MUST be a valid JSON object.
{{
  "seo_metadata": {{
    "title": "string",
    "meta_description": "string",
    "slug": "string"
  }},
  "content_markdown": "string (Start with H1, no external links, follow the site-specific internal-link policy)"
}}
""".strip()

USER_PROMPT_TEMPLATE = """
Focus Keyword: {keyword}
Additional Context/Tone: {context}
Output Language: {language}
Selected Site: {site_name}
Site Focus: {site_focus}
Local Focus: {local_focus}
Site Isolation: {site_isolation}

Quality Targets:
- Title MUST BE a complete, natural sentence aligned only with the selected site.
- Body: 1200-1800 words (NOT too long; quality over quantity)
- Intersperse the keyword naturally throughout the body (target 8-15 mentions for SEO density)
- Break long sentences into 2-3 shorter ones for better readability
- Include exactly the internal links required by the selected site rules.
- IMPORTANT: If `Additional Context/Tone` provides a specific internal link or backlink instruction (e.g. for Pillar/Spoke clustering), you MUST include that specific link in the body, overriding any URL format restrictions from the system rules.
- Anchor text must show the actual service/category/product name, never generic text like `ở đây` or `tại đây`.
- Strictly keep one language only.
- Use only the selected site's own brand voice, taxonomy, and audience context.

Execute the workflow and generate the article.
""".strip()


def build_seo_user_prompt(keyword: str, context: str, language: str, site_name: str | None = None) -> str:
  site_focus = _get_site_content_rules(site_name)
  if not site_focus:
    site_focus = "Use the selected site context and keep the article aligned with the current brand, taxonomy, and conversion goal."
  local_focus = _build_target_area_rule(language, site_name=site_name)
  site_isolation = _build_site_isolation_rule(site_name=site_name)

  return USER_PROMPT_TEMPLATE.format(
    keyword=(keyword or "").strip(),
    context=(context or "").strip(),
    language=(language or "").strip(),
    site_name=(site_name or "").strip() or "current site",
    site_focus=site_focus,
    local_focus=local_focus,
    site_isolation=site_isolation,
  )


def _load_sites_config() -> list[dict]:
  if not SITES_CONFIG_PATH.exists():
    return []

  with open(SITES_CONFIG_PATH, encoding="utf-8-sig") as f:
    data = json.load(f)

  return data if isinstance(data, list) else []


def _get_site_config(site_name: str | None) -> dict | None:
  normalized_name = str(site_name or "").strip().lower()
  if not normalized_name:
    return None

  for site in _load_sites_config():
    if str(site.get("name") or "").strip().lower() == normalized_name:
      return site
  return None


def _get_site_content_rules(site_name: str | None) -> str:
  site = _get_site_config(site_name)
  if not site:
    return ""
  return str(site.get("content_rules") or "").strip()


def _build_target_area_rule(language: str, site_name: str | None = None) -> str:
  normalized_site = str(site_name or "").strip().lower()
  if normalized_site == "innhanhgeta.com":
    return "Prioritize relevance for customers looking for printing and branded collateral solutions on GETA's printing site."
  if normalized_site == "quangcao.getagroup.vn":
    return "Prioritize relevance for customers looking for advertising and brand-visibility solutions on GETA's advertising site."
  if normalized_site == "mocbaibavet.com":
    return "Prioritize relevance for customers in Mộc Bài, Bavet, Xa Mát."

  language_lower = (language or "").lower()
  if "chinese" in language_lower or "giản thể" in language_lower or "简体" in language_lower:
    return "Prioritize relevance for customers of the selected site in Simplified Chinese without borrowing place names from unrelated sites."
  return "Prioritize relevance for customers of the selected site without borrowing place names from unrelated sites."


def _build_site_isolation_rule(site_name: str | None = None) -> str:
  normalized_site = str(site_name or "").strip().lower()
  if normalized_site == "innhanhgeta.com":
    return "Use the GETA printing site's own brand voice, product taxonomy, and consulting style only."
  if normalized_site == "quangcao.getagroup.vn":
    return "Use the GETA advertising site's own brand voice, product taxonomy, and consulting style only."
  if normalized_site == "mocbaibavet.com":
    return "Use the Mộc Bài Bavet service network's own brand voice, service taxonomy, and consulting style only."
  return "Use only the selected site's own brand voice, taxonomy, and audience context."


def _build_value_prop_rule(language: str, site_name: str | None = None) -> str:
  normalized_site = str(site_name or "").strip().lower()
  if normalized_site == "innhanhgeta.com":
    return "Always write with a practical printing-consultation mindset: help readers choose the right material, finishing, and product format before asking for a quote."
  if normalized_site == "quangcao.getagroup.vn":
    return "Always write with a practical advertising-consultation mindset: help readers choose the right material, finish, and display format before asking for a quote."

  language_lower = (language or "").lower()
  if "chinese" in language_lower or "giản thể" in language_lower or "简体" in language_lower:
    return "Always write with a one-stop solution mindset (一站式服务): save client time, unify brand execution, and streamline operations in Vietnam."
  return "Always write with an integrated full-service mindset (dịch vụ trọn gói, đồng bộ): save client time, unify brand execution, and streamline operations in Vietnam."


def build_service_link_pairs() -> list[dict[str, str]]:
  pairs: list[dict[str, str]] = []
  for service in SERVICE_INTERNAL_LINKS:
    slug = str(service["slug"]).strip()
    pairs.append(
      {
        "slug": slug,
        "vi_name": str(service["vi"]).strip(),
        "zh_name": str(service["zh"]).strip(),
        "vi_url": f"https://mocbaibavet.com/vi/services/{slug}",
        "zh_url": f"https://mocbaibavet.com/services/{slug}",
      }
    )
  return pairs


def _build_internal_link_rules(site_name: str | None) -> str:
  normalized_name = str(site_name or "").strip().lower()
  if normalized_name == "mocbaibavet.com":
    service_list_str = ""
    for service in build_service_link_pairs():
      service_list_str += (
        f"- slug: {service['slug']} | "
        f"VI: {service['vi_name']} (URL: {service['vi_url']}) | "
        f"ZH: {service['zh_name']} (URL: {service['zh_url']})\n"
      )

    return (
      "- Internal Links: Include EXACTLY TWO (2) links as ONE paired set for the same service slug:\n"
      "  - 1 Vietnamese URL: `https://mocbaibavet.com/vi/services/{slug}`\n"
      "  - 1 Chinese URL: `https://mocbaibavet.com/services/{slug}`\n"
      "- Selection Rule: Choose the service pair that MOST CLOSELY matches the article's category/topic. Both links MUST use the same slug.\n"
      "- Anchor Text Rule:\n"
      "  - For Vietnamese articles: use visible anchor text in Vietnamese only, in this pattern: `Service Name` and `Service Name - tiếng Trung`.\n"
      "  - For Simplified Chinese articles: use visible anchor text in Simplified Chinese only, in this pattern: `服务名称` and `服务名称（越南语）`.\n"
      "  - NEVER hide links behind generic anchors like `ở đây`, `tại đây`, `xem thêm`, `click here`, `点击这里`.\n"
      "- Placement: Integrate naturally within the body text.\n"
      "- STRICT FORBIDDEN:\n"
      "    - NO generic \"See more\" or \"Dịch vụ nổi bật\" sections at the end.\n"
      "    - NO external links or 3rd party references.\n"
      "    - You MUST use the `services/` paths provided in the list.\n"
      "    - NO image tags, markdown images `![]()`, or placeholders like `[Image here]`. The system handles images separately.\n"
      "- SERVICE LIST FOR INTERNAL LINKING:\n"
      f"{service_list_str.strip()}"
    ).strip()

  return (
    "- Internal Linking Strategy: You MUST seamlessly integrate 3-5 internal links directly into the natural flow of the paragraphs.\n"
    "  - Entity & Phrase Linking: Bold and link relevant phrases, nouns, or concepts (e.g., `**[related topic phrase]**(URL)`) within a full, meaningful sentence.\n"
    "  - Natural Flow: Ensure the sentence containing the link adds value to the current paragraph. The transition must be completely smooth and contextually relevant.\n"
    "  - STRICT FORBIDDEN: Do NOT use standalone call-to-action blocks like 'Xem chi tiết:', 'Xem thêm:', 'Tham khảo:', or generic anchors like 'Click here'. Do not interrupt the reading experience.\n"
    "- Selection Rule: Link only to closely matching products, categories, or blog articles from the provided dynamic list.\n"
    "- STRICT FORBIDDEN: No external links to other domains. Never use placeholder URLs."
  )


def build_seo_system_prompt(language: str, site_name: str | None = None) -> str:
  site_rules = _get_site_content_rules(site_name)
  if not site_rules:
    site_rules = (
      "Bạn là content agent cho website hiện tại. Viết bài đúng bối cảnh site đã chọn, ưu tiên chủ đề có khả năng chuyển đổi cao, "
      "không bịa dữ liệu, và giữ nội dung hữu ích cho người đang có nhu cầu thực tế."
    )

  site_isolation = _build_site_isolation_rule(site_name=site_name)

  return (
    SEO_AGENT_SYSTEM_PROMPT
    .replace("{site_rules}", site_rules)
    .replace("{internal_link_rules}", _build_internal_link_rules(site_name))
    .replace("__LANGUAGE__", (language or "").strip())
    .replace("__TARGET_AREA_RULE__", _build_target_area_rule(language, site_name=site_name))
    .replace("__VALUE_PROP_RULE__", _build_value_prop_rule(language, site_name=site_name))
    .replace("__SITE_ISOLATION_RULE__", site_isolation)
  )