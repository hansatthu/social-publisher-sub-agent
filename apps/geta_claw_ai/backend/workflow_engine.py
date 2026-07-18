import os
import requests
import logging
import json
import uuid

logger = logging.getLogger(__name__)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

ACTIVE_WORKFLOWS = {}
SITE_SELECTIONS = {}

def start_site_selection_workflow(chat_id: int, article_id: int, available_sites: list):
    """
    Hiển thị giao diện chọn website cho bài viết.
    """
    SITE_SELECTIONS[article_id] = {
        "chat_id": chat_id,
        "sites": available_sites,
        "selected": []
    }
    
    keyboard = {"inline_keyboard": []}
    for idx, site in enumerate(available_sites):
        # Mặc định chưa chọn ❌
        btn_text = f"❌ {site}"
        callback_data = f"site_sel_{article_id}_{idx}"
        keyboard["inline_keyboard"].append([{"text": btn_text, "callback_data": callback_data}])
        
    # Thêm nút Xác nhận
    keyboard["inline_keyboard"].append([{"text": "✅ Xác nhận đăng", "callback_data": f"site_confirm_{article_id}"}])
    
    msg = f"📝 *Chọn Website Đăng Bài*\nBài viết (ID: {article_id}) đã sẵn sàng.\nVui lòng tick chọn các website bạn muốn đăng bài lên, sau đó bấm Xác nhận."
    send_telegram_message(chat_id, msg, reply_markup=json.dumps(keyboard))

def handle_site_selection(article_id: int, idx: int, message_id: int):
    """
    Xử lý khi người dùng click vào một nút website để toggle chọn/bỏ chọn.
    """
    selection = SITE_SELECTIONS.get(article_id)
    if not selection:
        return
        
    site = selection["sites"][idx]
    if site in selection["selected"]:
        selection["selected"].remove(site)
    else:
        selection["selected"].append(site)
        
    # Cập nhật lại bàn phím
    keyboard = {"inline_keyboard": []}
    for i, s in enumerate(selection["sites"]):
        btn_text = f"✅ {s}" if s in selection["selected"] else f"❌ {s}"
        callback_data = f"site_sel_{article_id}_{i}"
        keyboard["inline_keyboard"].append([{"text": btn_text, "callback_data": callback_data}])
        
    keyboard["inline_keyboard"].append([{"text": "✅ Xác nhận đăng", "callback_data": f"site_confirm_{article_id}"}])
    
    msg = f"📝 *Chọn Website Đăng Bài*\nBài viết (ID: {article_id}) đã sẵn sàng.\nVui lòng tick chọn các website bạn muốn đăng bài lên, sau đó bấm Xác nhận."
    edit_telegram_message(selection["chat_id"], message_id, msg, reply_markup=json.dumps(keyboard))

def start_category_selection_workflow(chat_id: int, article_id: int, selected_sites: list):
    """
    Hỏi Category khi đã biết (các) trang web đích.
    """
    try:
        import sys
        import os
        from dotenv import load_dotenv
        import json
        blog_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../blog_tool'))
        if blog_dir not in sys.path:
            sys.path.append(blog_dir)
            
        load_dotenv(os.path.join(blog_dir, '.env'))
        from integrations.wordpress import WordPressPublisher
        
        # Get credentials for the first site
        first_site = selected_sites[0]
        config_path = os.path.join(os.path.dirname(__file__), 'task_config.json')
        
        wp_user = ""
        wp_pass = ""
        wp_url = f"https://{first_site}"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            creds = config.get("sites", {}).get(first_site, {})
            wp_user = creds.get("wp_user", os.getenv(f"WP_USERNAME_{first_site}"))
            wp_pass = creds.get("wp_app_password", os.getenv(f"WP_APP_PASSWORD_{first_site}"))
            wp_url = creds.get("wp_url", wp_url)
        except:
            pass
        
        categories = []
        if wp_user and wp_pass:
            wp_pub = WordPressPublisher(site_url=wp_url, username=wp_user, app_password=wp_pass)
            try:
                categories = wp_pub.list_categories()
            except Exception as ex:
                logger.error(f"Failed to fetch categories: {ex}")
                
        # Store state for next step
        CATEGORY_SELECTIONS[article_id] = {
            "chat_id": chat_id,
            "selected_sites": selected_sites,
            "categories": categories
        }
        
        # Render category selection UI
        keyboard = []
        if categories:
            for cat in categories:
                cat_name = cat.get('name', 'Unknown')
                keyboard.append([{"text": cat_name, "callback_data": f"cat_sel_{article_id}_{cat_name}"[:64]}])
        else:
            keyboard.append([{"text": "Mặc định (Không xác định được)", "callback_data": f"cat_sel_{article_id}_default"}])
            
        markup = {"inline_keyboard": keyboard}
        msg = f"✅ Đã chốt {len(selected_sites)} websites.\n\n" + "Vui lòng chọn **Chuyên mục (Category)** bạn muốn đăng:"
        
        # We don't have message_id here, so we send a new message
        send_telegram_message(chat_id, msg, reply_markup=json.dumps(markup))
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        send_telegram_message(chat_id, f"❌ Lỗi khi tải danh sách Category: {e}")

def handle_site_confirm(article_id: int, message_id: int):
    """
    Xử lý khi người dùng click Xác nhận Website.
    Lấy danh sách category từ trang đầu tiên và hiển thị bước chọn Category.
    """
    selection = SITE_SELECTIONS.get(article_id)
    if not selection:
        return
        
    selected_sites = selection["selected"]
    if not selected_sites and selection["sites"]:
        selected_sites = [selection["sites"][0]]
        
    try:
        import sys
        import os
        from dotenv import load_dotenv
        blog_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../blog_tool'))
        if blog_dir not in sys.path:
            sys.path.append(blog_dir)
            
        load_dotenv(os.path.join(blog_dir, '.env'))
        from integrations.wordpress import WordPressPublisher
        
        # Get credentials for the first site
        first_site = selected_sites[0]
        wp_user = os.getenv(f"WP_USERNAME_{first_site}")
        wp_pass = os.getenv(f"WP_APP_PASSWORD_{first_site}")
        
        categories = []
        if wp_user and wp_pass:
            wp_pub = WordPressPublisher(site_url=f"https://{first_site}", username=wp_user, app_password=wp_pass)
            try:
                categories = wp_pub.list_categories()
            except Exception as ex:
                logger.error(f"Failed to fetch categories: {ex}")
                
        # Store state for next step
        CATEGORY_SELECTIONS[article_id] = {
            "chat_id": selection["chat_id"],
            "selected_sites": selected_sites,
            "categories": categories
        }
        
        # Render category selection UI
        keyboard = []
        if categories:
            for cat in categories:
                cat_name = cat.get('name', 'Unknown')
                # Use a safe short name for callback data if needed, but ID is better
                keyboard.append([{"text": cat_name, "callback_data": f"cat_sel_{article_id}_{cat_name}"[:64]}])
        else:
            keyboard.append([{"text": "Mặc định (Không xác định được)", "callback_data": f"cat_sel_{article_id}_default"}])
            
        markup = {"inline_keyboard": keyboard}
        msg = f"✅ Đã chốt {len(selected_sites)} websites.\n\n" + "Vui lòng chọn **Chuyên mục (Category)** bạn muốn đăng:"
        edit_telegram_message(selection["chat_id"], message_id, msg, reply_markup=json.dumps(markup))
        
        # Xóa khỏi bộ nhớ
        del SITE_SELECTIONS[article_id]
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        edit_telegram_message(selection["chat_id"], message_id, f"❌ Lỗi khi tải danh sách Category: {e}")

def handle_category_confirm(article_id: int, message_id: int, category_name: str):
    """
    Xử lý khi người dùng chọn một Category.
    Lưu vào DB, chuyển trạng thái PENDING và gọi Celery publish_blog_task.
    """
    selection = CATEGORY_SELECTIONS.get(article_id)
    if not selection:
        return
        
    selected_sites = selection["selected_sites"]
    
    try:
        import sys
        import os
        import json
        blog_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../blog_tool'))
        if blog_dir not in sys.path:
            sys.path.append(blog_dir)
            
        from database.session import SessionLocal
        from database.models import Article, ArticleStatus
        
        with SessionLocal() as db:
            article = db.query(Article).filter(Article.id == article_id).first()
            if article:
                article.target_sites = json.dumps(selected_sites)
                article.status = ArticleStatus.PENDING
                db.commit()
                
        # Gọi Celery
        from backend.celery_app import celery_app
        try:
            # Truyền category_name cho task publish
            celery_app.send_task("tasks.publish_blog_task", args=[article_id, category_name])
        except Exception:
            import subprocess
            tasks_script = os.path.abspath(os.path.join(os.path.dirname(__file__), 'tasks.py')).replace('\\', '/')
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            subprocess.Popen([sys.executable, "-c", f"import sys, os; sys.path.append(os.path.dirname('{tasks_script}')); from tasks import publish_blog_task; publish_blog_task({article_id}, '{category_name}')"], env=env)
            
        # Cập nhật UI Telegram
        msg = f"✅ Đã xác nhận đăng bài viết (ID: {article_id}) vào chuyên mục **{category_name}**.\n\nTiến trình đăng bài đang chạy ngầm, vui lòng chờ..."
        edit_telegram_message(selection["chat_id"], message_id, msg) # Bỏ reply_markup để xoá nút
        
        # Xóa khỏi bộ nhớ
        del CATEGORY_SELECTIONS[article_id]
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        edit_telegram_message(selection["chat_id"], message_id, f"❌ Lỗi kích hoạt tiến trình đăng: {e}")

def send_telegram_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    res = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json=payload
    )
    if res.status_code != 200:
        logger.error(f"Failed to send message: {res.text}")

def edit_telegram_message(chat_id, message_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText",
        json=payload
    )

def start_interactive_workflow(chat_id: int):
    ACTIVE_WORKFLOWS[chat_id] = {
        "status": "awaiting_platform",
        "platforms": [],
        "profiles": [],
        "action": None,
        "data": {}
    }
    render_platform_selection(chat_id)

def render_platform_selection(chat_id: int, message_id: int = None):
    state = ACTIVE_WORKFLOWS.get(chat_id)
    if not state:
        return
        
    platforms = [
        {"id": "facebook_personal", "name": "Facebook Cá Nhân"},
        {"id": "facebook_page", "name": "Facebook Fanpage"},
        {"id": "tiktok", "name": "TikTok"},
        {"id": "website", "name": "Website (WordPress)"}
    ]
    
    keyboard = []
    for p in platforms:
        mark = "✅ " if p["id"] in state.get("platforms", []) else ""
        keyboard.append([{"text": f"{mark}{p['name']}", "callback_data": f"wf_plat_{p['id']}"}])
    
    keyboard.append([{"text": "➡️ Xác nhận", "callback_data": "wf_plat_DONE"}])
    
    markup = {"inline_keyboard": keyboard}
    text = "Vui lòng chọn **Nền tảng** bạn muốn thao tác (Có thể chọn nhiều):"
    
    if message_id:
        edit_telegram_message(chat_id, message_id, text, markup)
    else:
        send_telegram_message(chat_id, text, markup)

def start_blog_workflow_with_keyword(chat_id: int, keyword: str):
    import os
    import json
    env_path = os.path.join(os.path.dirname(__file__), '../blog_tool/.env')
    sites = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('WP_USERNAME_'):
                    sites.append(line.split('=')[0].replace('WP_USERNAME_', ''))
                    
    if not sites:
        send_telegram_message(chat_id, '❌ Chưa có website nào được kết nối trong hệ thống. Vui lòng cấu hình file .env')
        return
        
    ACTIVE_WORKFLOWS[chat_id] = {
        'status': 'awaiting_blog_site',
        'data': {'keyword': keyword},
        'sites_list': sites
    }
    
    keyboard = {'inline_keyboard': []}
    for idx, site in enumerate(sites):
        keyboard['inline_keyboard'].append([{'text': f'🌐 {site}', 'callback_data': f'wf_blog_site_{idx}'}])
        
    send_telegram_message(chat_id, f"📝 Đã ghi nhận từ khoá: '{keyword}'.\n\n🌐 Vui lòng chọn Website để đăng bài (hệ thống sẽ kết nối để lấy ảnh từ web này):", reply_markup=json.dumps(keyboard))


def start_website_workflow(chat_id: int):
    ACTIVE_WORKFLOWS[chat_id] = {
        "status": "awaiting_profiles",
        "platforms": ["website"],
        "profiles": []
    }
    render_profile_selection(chat_id)

def render_profile_selection(chat_id: int, message_id: int = None):
    state = ACTIVE_WORKFLOWS.get(chat_id)
    if not state:
        return
    
    platforms = state.get("platforms", [])
    if not platforms:
        text = "⚠️ Bạn chưa chọn nền tảng nào! Vui lòng chọn lại:"
        if message_id:
            edit_telegram_message(chat_id, message_id, text)
        render_platform_selection(chat_id)
        return

    all_profiles = [
        {"id": "fb_1", "platform": "facebook_personal", "name": "FB Cá Nhân 1"},
        {"id": "fb_2", "platform": "facebook_personal", "name": "FB Cá Nhân 2"},
        {"id": "page_1", "platform": "facebook_page", "name": "Fanpage Geta 1"},
        {"id": "tk_1", "platform": "tiktok", "name": "TikTok Kênh 1"},
        {"id": "tk_2", "platform": "tiktok", "name": "TikTok Kênh 2"}
    ]
    
    import os
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../blog_tool/.env'))
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("WP_USERNAME_"):
                    site = line.split('=')[0].replace("WP_USERNAME_", "").strip()
                    all_profiles.append({"id": f"web_{site}", "platform": "website", "name": site})
                    
    
    filtered_profiles = [p for p in all_profiles if p["platform"] in platforms]
    
    if not filtered_profiles:
        state["status"] = "awaiting_action"
        render_action_selection(chat_id, message_id)
        return
        
    keyboard = []
    for p in filtered_profiles:
        mark = "✅ " if p["id"] in state.get("profiles", []) else ""
        keyboard.append([{"text": f"{mark}[{p['platform'].split('_')[-1].upper()}] {p['name']}", "callback_data": f"wf_prof_{p['id']}"}])
        
    keyboard.append([{"text": "➡️ Xác nhận", "callback_data": "wf_prof_DONE"}])
    
    markup = {"inline_keyboard": keyboard}
    text = "Vui lòng chọn **Tài khoản** bạn muốn thao tác (Có thể chọn nhiều):"
    
    if message_id:
        edit_telegram_message(chat_id, message_id, text, markup)
    else:
        send_telegram_message(chat_id, text, markup)


def render_folder_selection(chat_id: int, message_id: int = None):
    state = ACTIVE_WORKFLOWS.get(chat_id)
    if not state: return
    
    import os
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "content/b_rolls"))
    os.makedirs(base_dir, exist_ok=True)
    
    folders = [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))]
    
    keyboard = []
    for f in folders:
        keyboard.append([{"text": f"📁 {f}", "callback_data": f"wf_fld_{f}"}])
    keyboard.append([{"text": "➕ Tạo thư mục mới", "callback_data": "wf_fld_NEW"}])
    
    markup = {"inline_keyboard": keyboard}
    text = "Vui lòng chọn **Thư mục chứa Video nguồn (B-roll)**:\n*(Nếu file nặng > 20MB, hãy sử dụng giao diện Web Dashboard của Geta để tải lên thay vì Bot nhé)*"
    
    if message_id:
        edit_telegram_message(chat_id, message_id, text, markup)
    else:
        send_telegram_message(chat_id, text, markup)


def render_action_selection(chat_id: int, message_id: int = None):
    state = ACTIVE_WORKFLOWS.get(chat_id)
    if not state:
        return
        
    platforms = state.get("platforms", [])
    
    actions = []
    if "facebook_personal" in platforms or "facebook_page" in platforms:
        actions.extend([
            {"id": "post", "name": "Đăng bài"},
            {"id": "join_group", "name": "Tham gia nhóm (Join Groups)"},
            {"id": "post_group", "name": "Đăng bài vào Nhóm"},
            {"id": "crawl", "name": "Quét Đối thủ / Lead (Crawl4AI)"}
        ])
    if "tiktok" in platforms:
        actions.extend([
            {"id": "post_video", "name": "Đăng Video (Có sẵn)"},
            {"id": "create_video", "name": "Tạo Video AI Mới"}
        ])
    if "website" in platforms:
        actions.extend([
            {"id": "blog", "name": "Viết Blog SEO"}
        ])
        
    unique_actions = {a["id"]: a for a in actions}.values()
    
    keyboard = []
    for a in unique_actions:
        keyboard.append([{"text": a["name"], "callback_data": f"wf_act_{a['id']}"}])
        
    markup = {"inline_keyboard": keyboard}
    text = "Vui lòng chọn **Kỹ năng (Action)** bạn muốn thực hiện:"
    
    if message_id:
        edit_telegram_message(chat_id, message_id, text, markup)
    else:
        send_telegram_message(chat_id, text, markup)

def handle_workflow_callback(chat_id: int, message_id: int, callback_data: str):
    if chat_id not in ACTIVE_WORKFLOWS:
        send_telegram_message(chat_id, "⏳ Luồng làm việc đã hết hạn hoặc không tồn tại. Vui lòng chat lại yêu cầu.")
        return
        
    state = ACTIVE_WORKFLOWS[chat_id]
    
    if callback_data.startswith("wf_plat_"):
        plat_id = callback_data.replace("wf_plat_", "")
        if plat_id == "DONE":
            state["status"] = "awaiting_profile"
            render_profile_selection(chat_id, message_id)
        else:
            if plat_id in state["platforms"]:
                state["platforms"].remove(plat_id)
            else:
                state["platforms"].append(plat_id)
            render_platform_selection(chat_id, message_id)
            
    elif callback_data.startswith("wf_prof_"):
        prof_id = callback_data.replace("wf_prof_", "")
        if prof_id == "DONE":
            state["status"] = "awaiting_action"
            render_action_selection(chat_id, message_id)
        else:
            if prof_id in state["profiles"]:
                state["profiles"].remove(prof_id)
            else:
                state["profiles"].append(prof_id)
            render_profile_selection(chat_id, message_id)
            
    elif callback_data.startswith("wf_act_"):
        action = callback_data.replace("wf_act_", "")
        state["action"] = action
        execute_action_branch(chat_id, message_id, state)
        
    elif callback_data.startswith("wf_sub_"):
        handle_subflow_callback(chat_id, message_id, callback_data, state)
        
    elif callback_data.startswith("wf_blog_site_"):
        idx = int(callback_data.replace("wf_blog_site_", ""))
        site = state.get("sites_list", [])[idx]
        state["data"]["target_site"] = site
        state["status"] = "awaiting_blog_image_source"
        
        markup = {"inline_keyboard": [
            [{"text": "📤 Tải ảnh trực tiếp (Upload)", "callback_data": "wf_blog_img_upload"}],
            [{"text": "🖼️ Chọn từ thư viện WordPress", "callback_data": "wf_blog_img_wp"}],
            [{"text": "⏭️ Không dùng ảnh", "callback_data": "wf_blog_img_skip"}]
        ]}
        edit_telegram_message(chat_id, message_id, f"✅ Đã chọn website: **{site}**\n\n❓ Bạn muốn cung cấp hình ảnh cho bài viết này bằng cách nào?", markup)
        
    elif callback_data == "wf_blog_img_upload":
        state["status"] = "awaiting_blog_images_upload"
        state["data"]["source_images"] = []
        edit_telegram_message(chat_id, message_id, "📤 Vui lòng **gửi (các) file ảnh** trực tiếp vào chat.\n\nSau khi nộp đủ ảnh, hãy chat chữ **'xong'** để hệ thống bắt đầu tạo bài viết!")
        
    elif callback_data == "wf_blog_img_skip":
        from core_agent import submit_blog_task_to_celery
        keyword = state["data"]["keyword"]
        target_site = state["data"]["target_site"]
        edit_telegram_message(chat_id, message_id, f"⏳ Đang giao việc cho AI viết bài với từ khoá: '{keyword}' (Không ảnh)...")
        try:
            # We can invoke it directly or create Article in DB directly
            result = submit_blog_task_to_celery(keyword, target_site)
            send_telegram_message(chat_id, str(result))
        except Exception as e:
            send_telegram_message(chat_id, f"❌ Lỗi khi viết blog: {str(e)}")
        del ACTIVE_WORKFLOWS[chat_id]
        
    elif callback_data == "wf_blog_img_wp":
        state["status"] = "awaiting_blog_img_wp"
        site = state["data"]["target_site"]
        edit_telegram_message(chat_id, message_id, f"⏳ Đang kết nối tới `{site}` để lấy danh sách ảnh mới nhất...")
        import sys
        sys.path.append("D:/GETA_WORKSPACE/python_backend/blog_tool")
        from ui.app import get_wp_publisher # Safe to use or we can create it
        from integrations.wordpress import WordPressPublisher
        import json
        config_path = "D:/GETA_WORKSPACE/python_backend/blog_tool/ui/task_config.json"
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            creds = config.get("sites", {}).get(site, {})
            wp_url = creds.get("wp_url", f"https://{site}")
            wp_user = creds.get("wp_user", "")
            wp_app_password = creds.get("wp_app_password", "")
            
            publisher = WordPressPublisher(wp_url, wp_user, wp_app_password)
            media_items = publisher.get_latest_media(limit=10)
            
            state["data"]["wp_media_list"] = media_items
            state["data"]["source_images"] = []
            
            keyboard = {"inline_keyboard": []}
            for i, item in enumerate(media_items):
                btn_text = f"❌ {item['title']}" # Default unchecked
                keyboard["inline_keyboard"].append([{"text": btn_text, "callback_data": f"wf_blog_media_{i}"}])
            keyboard["inline_keyboard"].append([{"text": "✅ XONG (Tiến hành Viết)", "callback_data": "wf_blog_media_done"}])
            
            edit_telegram_message(chat_id, message_id, "🖼️ Vui lòng chọn các hình ảnh từ thư viện WordPress:", reply_markup=json.dumps(keyboard))
        except Exception as e:
            edit_telegram_message(chat_id, message_id, f"❌ Lỗi khi kết nối WordPress: {e}")
            del ACTIVE_WORKFLOWS[chat_id]
            
    elif callback_data.startswith("wf_blog_media_"):
        if callback_data == "wf_blog_media_done":
            selected_ids = state["data"].get("source_images", [])
            keyword = state["data"]["keyword"]
            target_site = state["data"]["target_site"]
            if not selected_ids:
                edit_telegram_message(chat_id, message_id, "⚠️ Bạn chưa chọn ảnh nào. Quá trình tạo blog đã bị hủy.")
                del ACTIVE_WORKFLOWS[chat_id]
                return
            
            edit_telegram_message(chat_id, message_id, f"✅ Đã chọn {len(selected_ids)} ảnh.\n⏳ Đang tiến hành tạo bài viết cho từ khoá: '{keyword}'...")
            try:
                from core_agent import submit_blog_task_to_celery
                # Pass source_images as a JSON string or comma-separated
                import json
                result = submit_blog_task_to_celery(keyword, target_site, json.dumps(selected_ids))
                send_telegram_message(chat_id, str(result))
            except Exception as e:
                send_telegram_message(chat_id, f"❌ Lỗi khi tạo bài viết: {e}")
            del ACTIVE_WORKFLOWS[chat_id]
            return

        idx = int(callback_data.replace("wf_blog_media_", ""))
        media_list = state["data"].get("wp_media_list", [])
        if idx >= len(media_list): return
        selected_item = media_list[idx]
        item_id = selected_item["url"] # Store URL instead of ID for ease of injection
        
        selected_ids = state["data"].setdefault("source_images", [])
        if item_id in selected_ids:
            selected_ids.remove(item_id)
        else:
            selected_ids.append(item_id)
            
        # Re-render keyboard
        keyboard = {"inline_keyboard": []}
        for i, item in enumerate(media_list):
            is_selected = item["url"] in selected_ids
            btn_text = f"{'✅' if is_selected else '❌'} {item['title']}"
            keyboard["inline_keyboard"].append([{"text": btn_text, "callback_data": f"wf_blog_media_{i}"}])
            keyboard["inline_keyboard"].append([{"text": "✅ XONG (Tiến hành Viết)", "callback_data": "wf_blog_media_done"}])
        
        edit_telegram_message(chat_id, message_id, "🖼️ Vui lòng chọn các hình ảnh từ thư viện WordPress:", reply_markup=json.dumps(keyboard))
        
    elif callback_data.startswith("wf_fld_"):
        folder = callback_data.replace("wf_fld_", "")
        if folder == "NEW":
            state["status"] = "awaiting_new_folder_name"
            edit_telegram_message(chat_id, message_id, "📁 Vui lòng chat **Tên thư mục mới** (không dấu, không khoảng trắng, ví dụ: `tranh_dien_1`):")
        else:
            state["data"]["source_folder"] = folder
            edit_telegram_message(chat_id, message_id, f"✅ Đã chọn thư mục `{folder}`.\n\n⏳ Đang bắt đầu quá trình tạo Video...")
            start_video_generation(chat_id, state)
            del ACTIVE_WORKFLOWS[chat_id]

def execute_action_branch(chat_id: int, message_id: int, state: dict):
    action = state.get("action")
    if action in ["post", "post_group", "post_video"]:
        markup = {"inline_keyboard": [
            [{"text": "Đã có nội dung/file", "callback_data": "wf_sub_has_media"}],
            [{"text": "Chưa, nhờ AI tạo nội dung", "callback_data": "wf_sub_ai_content"}],
            [{"text": "Tạo Ảnh bằng AI", "callback_data": "wf_sub_ai_image"}]
        ]}
        state["status"] = "awaiting_content_decision"
        edit_telegram_message(chat_id, message_id, "Bạn đã chuẩn bị **Nội dung (Text/Hình ảnh/Video)** chưa?\n*(Nếu bạn gửi ảnh/video vào đây, hệ thống sẽ tự động bắt file và lưu cho tài khoản đang chọn)*", markup)
        
    elif action == "crawl":
        edit_telegram_message(chat_id, message_id, "🔍 Vui lòng chat **Từ khóa** hoặc **Đường link** mà bạn muốn Quét dữ liệu (Crawl4AI):")
        state["status"] = "awaiting_crawl_query"
        
    elif action == "join_group":
        markup = {"inline_keyboard": [
            [{"text": "Tìm nhóm theo Từ khóa", "callback_data": "wf_sub_jg_keyword"}],
            [{"text": "Nhập danh sách Link nhóm", "callback_data": "wf_sub_jg_links"}]
        ]}
        state["status"] = "awaiting_join_group_method"
        edit_telegram_message(chat_id, message_id, "Bạn muốn tham gia nhóm bằng cách nào?", markup)
        
    elif action == "create_video":
        markup = {"inline_keyboard": [
            [
                {"text": "15 Giây", "callback_data": "wf_sub_dur_15"},
                {"text": "30 Giây", "callback_data": "wf_sub_dur_30"},
                {"text": "60 Giây", "callback_data": "wf_sub_dur_60"}
            ]
        ]}
        state["status"] = "awaiting_video_duration"
        edit_telegram_message(chat_id, message_id, "Vui lòng chọn **Thời lượng Video**:", markup)
        
    elif action == "blog":
        edit_telegram_message(chat_id, message_id, "✅ Đã chọn chức năng **Viết Blog SEO**.")
        import json
        force_reply = json.dumps({"force_reply": True, "input_field_placeholder": "Nhập từ khóa..."})
        send_telegram_message(chat_id, "✍️ Vui lòng nhập **Từ khóa chính** cho bài Blog SEO:", reply_markup=force_reply)
        state["status"] = "awaiting_blog_keyword"
        
    else:
        edit_telegram_message(chat_id, message_id, f"🛠 Chức năng `{action}` đang được thiết lập. Vui lòng quay lại sau!")
        del ACTIVE_WORKFLOWS[chat_id]

def handle_subflow_callback(chat_id: int, message_id: int, callback_data: str, state: dict):
    if callback_data == "wf_sub_has_media":
        state["status"] = "awaiting_post_trigger"
        edit_telegram_message(chat_id, message_id, "✅ Đã ghi nhận! Bạn có thể gửi thêm ảnh/video vào chat (nếu có).\nSau đó chat *'bắt đầu đăng'* để thực thi lệnh RPA.")
        
    elif callback_data == "wf_sub_ai_content":
        state["status"] = "awaiting_ai_prompt"
        edit_telegram_message(chat_id, message_id, "🤖 Vui lòng chat **Chủ đề** hoặc **Từ khóa** để AI viết nội dung cho bạn:")
        
    elif callback_data == "wf_sub_ai_image":
        state["status"] = "awaiting_image_prompt"
        edit_telegram_message(chat_id, message_id, "🎨 Vui lòng miêu tả bức ảnh bạn muốn AI tạo:")

    elif callback_data.startswith("wf_sub_dur_"):
        duration = int(callback_data.split("_")[-1])
        state["data"]["duration"] = duration
        state["status"] = "awaiting_video_topic"
        edit_telegram_message(chat_id, message_id, f"⏱ Đã chọn thời lượng {duration}s.\n\n🎬 Vui lòng chat **Chủ đề video** bạn muốn tạo:")
        
    elif callback_data == "wf_sub_jg_keyword":
        state["status"] = "awaiting_jg_keyword"
        edit_telegram_message(chat_id, message_id, "🔍 Nhập **Từ khóa** để hệ thống tìm kiếm nhóm trên Facebook:")
        
    elif callback_data == "wf_sub_jg_links":
        state["status"] = "awaiting_jg_links"
        edit_telegram_message(chat_id, message_id, "🔗 Vui lòng gửi danh sách Link/UID nhóm (mỗi link một dòng):")


def start_video_generation(chat_id: int, state: dict):
    topic = state.get("data", {}).get("topic", "")
    duration = state.get("data", {}).get("duration", 30)
    source_folder = state.get("data", {}).get("source_folder", "")
    profiles = state.get("profiles", [])
    
    send_telegram_message(chat_id, f"⏳ Đang tiến hành tạo kịch bản, AI Voice và render video cho chủ đề: {topic} (Source: {source_folder})...")
    
    import threading
    def run_video_rpa():
        try:
            from video_engine.assembler import generate_faceless_tiktok
            output_path = generate_faceless_tiktok(topic=topic, duration_seconds=duration, source_folder=source_folder)
            
            from main import send_local_media_to_telegram
            send_local_media_to_telegram(chat_id, output_path)
            
            send_telegram_message(chat_id, f"✅ Đã tạo video thành công tại `{output_path}`.")
            
            if profiles:
                from rpa_executor import upload_to_tiktok
                for prof in profiles:
                    send_telegram_message(chat_id, f"⏳ Đang mở trình duyệt để upload lên tài khoản {prof}...")
                    rpa_status = upload_to_tiktok(output_path, topic, prof)
                    send_telegram_message(chat_id, f"🎉 Đã hoàn thành đăng video cho {prof}! Kết quả: {rpa_status}")
        except Exception as e:
            import traceback
            logger.error(f"Error in RPA thread: {traceback.format_exc()}")
            send_telegram_message(chat_id, f"❌ Lỗi: {str(e)}\n\n```\n{traceback.format_exc()}\n```")
    
    threading.Thread(target=run_video_rpa).start()


def process_text_input(chat_id: int, text: str) -> bool:
    if chat_id not in ACTIVE_WORKFLOWS:
        logger.info(f"[process_text_input] chat_id {chat_id} not in ACTIVE_WORKFLOWS")
        return False
        
    state = ACTIVE_WORKFLOWS[chat_id]
    status = state.get("status")
    logger.info(f"[process_text_input] chat_id {chat_id}, status={status}, text='{text}'")
    
    if status == "awaiting_video_topic":
        state["data"]["topic"] = text
        state["status"] = "awaiting_source_folder"
        render_folder_selection(chat_id)
        return True
        
    if status == "awaiting_new_folder_name":
        folder_name = text.strip()
        import os
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "content/b_rolls", folder_name))
        os.makedirs(base_dir, exist_ok=True)
        
        state["data"]["source_folder"] = folder_name
        state["status"] = "awaiting_folder_upload"
        send_telegram_message(chat_id, f"✅ Đã tạo thư mục `{folder_name}`.\n\n🎥 Anh có thể gửi trực tiếp Video/Ảnh vào chat để lưu vào thư mục này (Max 20MB/file. Gợi ý: Dùng Web UI nếu file quá nặng).\n\nKhi nào tải xong, hãy chat **'bắt đầu dựng'** để chạy.")
        return True
        
    if status == "awaiting_folder_upload":
        if "bắt đầu" in text.lower() or "btd" in text.lower():
            start_video_generation(chat_id, state)
            del ACTIVE_WORKFLOWS[chat_id]
        else:
            send_telegram_message(chat_id, f"✅ Đã nhận lệnh: '{text}'. Đang chờ upload... (Gõ 'bắt đầu dựng' khi xong)")
        return True

    if status == "awaiting_blog_images_upload":
        if "xong" in text.lower() or "ok" in text.lower():
            selected_imgs = state["data"].get("source_images", [])
            keyword = state["data"]["keyword"]
            target_site = state["data"]["target_site"]
            edit_telegram_message(chat_id, message_id=None, text=f"✅ Đã nhận {len(selected_imgs)} ảnh.\n⏳ Đang tiến hành tạo bài viết cho từ khoá: '{keyword}'...")
            try:
                from core_agent import submit_blog_task_to_celery
                import json
                result = submit_blog_task_to_celery(keyword, target_site, json.dumps(selected_imgs))
                send_telegram_message(chat_id, str(result))
            except Exception as e:
                send_telegram_message(chat_id, f"❌ Lỗi khi tạo bài viết: {e}")
            del ACTIVE_WORKFLOWS[chat_id]
        else:
            send_telegram_message(chat_id, f"✅ Đã nhận lệnh: '{text}'. Hãy tiếp tục gửi ảnh hoặc gõ 'xong' để bắt đầu.")
        return True

        
    if status == "awaiting_blog_keyword":
        state["data"] = {"keyword": text}
        state["status"] = "awaiting_blog_site"
        import json
        import os
        config_path = os.path.join(os.path.dirname(__file__), "task_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            sites = config.get("blog_sites", ["innhanhgeta.com", "lynhuatayninh.com"])
        except:
            sites = ["innhanhgeta.com", "lynhuatayninh.com"]
            
        state["sites_list"] = sites
        keyboard = {"inline_keyboard": []}
        for idx, site in enumerate(sites):
            keyboard["inline_keyboard"].append([{"text": f"🌐 {site}", "callback_data": f"wf_blog_site_{idx}"}])
            
        send_telegram_message(chat_id, f"📝 Đã ghi nhận từ khoá: '{text}'.\n\n🌐 Vui lòng chọn Website để đăng bài (hệ thống sẽ kết nối để lấy ảnh từ web này):", reply_markup=json.dumps(keyboard))
        return True
        
    if status in ["awaiting_crawl_query", "awaiting_ai_prompt", "awaiting_jg_keyword", "awaiting_jg_links", "awaiting_post_trigger", "awaiting_image_prompt"]:
        send_telegram_message(chat_id, f"✅ Đã nhận lệnh: '{text}'. Module này đang được tích hợp Crawl4AI/RPA. Vui lòng đợi bản cập nhật tiếp theo.")
        del ACTIVE_WORKFLOWS[chat_id]
        return True
        
    return False

def start_tiktok_workflow(chat_id: int, topic: str, duration: int = None):
    ACTIVE_WORKFLOWS[chat_id] = {
        "status": "awaiting_video_duration" if not duration else "awaiting_video_topic",
        "platforms": ["tiktok"],
        "profiles": [],
        "action": "create_video",
        "data": {"duration": duration}
    }
    if not duration:
        markup = {"inline_keyboard": [
            [{"text": "15 Giây", "callback_data": "wf_sub_dur_15"},
             {"text": "30 Giây", "callback_data": "wf_sub_dur_30"},
             {"text": "60 Giây", "callback_data": "wf_sub_dur_60"}]
        ]}
        send_telegram_message(chat_id, f"Dạ, anh muốn tạo video về *{topic}*.\nAnh chọn thời lượng bên dưới nhé:", markup)
    else:
        ACTIVE_WORKFLOWS[chat_id]["status"] = "awaiting_video_topic"
        process_text_input(chat_id, topic)

def handle_telegram_media(message: dict):
    chat_id = message['chat']['id']
    media_group_id = message.get('media_group_id')
    
    state = ACTIVE_WORKFLOWS.get(chat_id)
    if not state:
        send_telegram_message(chat_id, 'Bạn vừa gửi file, nhưng chưa có luồng làm việc nào được chọn. Vui lòng chat yêu cầu trước (Vd: "Tôi muốn đăng bài").')
        return
        
    platforms = state.get('platforms', [])
    profiles = state.get('profiles', [])
    
    if not profiles and state.get("action") not in ["create_video", "blog"]:
        send_telegram_message(chat_id, 'Vui lòng chọn Nền tảng và Tài khoản trước khi gửi file nhé!')
        return

    file_id = None
    if 'photo' in message:
        file_id = message['photo'][-1]['file_id']
    elif 'video' in message:
        file_id = message['video']['file_id']
    elif 'document' in message:
        file_id = message['document']['file_id']
        
    if not file_id:
        return
        
    if state.get("status") == "awaiting_blog_images_upload":
        import os, uuid
        def download_blog_img_task():
            try:
                res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}")
                res_data = res.json()
                if not res_data.get('ok'): return
                
                file_path = res_data['result']['file_path']
                ext = os.path.splitext(file_path)[1] or ".jpg"
                file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                
                r = requests.get(file_url)
                save_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "content/blog_images", str(chat_id)))
                os.makedirs(save_dir, exist_ok=True)
                
                full_path = os.path.join(save_dir, f"media_{uuid.uuid4().hex[:8]}{ext}")
                with open(full_path, "wb") as f:
                    f.write(r.content)
                    
                # Update state
                if "source_images" not in state["data"]:
                    state["data"]["source_images"] = []
                state["data"]["source_images"].append(full_path)
                
                send_telegram_message(chat_id, f"✅ Đã nhận 1 ảnh. Hãy gửi tiếp hoặc chat **'xong'** khi bạn hoàn tất.")
            except Exception as e:
                send_telegram_message(chat_id, f"❌ Lỗi tải ảnh: {e}")
        import threading
        threading.Thread(target=download_blog_img_task).start()
        return

    
    if state.get("status") == "awaiting_folder_upload":
        folder_name = state["data"]["source_folder"]
        import os, uuid
        def download_task_custom():
            try:
                res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}")
                res_data = res.json()
                if not res_data.get('ok'): return
                
                file_path = res_data['result']['file_path']
                ext = os.path.splitext(file_path)[1] or (".jpg" if "photo" in message else ".mp4")
                file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                
                r = requests.get(file_url)
                save_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "content/b_rolls", folder_name))
                os.makedirs(save_dir, exist_ok=True)
                
                full_path = os.path.join(save_dir, f"media_{uuid.uuid4().hex[:8]}{ext}")
                with open(full_path, "wb") as f:
                    f.write(r.content)
                    
                if True: # Always send msg
                    send_telegram_message(chat_id, f"✅ Đã lưu file vào `{folder_name}`. Gửi tiếp hoặc chat 'bắt đầu dựng'.")
            except Exception as e:
                if True:
                    send_telegram_message(chat_id, f"❌ Lỗi tải file: {e}")
        import threading
        threading.Thread(target=download_task_custom).start()
        return

    try:
        from main import redis_client
        if media_group_id:
            if redis_client.get(f"mg_{media_group_id}"):
                send_msg = False
            else:
                redis_client.setex(f"mg_{media_group_id}", 10, "1")
                send_msg = True
        else:
            send_msg = True
    except:
        send_msg = True
        
    if send_msg:
        send_telegram_message(chat_id, '⏳ Đang tải file/album của bạn về máy chủ...')
        
    import threading
    def download_task():
        try:
            res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}")
            res_data = res.json()
            if not res_data.get('ok'):
                logger.error(f"Failed to get file: {res_data}")
                return
                
            file_path = res_data['result']['file_path']
            ext = os.path.splitext(file_path)[1]
            if not ext:
                ext = ".jpg" if "photo" in message else ".mp4"
                
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            
            r = requests.get(file_url)
            
            saved_paths = []
            for prof in profiles:
                plat = platforms[0] if platforms else "general"
                save_dir = f"D:/GETA_WORKSPACE/python_backend/backend/content/{plat}/{prof}"
                os.makedirs(save_dir, exist_ok=True)
                
                filename = f"media_{uuid.uuid4().hex[:8]}{ext}"
                full_path = os.path.join(save_dir, filename)
                with open(full_path, "wb") as f:
                    f.write(r.content)
                saved_paths.append(full_path)
                
            if send_msg:
                send_telegram_message(chat_id, f"✅ Đã tải xong! Đã lưu vào thư mục của {len(profiles)} tài khoản đang chọn.\nAnh có thể tiếp tục luồng công việc.")
                
        except Exception as e:
            logger.error(f"Error downloading media: {e}")
            if send_msg:
                send_telegram_message(chat_id, f"❌ Lỗi tải file: {e}")
                
    threading.Thread(target=download_task).start()


