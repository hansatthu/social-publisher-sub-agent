import sys
import time
import os
import random
import json
import urllib.parse
from playwright.sync_api import sync_playwright
import traceback

def random_delay(min_sec=3, max_sec=7):
    time.sleep(random.uniform(min_sec, max_sec))

def get_already_joined_groups(page):
    """Lấy danh sách các nhóm đã tham gia bằng cách quét trang facebook.com/groups/"""
    joined_urls = set()
    print("🔍 Đang quét danh sách các nhóm bạn đã tham gia từ trước...")
    try:
        page.goto("https://www.facebook.com/groups/", timeout=15000)
        random_delay(4, 6)
        
        anchors = page.locator('a[href*="/groups/"]')
        count = anchors.count()
        for i in range(count):
            href = anchors.nth(i).get_attribute("href")
            if href:
                parts = href.split("/groups/")
                if len(parts) > 1:
                    group_id = parts[1].split("/")[0].split("?")[0]
                    if group_id and group_id not in ["feed", "discover", "create", "joins", "subbed"]:
                        joined_urls.add(group_id.lower())
        print(f"✅ Đã phát hiện {len(joined_urls)} nhóm bạn đã tham gia trên Facebook.")
    except Exception as e:
        print(f"⚠️ Không thể quét danh sách nhóm đã tham gia: {e}. Sẽ tiến hành kiểm tra từng nhóm.")
    return joined_urls

def run(playwright, keyword=None):
    import requests
    import socket
    cdp_host = os.getenv("CDP_HOST", "127.0.0.1:9222")
    print(f"👉 Đang cố gắng kết nối tới trình duyệt Chrome ở {cdp_host}...")
    
    host_part = cdp_host
    port_part = "9222"
    if ":" in cdp_host:
        host_part, port_part = cdp_host.split(":", 1)
        
    if host_part == "host.docker.internal":
        try:
            host_part = socket.gethostbyname("host.docker.internal")
        except Exception:
            pass
            
    resolved_host = f"{host_part}:{port_part}"
    ws_url = None
    try:
        res = requests.get(f"http://{resolved_host}/json/version", timeout=2)
        if res.status_code == 200:
            ws_url = res.json().get("webSocketDebuggerUrl")
    except Exception as e:
        print(f"[!] Error resolving WebSocket URL: {e}")

    if not ws_url:
        print(f"❌ LỖI KẾT NỐI: Không thể phân giải WebSocket URL ở {cdp_host} (IP: {host_part}).")
        return

    try:
        browser = playwright.chromium.connect_over_cdp(ws_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page() # Luôn mở tab mới
        print("✅ Kết nối Chrome THÀNH CÔNG!")
    except Exception as e:
        print(f"❌ LỖI KẾT NỐI: Không thể kết nối tới Chrome ở {cdp_host}. Chi tiết: {e}")
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(script_dir, "joined_log.txt")

    # Đọc danh sách URL được chọn từ tham số thứ 2 (nếu có)
    selected_urls = []
    if len(sys.argv) > 2:
        try:
            selected_urls = json.loads(sys.argv[2])
        except Exception as e:
            print(f"Không thể parse JSON danh sách URL: {e}")

    # Xác định danh sách nhóm theo keyword hoặc danh sách URL chọn sẵn
    groups = []
    if selected_urls:
        groups = [{"name": f"Nhóm chọn sẵn {i+1}", "url": url} for i, url in enumerate(selected_urls)]
        print(f"📂 Sử dụng danh sách {len(groups)} nhóm được chọn trực tiếp từ giao diện.")
    else:
        # Đọc file crawled_groups.json
        crawled_file = os.path.join(script_dir, "crawled_groups.json")
        
        if not os.path.exists(crawled_file):
            print(f"❌ LỖI: Không tìm thấy file danh sách nhóm đã cào tại: {crawled_file}")
            print("Vui lòng chạy tính năng cào (Crawl) trước.")
            return
            
        try:
            with open(crawled_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ LỖI: Không thể đọc file {crawled_file}. Chi tiết: {e}")
            return

        if isinstance(data, list):
            groups = data
            print("📂 Đọc file cấu hình kiểu cũ (dạng list).")
        elif isinstance(data, dict):
            if keyword:
                groups = data.get(keyword, [])
                print(f"📂 Lọc danh sách nhóm cho từ khóa: '{keyword}'")
            else:
                if data:
                    first_kw = list(data.keys())[0]
                    groups = data[first_kw]
                    print(f"📂 Từ khóa không được truyền. Tự động chọn từ khóa đầu tiên: '{first_kw}'")
                else:
                    print("❌ LỖI: Không có từ khóa nào trong file.")
                    return
        else:
            print("❌ LỖI: Định dạng file không hợp lệ.")
            return

    if not groups:
        print(f"❌ LỖI: Không có nhóm nào được tìm thấy.")
        return

    print(f"📂 Đã đọc danh sách nhóm. Tìm thấy {len(groups)} nhóm.")
    
    # Lọc danh sách nhóm đã tham gia trước để tránh vào từng trang một cách mất thời gian
    already_joined_ids = get_already_joined_groups(page)
    filtered_groups = []
    for g in groups:
        url = g.get("url", "")
        parts = url.split("/groups/")
        if len(parts) > 1:
            g_id = parts[1].split("/")[0].split("?")[0]
            if g_id.lower() in already_joined_ids:
                print(f"⏭️ Bỏ qua nhóm đã tham gia (phát hiện nhanh trước): {g.get('name')} ({url})")
                continue
        filtered_groups.append(g)
        
    print(f"📝 Sau khi lọc nhanh, còn lại {len(filtered_groups)}/{len(groups)} nhóm chưa tham gia.")
    groups = filtered_groups

    joined_count = 0
    max_joins = len(groups) # Tham gia toàn bộ danh sách nhóm chưa tham gia
    log_file_path = os.path.join(script_dir, "joined_log.txt")

    for idx, group in enumerate(groups):
        if joined_count >= max_joins:
            break
            
        group_name = group.get("name", "Không rõ tên")
        group_url = group.get("url")
        
        if not group_url:
            continue
            
        print(f"\n👉 [{idx + 1}/{len(groups)}] Đang truy cập nhóm: '{group_name}'")
        print(f"🔗 URL: {group_url}")
        
        try:
            page.goto(group_url)
            random_delay(5, 8)
            
            # Kiểm tra xem đã là thành viên hay chưa bằng cách quét text trong trang
            page_text = page.locator("body").inner_text()
            if any(text in page_text for text in ["Đã gửi yêu cầu", "Requested", "Đã tham gia", "Joined", "Truy cập nhóm", "Visit group"]):
                print("⏭️ Bạn đã là thành viên hoặc đã gửi yêu cầu tham gia nhóm này rồi. Bỏ qua.")
                continue

            # Tìm nút Tham gia nhóm
            join_btn = page.locator('div[role="button"]:has-text("Tham gia nhóm"), div[role="button"]:has-text("Join Group"), div[role="button"]:has-text("Tham gia"), div[role="button"]:has-text("Join"), button:has-text("Tham gia nhóm"), button:has-text("Join Group")').first
            
            if join_btn.count() == 0:
                print("⚠️ Không tìm thấy nút Tham gia trên trang này. Có thể nhóm đã đóng hoặc giao diện khác.")
                continue
                
            btn_text = join_btn.inner_text().strip()
            print(f"👉 Đang click nút: '{btn_text}'")
            
            # Click
            join_btn.scroll_into_view_if_needed()
            random_delay(1, 3)
            join_btn.click()
            random_delay(3, 5)
            
            # Kiểm tra xem có bảng câu hỏi (Questions dialog) hiện lên hay không
            dialog = page.locator('div[role="dialog"]')
            if dialog.count() > 0:
                print("⚠️ Nhóm này yêu cầu trả lời câu hỏi thành viên.")
                close_btn = dialog.locator('div[role="button"][aria-label="Đóng"], div[role="button"][aria-label="Close"], div[role="button"]:has-text("Hủy"), div[role="button"]:has-text("Cancel")').first
                if close_btn.count() > 0:
                    close_btn.click()
                    print("Đã tự động đóng bảng câu hỏi.")
                    random_delay(2, 4)
            
            # Ghi log
            with open(log_file_path, "a", encoding="utf-8") as log_f:
                log_f.write(f"Đã tham gia nhóm '{group_name}' ({group_url}) vào lúc {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                
            joined_count += 1
            if joined_count > 0 and joined_count % 5 == 0:
                print(f"✅ Đã gửi yêu cầu tham gia thành công. Đã xong 1 batch 5 nhóm (Tổng cộng: {joined_count} nhóm). Nghỉ 30 giây...")
                random_delay(30, 32)
            else:
                print(f"✅ Đã gửi yêu cầu tham gia thành công. Chờ 8-10 giây giãn cách để xử lý nhóm tiếp theo...")
                random_delay(8, 10)
            
        except Exception as ex:
            print(f"❌ Gặp lỗi khi xử lý nhóm '{group_name}': {ex}")
            traceback.print_exc()

    print(f"\n🎉 HOÀN THÀNH! Đã thực hiện gửi yêu cầu tham gia {joined_count} nhóm mới từ file crawled.")
    print(f"Nhật ký chạy được lưu tại: {log_file_path}")
    
    try:
        page.close()
        print("ℹ️ Đã đóng tab tự động hóa.")
    except Exception as e:
        print(f"⚠️ Không thể đóng tab: {e}")

if __name__ == "__main__":
    # Nhận từ khóa từ dòng lệnh, nếu không có thì mặc định là "việc làm tây ninh"
    keyword_input = sys.argv[1] if len(sys.argv) > 1 else "việc làm tây ninh"
    
    with sync_playwright() as p:
        run(p, keyword_input)
