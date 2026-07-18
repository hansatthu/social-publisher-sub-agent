"""
cron_generate_image.py — Tạo ảnh sản phẩm in ấn (không text) để đính kèm bài đăng.
Đọc next_post.txt để hiểu nội dung, sinh prompt phù hợp rồi tạo ảnh qua Gemini Imagen.
Output: tools/next_post_image.jpg
"""
import sys
import re
import os
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.gemini_image_gen import generate_image_with_fallback

BASE       = Path(__file__).parent.parent
POST_PATH  = BASE / "tools" / "next_post.txt"
IMAGE_PATH = BASE / "tools" / "next_post_image.jpg"

# Sơ đồ ánh xạ từ khóa bài đăng -> Prompt hình ảnh chi tiết (Tiếng Anh)
PROMPT_MAP = [
    (r"ly nhựa|ly in|cup|hộp nhựa",
     "A professional product photography of plain, blank, clear plastic cups and containers arranged elegantly on a white surface. "
     "Clean studio lighting, photorealistic, absolutely no logos, no print designs, no text, no words, no letters, no characters, no watermark"),
    (r"standee|banner|bạt|hiflex|bảng hiệu",
     "A professional outdoor advertising display with a clean, blank, white standee and banner at a storefront. "
     "Rich colors, absolutely no text, no logos, no print designs, no words, no letters, no characters, studio-clean composition, photorealistic"),
    (r"sticker|decal|nhãn",
     "A flat-lay product photography of colorful blank sticker sheets and die-cut decals on a clean white background, "
     "various shapes and vivid colors, high-quality finish, absolutely no text, no logos, no print designs, no words, no letters, no characters, photorealistic"),
    (r"áo|đồng phục|in áo",
     "Professional product photography of plain, blank t-shirts and uniforms without any prints or designs. "
     "Laid flat, clean white background, absolutely no text, no logos, no print designs, no words, no letters, no characters, photorealistic studio shot"),
    (r"bật lửa|sạc dự phòng|quà tặng|mũ bảo hiểm",
     "Flat lay product photography of clean, blank corporate gift items: lighters, power banks, caps. "
     "Premium presentation, absolutely no text, no logos, no print designs, no words, no letters, no characters, photorealistic"),
    (r"flash sale|khuyến mãi|giảm giá|miễn phí",
     "Vibrant promotional product display with colorful plain packaging and blank paper samples. "
     "Festive and energetic atmosphere, absolutely no text, no logos, no print designs, no words, no letters, no characters, photorealistic, clean background"),
    (r"tips|hướng dẫn|mẹo|thiết kế file|in ấn số lượng",
     "Creative flat lay of professional printing tools and clean blank design materials: CMYK color swatches, paper samples, "
     "blank sketches, pantone cards on a modern desk. Absolutely no text, no logos, no words, no letters, no characters, photorealistic top-down view"),
]

DEFAULT_PROMPT = (
    "Professional product photography: assorted blank, unprinted materials including cards, flyers, stickers and paper cups. "
    "Arranged beautifully on a clean white surface, vibrant colors, high-quality finish, "
    "absolutely no text, no logos, no print designs, no words, no letters, no characters, no watermark, photorealistic studio lighting"
)

def pick_prompt(content: str) -> str:
    content_lower = content.lower()
    for pattern, prompt in PROMPT_MAP:
        if re.search(pattern, content_lower):
            return prompt
    return DEFAULT_PROMPT

def main():
    if not POST_PATH.exists() or not POST_PATH.read_text(encoding="utf-8").strip():
        print("⚠️  next_post.txt trống — dùng default prompt")
        content = ""
    else:
        content = POST_PATH.read_text(encoding="utf-8")
        
    prompt = pick_prompt(content)
    matched = any(re.search(p, content.lower()) for p, _ in PROMPT_MAP)
    
    print(f"🎯 Prompt category: {'matched keyword' if matched else 'default'}")
    print(f"📝 Prompt: {prompt[:100]}...")
    print(f"\n🖼️  Đang tạo ảnh → {IMAGE_PATH.name} ...")
    
    success = generate_image_with_fallback(
        prompt      = prompt,
        output_path = str(IMAGE_PATH),
        aspect_ratio = "1:1"
    )
    
    if success and IMAGE_PATH.exists():
        size_kb = IMAGE_PATH.stat().st_size // 1024
        print(f"✅ Ảnh đã tạo: {IMAGE_PATH} ({size_kb} KB)")
        return True
    else:
        print("❌ Tạo ảnh thất bại!")
        return False

if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
