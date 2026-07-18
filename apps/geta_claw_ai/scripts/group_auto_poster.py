import time
import os
import random
import json
import traceback
from datetime import datetime
from playwright.sync_api import sync_playwright

# Nội dung bài đăng mặc định (fallback nếu không chạy chiến dịch tùy chọn)
DEFAULT_CONTENT = """🚀 [GÓC TUYỂN DỤNG] TÌM ĐỒNG ĐỘI THIẾT KẾ 3D VỀ CHUNG NHÀ! 🚀

Nhà Phân Phối Ly Nhựa Tây Ninh đang tìm kiếm một nhân tài "múa chuột" 3D!

🔥 VỊ TRÍ: Nhân viên Thiết kế 3D
💸 LƯƠNG: Thỏa thuận (Đảm bảo xứng đáng với năng lực!)
📞 Liên hệ ngay: 0919 511 911

Yêu cầu: Có kinh nghiệm thiết kế 3D.
Ứng tuyển ngay nhé mọi người ơi!"""

def random_delay(min_sec=2, max_sec=5):
    time.sleep(random.uniform(min_sec, max_sec))

def run(playwright):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_file_path = os.path.join(script_dir, "campaign_config.json")
    
    # 1. Khởi động cấu hình chiến dịch
    profile_type = "user"
    page_name = ""
    post_content = DEFAULT_CONTENT
    image_file = None
    groups = []
    
    if os.path.exists(config_file_path):
        print(f"📖 Tìm thấy file cấu hình chiến dịch: {config_file_path}")
        try:
            with open(config_file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                
            profile_type = config.get("profile_type", "user")
            page_name = config.get("page_name", "")
            groups = config.get("groups", [])
            
            # Đọc nội dung bài viết từ file được chọn
            content_filename = config.get("content_file", "")
            if content_filename:
                # Nếu là tên file, ghép với thư mục content
                if not os.path.isabs(content_filename):
                    content_path = os.path.join(script_dir, "content", content_filename)
                else:
                    content_path = content_filename
                    
                if os.path.exists(content_path):
                    with open(content_path, "r", encoding="utf-8") as cf:
                        post_content = cf.read()
                    print(f"✅ Đã nạp nội dung bài viết từ: {content_path}")
                else:
                    print(f"⚠️ Không tìm thấy file nội dung: {content_path}, dùng mặc định.")
            
            # Định vị file ảnh
            image_filename = config.get("image_file", "")
            if image_filename:
                if not os.path.isabs(image_filename):
                    image_file = os.path.join(script_dir, "images", image_filename)
                else:
                    image_file = image_filename
                
                if os.path.exists(image_file):
                    print(f"✅ Đã xác định file ảnh đính kèm: {image_file}")
                else:
                    print(f"⚠️ Không tìm thấy file ảnh: {image_file}")
                    image_file = None
                    
        except Exception as e:
            print(f"❌ Lỗi đọc cấu hình chiến dịch: {e}")
            traceback.print_exc()
    else:
        print("💡 Không thấy file cấu hình chiến dịch, chạy mặc định sử dụng file target_groups.txt.")
        # Đọc danh sách group mặc định
        groups_file_path = os.path.join(script_dir, "target_groups.txt")
        try:
            with open(groups_file_path, "r", encoding="utf-8") as f:
                groups = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"❌ Không tìm thấy file nhóm tại: {groups_file_path}")
            return

    if not groups:
        print("❌ Không có group nào để đăng bài.")
        return

    # Tải lịch sử các nhóm đã đăng hôm nay để lọc trùng
    posted_history_file = os.path.join(script_dir, "posted_groups.json")
    posted_history = {}
    if os.path.exists(posted_history_file):
        try:
            with open(posted_history_file, "r", encoding="utf-8") as hf:
                posted_history = json.load(hf)
        except Exception as e:
            print(f"⚠️ Không thể đọc lịch sử đăng bài: {e}")
            
    today_str = datetime.now().strftime("%Y-%m-%d")
    filtered_groups = []
    for url in groups:
        clean_url = url.strip().rstrip('/')
        if posted_history.get(clean_url) == today_str:
            print(f"⏭️ Bỏ qua Group (Đã đăng bài hôm nay): {url}")
        else:
            filtered_groups.append(url)
            
    groups = filtered_groups
    if not groups:
        print("⏭️ Tất cả các nhóm mục tiêu đều đã được đăng bài trong ngày hôm nay!")
        return

    # 2. Kết nối tới Chrome
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
        traceback.print_exc()
        return
    
    # Bỏ qua dòng input chờ đăng nhập nếu chạy tự động hoàn toàn từ Celery (giả định đã đăng nhập ở bước trước)
    # Nhưng nếu chạy từ CLI thì vẫn cần, ta sẽ kiểm tra xem có cờ tự động không
    if not os.path.exists(config_file_path):
        page.goto("https://www.facebook.com")
        input("\n➡ Sau khi đã ĐĂNG NHẬP THÀNH CÔNG và thấy Trang chủ Facebook, hãy quay lại đây nhấn phím [ENTER] để bắt đầu chạy đăng bài: ")
    
    print(f"📋 Bắt đầu chiến dịch đăng bài lên {len(groups)} group...")

    for url in groups:
        try:
            print(f"\n➡️ Đang vào Group: {url}")
            page.goto(url)
            print("Đợi 5-8 giây sau khi tải trang nhóm...")
            random_delay(5, 8)
            
            # Cố gắng tìm ô đăng bài (Thường có chữ "Bạn viết gì đi", "Write something", "Tạo bài viết công khai...")
            print("Đang tìm ô viết bài...")
            box = page.locator('div[role="button"]:has-text("Bạn viết gì đi"), div[role="button"]:has-text("Write something"), div[role="button"]:has-text("Tạo bài viết công khai..."), div[role="button"]:has-text("Create a public post...")').first
            
            if box.count() > 0:
                box.click(force=True)
                print("Đang chờ bảng Tạo bài viết hiện lên...")
                
                # Chờ cho đến khi hộp thoại Tạo bài viết (dialog) xuất hiện (Dự phòng nếu là inline thì bỏ qua)
                dialog_opened = False
                try:
                    page.wait_for_selector('div[role="dialog"]', timeout=3000)
                    dialog_opened = True
                    print("✅ Đã phát hiện hộp thoại Tạo bài viết dạng Popup (dialog).")
                except:
                    print("ℹ️ Không xuất hiện popup dialog, có thể ô soạn thảo là dạng Inline.")
                
                print("Đợi 4-6 giây sau khi nhấn ô viết bài...")
                random_delay(4, 6)
                scope = 'div[role="dialog"]' if dialog_opened else ""
                
                # CHUYỂN PROFILE ĐĂNG BÀI (Nếu cấu hình yêu cầu đăng dưới tư cách Page)
                if profile_type == "page" and page_name:
                    print(f"Đang kiểm tra nút chuyển đổi profile sang Page: '{page_name}'...")
                    switcher_selectors = [
                        f'{scope} div[role="button"][aria-label*="Đăng với tư cách"]' if scope else 'div[role="button"][aria-label*="Đăng với tư cách"]',
                        f'{scope} div[role="button"][aria-label*="Post as"]' if scope else 'div[role="button"][aria-label*="Post as"]'
                    ]
                    profile_switcher = None
                    for selector in switcher_selectors:
                        switcher = page.locator(selector).first
                        if switcher.count() > 0:
                            profile_switcher = switcher
                            break
                            
                    if profile_switcher:
                        profile_switcher.click()
                        random_delay(2, 4)
                        page_option = page.locator(f'div[role="menuitem"]:has-text("{page_name}"), div[role="menuitemcheckbox"]:has-text("{page_name}")').first
                        if page_option.count() > 0:
                            page_option.click()
                            print(f"✅ Đã click chuyển sang Page: {page_name}")
                            random_delay(3, 5)
                        else:
                            print(f"⚠️ Không tìm thấy Page '{page_name}' trong danh sách switcher. Giữ mặc định.")
                    else:
                        print("ℹ️ Không tìm thấy nút chuyển profile, đăng dưới tư cách User mặc định.")
                
                # Nhập nội dung
                print("Đang nhập nội dung bài viết...")
                # Thêm khoảng trắng và dấu xuống dòng ở cuối bài để không bị dính gợi ý hashtag của Facebook làm kẹt nút Đăng
                post_content_with_space = post_content.strip() + " \n"
                
                try:
                    # Hộp bình luận cũng mang thuộc tính contenteditable=true, nên cần lọc bỏ chúng
                    textbox_selectors = [
                        f'{scope} [contenteditable="true"]' if scope else None,
                        'div[role="dialog"] [contenteditable="true"]',
                        '[contenteditable="true"][aria-label*="nghĩ"]',
                        '[contenteditable="true"][aria-label*="viết"]',
                        '[contenteditable="true"][aria-label*="something"]',
                        '[contenteditable="true"][aria-label*="mind"]',
                        '[contenteditable="true"][aria-label*="công khai"]',
                        '[contenteditable="true"][aria-label*="public"]',
                        '[contenteditable="true"]',
                        '[role="textbox"]'
                    ]
                    textbox_selectors = [s for s in textbox_selectors if s]
                    
                    textbox = None
                    for selector in textbox_selectors:
                        try:
                            elements = page.locator(selector)
                            count = elements.count()
                            for idx in range(count):
                                el = elements.nth(idx)
                                if el.is_visible():
                                    label = el.get_attribute("aria-label") or ""
                                    placeholder = el.get_attribute("placeholder") or ""
                                    text_val = (label + " " + placeholder).lower()
                                    if any(word in text_val for word in ["bình luận", "comment", "reply", "phản hồi", "tìm kiếm", "search"]):
                                        continue
                                    textbox = el
                                    break
                            if textbox:
                                break
                        except Exception:
                            continue
                            
                    if not textbox:
                        textbox = page.locator('[contenteditable="true"]').first
                        
                    textbox.wait_for(state="visible", timeout=10000)
                    textbox.click(force=True)
                    textbox.focus()
                    page.keyboard.insert_text(post_content_with_space)
                    print("Đợi 4-6 giây sau khi nhập text...")
                    random_delay(4, 6)
                    
                    # Kiểm tra xem text đã được điền chưa (nếu rỗng thì dùng giải pháp dự phòng JavaScript)
                    current_text = textbox.inner_text().strip()
                    if not current_text:
                        print("⚠️ Nhập bằng bàn phím trống hoặc lỗi, sử dụng JavaScript dự phòng...")
                        post_content_html = post_content_with_space.replace('\n', '<br>')
                        textbox.evaluate('(el, val) => { el.innerHTML = val; el.dispatchEvent(new Event("input", { bubbles: true })); }', post_content_html)
                        random_delay(2, 3)
                except Exception as text_err:
                    print(f"⚠️ Gặp lỗi khi nhập text bằng Playwright, dùng JS dự phòng: {text_err}")
                    try:
                        post_content_html = post_content_with_space.replace('\n', '<br>')
                        page.evaluate(f'''
                            (html) => {{
                                const editors = Array.from(document.querySelectorAll('[contenteditable="true"], [role="textbox"]'));
                                const activeEditor = editors.find(el => {{
                                    const label = (el.getAttribute("aria-label") || "").lower();
                                    const placeholder = (el.getAttribute("placeholder") || "").lower();
                                    return !["bình luận", "comment", "reply", "phản hồi", "tìm", "search"].some(w => label.includes(w) || placeholder.includes(w));
                                }});
                                if (activeEditor) {{
                                    activeEditor.focus();
                                    activeEditor.innerHTML = html;
                                    activeEditor.dispatchEvent(new Event("input", {{ bubbles: true }}));
                                }} else {{
                                    const fallback = document.querySelector('[contenteditable="true"]');
                                    if (fallback) {{
                                        fallback.focus();
                                        fallback.innerHTML = html;
                                        fallback.dispatchEvent(new Event("input", {{ bubbles: true }}));
                                    }}
                                }}
                            }}
                        ''', post_content_html)
                        random_delay(2, 3)
                    except Exception as js_err:
                        print(f"❌ Cả 2 phương pháp nhập đều thất bại: {js_err}")

                # TẢI ẢNH LÊN (Nếu có ảnh đính kèm)
                if image_file and os.path.exists(image_file):
                    print(f"Đang tải ảnh đính kèm: {image_file}")
                    file_input_selector = f'{scope} input[type="file"][accept*="image"]' if scope else 'input[type="file"][accept*="image"]'
                    file_input = page.locator(file_input_selector).first
                    if file_input.count() > 0:
                        file_input.set_input_files(image_file)
                        print("✅ Đã đưa ảnh vào hàng đợi upload. Đợi 8-10 giây cho ảnh load...")
                        random_delay(8, 10)
                    else:
                        print("⚠️ Không tìm thấy ô tải ảnh ẩn. Bỏ qua tải ảnh.")
                
                # Bấm Đăng
                print("Đang bấm Đăng...")
                post_btn = None
                
                # Tạo danh sách các selector động dựa trên scope
                selectors = []
                base_labels = [
                    'div[role="button"][aria-label="Đăng"]',
                    'div[role="button"][aria-label="Post"]',
                    'div[role="button"][aria-label*="Đăng"]',
                    'div[role="button"][aria-label*="Post"]',
                    'div[role="button"]:has-text("Đăng")',
                    'div[role="button"]:has-text("Post")',
                    'div[role="button"]:has-text("Đăng bài viết")'
                ]
                if scope:
                    for label in base_labels:
                        selectors.append(f"{scope} {label}")
                for label in base_labels:
                    selectors.append(label)
                    
                for selector in selectors:
                    btn = page.locator(selector).first
                    if btn.count() > 0 and btn.is_visible():
                        post_btn = btn
                        break
                        
                success_posted = False
                if post_btn:
                    post_btn.click(force=True)
                    print("✅ Đã bấm nút Đăng.")
                    success_posted = True
                else:
                    print("⚠️ Không tìm thấy nút Đăng bằng các selector chuẩn, thử click nút role=button cuối cùng...")
                    buttons_selector = f'{scope} div[role="button"]' if scope else 'div[role="button"]'
                    buttons = page.locator(buttons_selector)
                    btn_count = buttons.count()
                    
                    # Lọc lấy các nút có vẻ là nút Đăng (thường nằm ở dưới cùng)
                    clicked = False
                    for i in reversed(range(btn_count)):
                        btn = buttons.nth(i)
                        if btn.is_visible() and btn.is_enabled():
                            btn.click(force=True)
                            print(f"✅ Đã click nút thứ {i+1} trong danh sách nút có sẵn.")
                            clicked = True
                            success_posted = True
                            break
                    if not clicked:
                        print("❌ Không thể click nút đăng nào.")
                        
                if success_posted:
                    # Đợi 5-8 giây để bài viết được upload xong và xuất hiện link
                    random_delay(5, 8)
                    
                    # KIỂM TRA LỖI SPAM BLOCK
                    body_text = page.locator('body').inner_text()
                    if "we limit how often you can" in body_text.lower() or "bảo vệ cộng đồng" in body_text.lower() or "giới hạn tần suất" in body_text.lower() or "community standards" in body_text.lower():
                        print("🚨 PHÁT HIỆN FACEBOOK CHẶN SPAM TẠM THỜI (We limit how often you can post...)! DỪNG CHIẾN DỊCH NGAY LẬP TỨC ĐỂ BẢO VỆ TÀI KHOẢN!")
                        break # Dừng vòng lặp các nhóm
                        
                    post_url = None
                    try:
                        # 1. Thử lấy link từ thông báo popup / toast của Facebook
                        print("Đang quét link bài viết từ toast notification...")
                        toast_links = page.locator('a[href*="/permalink/"], a[href*="/posts/"], div[role="alert"] a')
                        for i in range(toast_links.count()):
                            href = toast_links.nth(i).get_attribute("href")
                            if href and ("permalink" in href or "posts" in href):
                                # Loại bỏ tham số tracking
                                if "?" in href:
                                    href = href.split("?")[0]
                                post_url = href
                                break
                    except Exception as le:
                        print(f"⚠️ Không lấy được link từ toast: {le}")

                    if not post_url:
                        try:
                            # 2. Dự phòng: Quét các link permalink trên Feed của nhóm vừa load
                            print("Không bắt được toast, đang quét feed trên Group...")
                            feed_links = page.locator('a[href*="/permalink/"], a[href*="/posts/"]')
                            for i in range(feed_links.count()):
                                href = feed_links.nth(i).get_attribute("href")
                                if href and ("/posts/" in href or "/permalink/" in href):
                                    if "?" in href:
                                        href = href.split("?")[0]
                                    post_url = href
                                    break
                        except Exception as fe:
                            print(f"⚠️ Không quét được feed links: {fe}")

                    if post_url:
                        print(f"✨ LẤY ĐƯỢC LINK BÀI VIẾT THÀNH CÔNG: {post_url}")
                    else:
                        print("ℹ️ Bài viết có thể đang chờ phê duyệt (Pending) hoặc không lấy được link.")

                    # Ghi nhận lịch sử ĐÃ ĐĂNG NGAY LẬP TỨC (để tránh trường hợp câu hỏi phụ lỗi làm mất lịch sử, bài pending cũng tính là đã đăng)
                    clean_url = url.strip().rstrip('/')
                    posted_history[clean_url] = today_str
                    try:
                        with open(posted_history_file, "w", encoding="utf-8") as hf:
                            json.dump(posted_history, hf, ensure_ascii=False, indent=4)
                        print("💾 Đã ghi nhận lịch sử đăng bài thành công cho nhóm này (được lưu ngay lập tức).")
                    except Exception as e:
                        print(f"⚠️ Không thể lưu lịch sử đăng bài: {e}")

                    # Lưu link bài viết vào file riêng posted_links.json
                    posted_links_file = os.path.join(script_dir, "posted_links.json")
                    posted_links = {}
                    if os.path.exists(posted_links_file):
                        try:
                            with open(posted_links_file, "r", encoding="utf-8") as lf:
                                posted_links = json.load(lf)
                        except:
                            pass
                    posted_links[clean_url] = {
                        "date": today_str,
                        "post_url": post_url or "Chờ duyệt / Không lấy được link"
                    }
                    try:
                        with open(posted_links_file, "w", encoding="utf-8") as lf:
                            json.dump(posted_links, lf, ensure_ascii=False, indent=4)
                        print("💾 Đã ghi nhận link bài viết vào posted_links.json")
                    except Exception as le:
                        print(f"⚠️ Không thể lưu link bài viết: {le}")

                    # Trả lời câu hỏi / duyệt nội quy (được bọc trong try-except riêng biệt để không ảnh hưởng đến luồng chính)
                    try:
                        # Đợi 3-5 giây xem có xuất hiện hộp thoại trả lời câu hỏi / đồng ý quy tắc không
                        random_delay(3, 5)
                        active_dialogs = page.locator('div[role="dialog"]')
                        dialog_count = active_dialogs.count()
                        if dialog_count > 0:
                            dialog = active_dialogs.last
                            dialog_text = dialog.inner_text().lower()
                            if any(word in dialog_text for word in ["câu hỏi", "quy tắc", "rule", "question", "yêu cầu", "tham gia"]):
                                print("📋 Phát hiện biểu mẫu câu hỏi/quy tắc của nhóm. Đang tự động điền...")
                                
                                # 1. Click tất cả các ô checkbox (đồng ý quy tắc nhóm)
                                checkboxes = dialog.locator('div[role="checkbox"], input[type="checkbox"]')
                                cb_count = checkboxes.count()
                                for i in range(cb_count):
                                    cb = checkboxes.nth(i)
                                    if cb.is_visible():
                                        try:
                                            # Kiểm tra xem checkbox đã được chọn chưa trước khi click
                                            is_checked = cb.get_attribute("aria-checked") == "true" or cb.is_checked()
                                            if not is_checked:
                                                cb.click(force=True)
                                                print(f"✅ Đã chọn checkbox đồng ý {i+1}")
                                                random_delay(1, 2)
                                        except:
                                            cb.click(force=True)
                                            print(f"✅ Đã click checkbox đồng ý {i+1}")
                                            random_delay(1, 2)
                                        
                                # 2. Điền câu trả lời vào các ô nhập văn bản (textarea / input)
                                text_inputs = dialog.locator('textarea, input[type="text"]')
                                ti_count = text_inputs.count()
                                for i in range(ti_count):
                                    ti = text_inputs.nth(i)
                                    if ti.is_visible():
                                        ti.click(force=True)
                                        ti.focus()
                                        ti.fill("ok")
                                        print(f"✅ Đã tự động điền 'ok' cho câu hỏi {i+1}")
                                        random_delay(1, 2)
                                        
                                # 3. Tìm nút gửi câu trả lời
                                submit_btn = None
                                submit_selectors = [
                                    'div[role="dialog"] div[role="button"][aria-label="Gửi"]',
                                    'div[role="dialog"] div[role="button"][aria-label="Submit"]',
                                    'div[role="dialog"] div[role="button"][aria-label="Xong"]',
                                    'div[role="dialog"] div[role="button"][aria-label="Done"]',
                                    'div[role="dialog"] div[role="button"]:has-text("Gửi")',
                                    'div[role="dialog"] div[role="button"]:has-text("Submit")',
                                    'div[role="dialog"] div[role="button"]:has-text("Xong")',
                                    'div[role="dialog"] div[role="button"]:has-text("Done")'
                                ]
                                for selector in submit_selectors:
                                    btn = page.locator(selector).first
                                    if btn.count() > 0 and btn.is_visible():
                                        submit_btn = btn
                                        break
                                
                                if submit_btn:
                                    submit_btn.click(force=True)
                                    print("✅ Đã bấm gửi câu trả lời phê duyệt bài viết.")
                                    random_delay(3, 5)
                                else:
                                    print("⚠️ Không tìm thấy nút Gửi câu trả lời cụ thể, thử click nút cuối cùng trong hộp thoại câu hỏi...")
                                    q_buttons = dialog.locator('div[role="button"]')
                                    q_btn_count = q_buttons.count()
                                    if q_btn_count > 0:
                                        q_buttons.nth(q_btn_count - 1).click(force=True)
                                        print("✅ Đã click nút cuối cùng trong hộp thoại câu hỏi.")
                                        random_delay(3, 5)
                    except Exception as q_err:
                        print(f"⚠️ Gặp lỗi khi tự động trả lời câu hỏi phụ (bỏ qua để tiếp tục): {q_err}")
                
                # Chờ bài đăng gửi xong trước khi sang nhóm khác
                print("Đợi 120-180 giây (2-3 phút) để tránh bị Facebook đánh dấu SPAM...")
                random_delay(120, 180)
                print("✅ XONG 1 GROUP!")
            else:
                print("⚠️ Không tìm thấy ô viết bài. Có thể bạn chưa tham gia nhóm này.")
                
        except Exception as e:
            print(f"❌ Lỗi khi đăng bài vào {url}: {str(e)}")
            traceback.print_exc()

    print("🎉 KẾT THÚC CHIẾN DỊCH AUTO POST!")
    
    # Xóa file config tạm sau khi chạy xong
    if os.path.exists(config_file_path):
        try:
            os.remove(config_file_path)
            print("🗑️ Đã xóa file cấu hình tạm sau khi hoàn tất chiến dịch.")
        except:
            pass
            
    try:
        page.close()
        print("ℹ️ Đã đóng tab tự động hóa.")
    except Exception as e:
        print(f"⚠️ Không thể đóng tab: {e}")

if __name__ == "__main__":
    with sync_playwright() as p:
        run(p)
