import os
import sys
import json
import asyncio
import argparse
from pydantic import BaseModel, Field
import google.generativeai as genai

# Thêm path để load .env nếu cần
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crawl4ai import AsyncWebCrawler

sys.stdout.reconfigure(encoding='utf-8')

class SearchResult(BaseModel):
    title: str = Field(..., description="Tiêu đề bài viết, tên trang, hoặc tên nhà cung cấp")
    link: str = Field(..., description="Đường link (URL)")
    snippet: str = Field(..., description="Mô tả hoặc nội dung tóm tắt")
    price: str = Field(None, description="Giá bán, giá sỉ (nếu có)")
    phone: str = Field(None, description="Số điện thoại liên hệ (nếu có)")

def extract_with_gemini(markdown_text: str, api_key: str):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config={
            "response_mime_type": "application/json"
        }
    )
    prompt = f"""Bạn là chuyên gia khai thác dữ liệu (Data Mining). YÊU CẦU QUAN TRỌNG: Hãy quét TOÀN BỘ NỘI DUNG của trang web bên dưới.
TRÍCH XUẤT TẤT CẢ TỪNG KẾT QUẢ TÌM KIẾM ĐƯỢC LIỆT KÊ. Tuyệt đối không được bỏ sót!
Tối thiểu phải có title và snippet, nếu có số điện thoại hoặc giá sỉ thì lấy luôn.

Nội dung Markdown:
{markdown_text[:30000]}
"""
    try:
        response = model.generate_content(prompt)
        if response.text:
            return json.loads(response.text)
    except Exception as e:
        print(f"[!] Gemini Extraction Error: {e}")
    return []

async def main():
    parser = argparse.ArgumentParser(description="Market Research using Crawl4AI")
    parser.add_argument("--query", required=True, help="Từ khóa tìm kiếm")
    args = parser.parse_args()
    
    query = args.query
    print(f"[*] Starting Market Research for '{query}' using Crawl4AI...")
    
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        api_key = "AIzaSyAlOe_3hZrz07JLQuUve6HeixvZrTor-VA"
        
    urls = [
        f"https://coccoc.com/search?query={query}",
        f"https://www.google.com/search?q={query}"
    ]
    
    extracted_data = []
    
    async with AsyncWebCrawler(verbose=True) as crawler:
        for url in urls:
            print(f"[*] Crawling {url}...")
            result = await crawler.arun(url=url, bypass_cache=True, delay_before_return_html=2.0)
            
            if result.markdown:
                print(f"[*] Extracting data from markdown (length: {len(result.markdown)})...")
                data = extract_with_gemini(result.markdown, api_key)
                if isinstance(data, list):
                    extracted_data.extend(data)
                elif data:
                    extracted_data.append(data)
            else:
                print(f"[!] No content fetched for {url}.")
                    
    # Format cho Master Agent & Zalo CRM đọc được
    final_results = []
    for item in extracted_data:
        if isinstance(item, dict):
            final_results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "platform": "Search Engine",
                "phone": item.get("phone", None),
                "price": item.get("price", None)
            })
        
    output_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "research_results.json"))
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_results, f, indent=4, ensure_ascii=False)
        
    print(f"✅ Đã tìm thấy {len(final_results)} kết quả.")
    print(f"✅ Dữ liệu đã lưu tại {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
