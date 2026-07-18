from celery.result import AsyncResult
from fastapi import FastAPI, Request, Header, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import os
import redis
import psycopg2
import shutil
import time
from workflow_engine import handle_workflow_callback, ACTIVE_WORKFLOWS

# Thiáº¿t láº­p logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Webhook Receiver", version="1.0.0")

# Cáº¥u hÃ¬nh CORS Ä‘á»ƒ UI Next.js cÃ³ thá»ƒ gá»i API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phÃ©p táº¥t cáº£ cÃ¡c domain (Hoáº·c thay báº±ng domain cá»§a Cloudflare Pages sau nÃ y)
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles

# Äáº£m báº£o cÃ¡c thÆ° má»¥c static tá»“n táº¡i trÆ°á»›c khi mount
os.makedirs("/app/scripts/content", exist_ok=True)
os.makedirs("/app/scripts/images", exist_ok=True)

app.mount("/static/content", StaticFiles(directory="/app/scripts/content"), name="content")
app.mount("/static/images", StaticFiles(directory="/app/scripts/images"), name="images")

# Redis configuration for Idempotency
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# PostgreSQL configuration
DB_URL = os.getenv("POSTGRES_URL", "postgresql://user:password@localhost:5432/automation_db")
url_sync = DB_URL.replace("postgresql://", "postgres://")

def get_db_connection():
    return psycopg2.connect(url_sync)

@app.get("/")
def read_root():
    return {"message": "Webhook receiver is running"}

@app.get("/api/dashboard/metrics")
def get_dashboard_metrics():
    """
    API cung cáº¥p dá»¯ liá»‡u cho Dashboard UI.
    Truy váº¥n ads_metrics & orders tá»« Local Postgres vÃ  inventory tá»« Supabase Postgres.
    """
    local_conn = None
    supabase_conn = None
    try:
        # 1. Káº¿t ná»‘i DB cá»¥c bá»™ Ä‘á»ƒ láº¥y Ads Performance & Orders
        local_conn = get_db_connection()
        local_cursor = local_conn.cursor()
        
        # Láº¥y tá»•ng doanh thu vÃ  tá»•ng Ä‘Æ¡n tá»« local
        local_cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM orders")
        orders_count, total_revenue = local_cursor.fetchone()
        
        # Láº¥y dá»¯ liá»‡u ROAS tá»« local
        local_cursor.execute('''
            SELECT 
                a.campaign_id,
                a.platform,
                SUM(a.spend) as total_spend,
                COALESCE(SUM(o.total_amount), 0) as total_revenue,
                CASE WHEN SUM(a.spend) > 0 THEN ROUND(COALESCE(SUM(o.total_amount), 0) / SUM(a.spend), 2) ELSE 0 END as ROAS
            FROM ads_metrics a
            LEFT JOIN orders o ON a.campaign_id = o.campaign_id
            GROUP BY a.campaign_id, a.platform
        ''')
        ads_performance = [
            {
                "campaign": row[0], 
                "platform": row[1], 
                "spend": float(row[2]) if row[2] is not None else 0.0, 
                "revenue": float(row[3]) if row[3] is not None else 0.0, 
                "roas": float(row[4]) if row[4] is not None else 0.0
            }
            for row in local_cursor.fetchall()
        ]
        local_cursor.close()
        
        # 2. Káº¿t ná»‘i Supabase DB Ä‘á»ƒ láº¥y Tá»“n Kho & Xuáº¥t Nháº­p Kho
        supabase_url = os.getenv("SUPABASE_DB_URL")
        if supabase_url:
            if "?" in supabase_url:
                supabase_url = supabase_url.split("?")[0]
            supabase_conn = psycopg2.connect(supabase_url)
            logger.info("Connected to Supabase for inventory metrics")
        else:
            supabase_conn = get_db_connection()
            logger.info("Fallback to Local Postgres for inventory metrics")
            
        supabase_cursor = supabase_conn.cursor()
        
        # Láº¥y dá»¯ liá»‡u tá»“n kho
        supabase_cursor.execute("""
            SELECT 
                i.item_name, 
                i.current_stock, 
                COALESCE(t.unit_price, 0) as last_price
            FROM inventory_items i
            LEFT JOIN (
                SELECT DISTINCT ON (item_id) item_id, unit_price
                FROM inventory_transactions
                ORDER BY item_id, created_at DESC
            ) t ON i.id = t.item_id
            WHERE i.is_active=true
            ORDER BY i.current_stock DESC
        """)
        inventory = [
            {
                "name": row[0], 
                "stock": float(row[1]) if row[1] is not None else 0.0, 
                "price": float(row[2]) if row[2] is not None else 0.0
            } 
            for row in supabase_cursor.fetchall()
        ]
        
        # Láº¥y 10 giao dá»‹ch xuáº¥t nháº­p kho gáº§n nháº¥t
        supabase_cursor.execute("""
            SELECT 
                t.created_at,
                i.item_name,
                t.type,
                t.quantity,
                t.unit_price,
                t.total_amount
            FROM inventory_transactions t
            JOIN inventory_items i ON t.item_id = i.id
            ORDER BY t.created_at DESC
            LIMIT 10
        """)
        recent_transactions = [
            {
                "created_at": row[0].isoformat() if row[0] is not None else "",
                "item_name": row[1],
                "type": row[2],
                "quantity": float(row[3]) if row[3] is not None else 0.0,
                "unit_price": float(row[4]) if row[4] is not None else 0.0,
                "total_amount": float(row[5]) if row[5] is not None else 0.0
            }
            for row in supabase_cursor.fetchall()
        ]
        
        supabase_cursor.close()
        
        return {
            "status": "success",
            "data": {
                "summary": {
                    "total_orders": orders_count,
                    "total_revenue": total_revenue
                },
                "inventory": inventory,
                "recent_transactions": recent_transactions,
                "ads_performance": ads_performance
            }
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if local_conn:
            local_conn.close()
        if supabase_conn:
            supabase_conn.close()


from llm_router import classify_intent, handle_intent
from core_agent import run_agent

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_ADMIN_CHAT_ID"))

def send_local_media_to_telegram(chat_id: int, file_path: str):
    import os
    import requests
    if not os.path.exists(file_path):
        return False
    ext = os.path.splitext(file_path)[1].lower()
    url = ""
    files = {}
    with open(file_path, 'rb') as f:
        if ext in ['.mp4', '.avi', '.mov']:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
            files = {'video': (os.path.basename(file_path), f, 'video/mp4')}
        elif ext in ['.jpg', '.jpeg', '.png', '.gif']:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {'photo': (os.path.basename(file_path), f, 'image/jpeg')}
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
            files = {'document': (os.path.basename(file_path), f)}
            
        data = {'chat_id': chat_id}
        res = requests.post(url, data=data, files=files)
        if res.status_code != 200:
            logger.error(f"Failed to upload media {file_path}: {res.text}")
        return res.status_code == 200


from fastapi import BackgroundTasks

@app.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint nháº­n Webhook vÃ  xá»­ lÃ½ phÃ¢n loáº¡i Intent (Phase 3), RAG (Phase 4).
    CÃ³ tÃ­nh nÄƒng Idempotency (Phase 6) chá»‘ng trÃ¹ng láº·p.
    """
    try:
        data = await request.json()
        logger.info("=== WEBHOOK RECEIVED ===")
        logger.info(f"Payload: {json.dumps(data, indent=2, ensure_ascii=False)}")

        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key:
            cached = redis_client.get(f"idemp:{idempotency_key}")
            if cached:
                logger.info(f"Idempotency hit! Returning cached response for key: {idempotency_key}")
                return json.loads(cached)
            
        message = data.get("message")
        session_id = data.get("session_id", "test_user_1")
        if not message:
            return {"status": "error", "message": "No 'message' field found"}

        classification = await classify_intent(message)
        intent = classification.get("intent", "SPAM")
        
        action_route = handle_intent(intent, message).get("route")
        
        reply_message = ""
        if action_route == "AUTO_REPLY":
            reply_message = handle_intent(intent, message).get("reply")
        else: # CORE_AGENT
            logger.info("Routing to Core Agent...")
            reply_message = run_agent(session_id, message)
        
        response_data = {
            "status": "success", 
            "intent": intent,
            "reply": reply_message
        }
        
        # Náº¿u cÃ³ key, lÆ°u response vÃ o Redis vá»›i TTL 24h
        if idempotency_key:
            redis_client.setex(f"idemp:{idempotency_key}", 86400, json.dumps(response_data))
            
        return response_data
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {"status": "error", "message": "Failed to parse or process webhook"}

@app.post("/webhook/logistics")
async def receive_logistics_webhook(request: Request):
    """
    Webhook giáº£ láº­p tá»« Ä‘Æ¡n vá»‹ váº­n chuyá»ƒn (Phase 5 + Phase 8: BÃ¡n tá»± Ä‘á»™ng Geta-Finance).
    """
    try:
        data = await request.json()
        order_id = data.get("order_id")
        status = data.get("status")
        
        if status == "SHIPPED":
            # 1. Update order status
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orders SET status = %s, updated_at = NOW() WHERE order_id = %s",
                (status, order_id)
            )
            
            # Giáº£ Ä‘á»‹nh item_code = 'PROD-1', quantity = 1 (Trong thá»±c táº¿ sáº½ join vá»›i order_items)
            item_code = 'PROD-1'
            qty = 1
            
            conn.commit()
            cursor.close()
            conn.close()
            logger.info(f"Logistics Webhook received for order {order_id}: {status}")
            
            # 2. Gá»­i yÃªu cáº§u duyá»‡t xuáº¥t kho qua Telegram
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                import requests
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "âœ… Duyá»‡t Xuáº¥t Kho", "callback_data": f"approve_out_{item_code}_{qty}"},
                            {"text": "âŒ Tá»« Chá»‘i", "callback_data": f"reject_out_{item_code}"}
                        ]
                    ]
                }
                msg = f"ðŸ“¦ *YÃªu cáº§u xuáº¥t kho*\nÄÆ¡n hÃ ng: #{order_id}\nSáº£n pháº©m: {item_code}\nSá»‘ lÆ°á»£ng: {qty}\nTráº¡ng thÃ¡i: SHIPPED"
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": msg,
                        "parse_mode": "Markdown",
                        "reply_markup": json.dumps(keyboard)
                    }
                )
                logger.info("Sent approval request to Telegram")
                
            return {"status": "success", "message": "Approval request sent to Telegram"}
        return {"status": "ignored"}
    except Exception as e:
        logger.error(f"Error processing logistics webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook nháº­n callback tá»« Telegram khi Quáº£n lÃ½ báº¥m nÃºt Duyá»‡t/Tá»« chá»‘i (Phase 8).
    """
    try:
        data = await request.json()
        logger.info(f"=== TELEGRAM WEBHOOK RECEIVED ===")
        logger.info(f"Payload: {json.dumps(data, indent=2, ensure_ascii=False)}")
        if "callback_query" in data:
            callback_query = data["callback_query"]
            query_id = callback_query["id"]
            callback_data = callback_query["data"]
            chat_id = callback_query["message"]["chat"]["id"]
            message_id = callback_query["message"]["message_id"]
            
            import requests
            
            if callback_data.startswith("wf_"):
                handle_workflow_callback(chat_id, message_id, callback_data)
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": query_id}
                )
                return {"status": "ok"}
            
            if callback_data.startswith("approve_out_"):
                parts = callback_data.split("_")
                item_code = parts[2]
                qty = float(parts[3])
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # 1. Trá»« kho inventory_items
                cursor.execute(
                    "UPDATE inventory_items SET current_stock = current_stock - %s, updated_at = NOW() WHERE item_code = %s RETURNING id, current_stock",
                    (qty, item_code)
                )
                res = cursor.fetchone()
                
                if res:
                    item_id = res[0]
                    new_stock = res[1]
                    # 2. Ghi log inventory_transactions
                    import uuid
                    cursor.execute(
                        "INSERT INTO inventory_transactions (id, item_id, type, quantity, created_by) VALUES (%s, %s, 'OUT', %s, 'Telegram Approver')",
                        (str(uuid.uuid4()), item_id, qty)
                    )
                    conn.commit()
                    
                    # Update message on Telegram
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText",
                        json={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": f"âœ… ÄÃ£ duyá»‡t xuáº¥t kho cho sáº£n pháº©m {item_code} (SL: {qty})\nðŸ“¦ *Tá»“n kho cÃ²n láº¡i:* {new_stock}",
                            "parse_mode": "Markdown"
                        }
                    )
                else:
                    conn.rollback()
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={"chat_id": chat_id, "text": f"Lá»—i: KhÃ´ng tÃ¬m tháº¥y sáº£n pháº©m {item_code} trong kho!"}
                    )
                    
                cursor.close()
                conn.close()
                
            elif callback_data.startswith("reject_out_"):
                parts = callback_data.split("_")
                item_code = parts[2]
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText",
                    json={
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "text": f"âŒ ÄÃ£ tá»« chá»‘i xuáº¥t kho cho sáº£n pháº©m {item_code}.",
                        "parse_mode": "Markdown"
                    }
                )
            elif callback_data.startswith("site_sel_"):
                parts = callback_data.split("_")
                article_id = int(parts[2])
                idx = int(parts[3])
                from workflow_engine import handle_site_selection
                handle_site_selection(article_id, idx, message_id)
            elif callback_data.startswith("site_confirm_"):
                parts = callback_data.split("_")
                article_id = int(parts[2])
                from workflow_engine import handle_site_confirm
                handle_site_confirm(article_id, message_id)
            elif callback_data.startswith("cat_sel_"):
                parts = callback_data.split("_", 3) # cat_sel_<article_id>_<category_name>
                article_id = int(parts[2])
                category_name = parts[3]
                from workflow_engine import handle_category_confirm
                handle_category_confirm(article_id, message_id, category_name)
            
            # Answer callback query to stop loading animation
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                json={"callback_query_id": query_id}
            )
            
            return {"status": "ok"}
            
        elif "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            
            # 1. Media Parsing (Photo, Video, Document)
            if "photo" in message or "video" in message or "document" in message:
                from workflow_engine import handle_telegram_media
                handle_telegram_media(message)
                return {"status": "ok"}
                
            # 2. Text Parsing
            if "text" not in message:
                return {"status": "ok"}
                
            text = message["text"]
            
            # Check Decision Tree State Machine First
            from workflow_engine import process_text_input
            if process_text_input(chat_id, text):
                return {"status": "ok"}
            
            # ÄÆ°a tÃ¡c vá»¥ xá»­ lÃ½ LLM vÃ  sinh Video náº·ng ná» vÃ o Background Task 
            # Ä‘á»ƒ khÃ´ng bá»‹ Telegram Timeout (gÃ¢y lá»—i ConnectionResetError vÃ  láº·p webhook)
            background_tasks.add_task(process_telegram_message_bg, chat_id, text)
            return {"status": "ok"}
            
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing telegram webhook: {str(e)}")
        return {"status": "error"}

async def process_telegram_message_bg(chat_id: int, text: str):
    """Background task xá»­ lÃ½ tin nháº¯n Telegram qua LLM vÃ  cÃ¡c Tool."""
    try:
        classification = await classify_intent(text)
        intent = classification.get("intent", "SPAM")
        action_route = handle_intent(intent, text).get("route")
        
        reply_message = ""
        if action_route == "AUTO_REPLY":
            reply_message = handle_intent(intent, text).get("reply")
        else: # CORE_AGENT
            logger.info("Routing to Core Agent from Telegram...")
            import httpx
            import asyncio
            
            async def keep_typing(cid: int, stop_evt: asyncio.Event):
                async with httpx.AsyncClient() as client:
                    while not stop_evt.is_set():
                        try:
                            await client.post(
                                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction",
                                json={"chat_id": cid, "action": "typing"},
                                timeout=5.0
                            )
                        except:
                            pass
                        try:
                            await asyncio.wait_for(stop_evt.wait(), timeout=4.0)
                        except asyncio.TimeoutError:
                            continue

            stop_event = asyncio.Event()
            typing_task = asyncio.create_task(keep_typing(chat_id, stop_event))
            
            try:
                reply_message = await asyncio.to_thread(run_agent, str(chat_id), text)
            finally:
                stop_event.set()
            
        import requests
        import re
        import json
        
        # Intercept workflow commands
        if "__COMMAND__:start_interactive_workflow" in reply_message:
            from workflow_engine import start_interactive_workflow
            start_interactive_workflow(chat_id)
            return
        elif "__COMMAND__:start_website_workflow" in reply_message:
            from workflow_engine import start_website_workflow
            start_website_workflow(chat_id)
            return
        elif "__COMMAND__:start_blog_workflow_with_keyword:" in reply_message:
            keyword = reply_message.split("__COMMAND__:start_blog_workflow_with_keyword:")[1].strip()
            from workflow_engine import start_blog_workflow_with_keyword
            start_blog_workflow_with_keyword(chat_id, keyword)
            return
        elif "__COMMAND__" in reply_message:
            match = re.search(r'__COMMAND__(.*?)__COMMAND__', reply_message, re.DOTALL)
            if match:
                cmd_str = match.group(1)
                try:
                    cmd = json.loads(cmd_str)
                    if cmd.get("action") == "START_TIKTOK_WORKFLOW":
                        from workflow_engine import start_tiktok_workflow
                        start_tiktok_workflow(chat_id, cmd.get("topic"), cmd.get("duration"))
                        return
                    elif cmd.get("action") == "START_SITE_SELECTION":
                        from workflow_engine import start_site_selection_workflow
                        start_site_selection_workflow(chat_id, cmd.get("article_id"), cmd.get("sites", []))
                        return
                except Exception as e:
                    logger.error(f"Error parsing workflow command: {e}")
                    
        # Parse for any local file paths to upload
        import os
        file_paths = re.findall(r'([a-zA-Z]:\\[\w\-\.\\]+\.\w+|/[\w\-\.\/]+\.\w+)', reply_message)
        for file_path in file_paths:
            if os.path.exists(file_path):
                send_local_media_to_telegram(chat_id, file_path)
                    
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": reply_message,
                "parse_mode": "Markdown"
            }
        )
    except Exception as e:
        logger.error(f"Error in background telegram task: {str(e)}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing telegram webhook: {str(e)}")
        return {"status": "error"}

from fastapi import Response
from celery_app import celery_app

GETA_FACEBOOK_WEBHOOK_SECRET = "geta_automation_secret_2026"

@app.get("/api/facebook/webhook")
async def verify_facebook_webhook(request: Request):
    """XÃ¡c minh Webhook vá»›i Meta/Facebook."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == GETA_FACEBOOK_WEBHOOK_SECRET:
            logger.info("WEBHOOK_VERIFIED")
            return Response(content=challenge, status_code=200)
        else:
            raise HTTPException(status_code=403, detail="Forbidden")
    raise HTTPException(status_code=400, detail="Bad Request")

@app.post("/api/facebook/webhook")
async def handle_facebook_webhook(request: Request):
    """Xá»­ lÃ½ sá»± kiá»‡n tá»« Facebook (BÃ¬nh luáº­n)."""
    try:
        data = await request.json()
        logger.info(f"=== FACEBOOK WEBHOOK RECEIVED ===")
        logger.info(f"Payload: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        if data.get("object") == "page":
            for entry in data.get("entry", []):
                page_id = entry.get("id")
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    # Xá»­ lÃ½ sá»± kiá»‡n comment
                    if change.get("field") == "feed" and value.get("item") == "comment":
                        verb = value.get("verb")
                        if verb == "add":
                            comment_id = value.get("comment_id")
                            comment_text = value.get("message")
                            from_id = value.get("from", {}).get("id")
                            
                            # Äá»«ng tá»± reply chÃ­nh page cá»§a mÃ¬nh
                            if from_id == page_id:
                                continue
                                
                            logger.info(f"New comment from {from_id} on page {page_id}: {comment_text}")
                            
                            # Äáº©y vÃ o Celery queue xá»­ lÃ½ ngáº§m (countdown 60s Ä‘á»ƒ giáº£ láº­p ngÆ°á»i tháº­t)
                            celery_app.send_task(
                                "tasks.reply_facebook_comment_task",
                                args=[comment_id, comment_text, page_id],
                                countdown=60
                            )
        return Response(content="EVENT_RECEIVED", status_code=200)
    except Exception as e:
        logger.error(f"Error handling facebook webhook: {e}")
        return Response(content="ERROR", status_code=500)

from pydantic import BaseModel
from typing import List

class SaveGroupsRequest(BaseModel):
    groups: str

class SearchJoinRequest(BaseModel):
    keyword: str = None
    urls: List[str] = None

@app.get("/api/facebook/active-profile")
def get_active_profile():
    """Tá»± Ä‘á»™ng phÃ¡t hiá»‡n tÃªn tÃ i khoáº£n Facebook Ä‘ang Ä‘Äƒng nháº­p trong Chrome."""
    from playwright.sync_api import sync_playwright
    import requests
    import socket
    
    cdp_host = os.getenv("CDP_HOST", "127.0.0.1:9222")
    
    # PhÃ¢n giáº£i host.docker.internal sang IP sá»‘ Ä‘á»ƒ thá»a mÃ£n báº£o máº­t cá»§a Chrome (yÃªu cáº§u IP hoáº·c localhost)
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
    
    # Láº¥y WebSocket debugger URL tá»« Chrome
    try:
        res = requests.get(f"http://{resolved_host}/json/version", timeout=2)
        if res.status_code == 200:
            ws_url = res.json().get("webSocketDebuggerUrl")
    except Exception as e:
        pass

    if not ws_url:
        return {"status": "error", "message": f"KhÃ´ng thá»ƒ káº¿t ná»‘i tá»›i Chrome gá»¡ lá»—i á»Ÿ {cdp_host} (IP: {host_part}). HÃ£y cháº¯c cháº¯n báº¡n Ä‘Ã£ má»Ÿ Chrome vá»›i port 9222."}

    # 2. Sá»­ dá»¥ng Playwright truy cáº­p facebook.com/me Ä‘á»ƒ láº¥y tÃªn tÃ i khoáº£n
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(ws_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page() # LuÃ´n má»Ÿ tab má»›i Ä‘á»ƒ trÃ¡nh Ä‘Ã¨ lÃªn tab lÃ m viá»‡c cá»§a ngÆ°á»i dÃ¹ng
            
            try:
                # 1. Thá»­ láº¥y siÃªu tá»‘c báº±ng biáº¿n cá»¥c bá»™ cá»§a Facebook React (Nhanh vÃ  chÃ­nh xÃ¡c 100%)
                page.goto("https://www.facebook.com/", timeout=15000)
                page.wait_for_timeout(1500)
                try:
                    js_name = page.evaluate('() => require("CurrentUserInitialData").NAME')
                    if js_name:
                        return {"status": "success", "profile": js_name}
                except:
                    pass

                # 2. Äiá»u hÆ°á»›ng tá»›i facebook.com/me (sáº½ tá»± redirect vá» trang cÃ¡ nhÃ¢n cá»§a nick hiá»‡n táº¡i)
                page.goto("https://www.facebook.com/me", timeout=15000)
                try:
                    page.wait_for_function("document.title !== 'Facebook' && document.title !== ''", timeout=10000)
                except:
                    page.wait_for_timeout(2000)
                
                # Danh sÃ¡ch cÃ¡c tá»« khÃ³a há»‡ thá»‘ng Ä‘á»ƒ bá» qua (trÃ¡nh láº¥y nháº§m tÃªn trang há»‡ thá»‘ng khi Ä‘ang load)
                blacklist = ["notifications", "thÃ´ng bÃ¡o", "messages", "tin nháº¯n", "home", "trang chá»§", "facebook", "login", "Ä‘Äƒng nháº­p", "checkpoint", "search", "tÃ¬m kiáº¿m"]
                name = ""
                
                # Thá»­ quÃ©t 3 láº§n, má»—i láº§n cÃ¡ch nhau 2s náº¿u bá»‹ nháº­n diá»‡n nháº§m tá»« khÃ³a há»‡ thá»‘ng
                for attempt in range(3):
                    curr_url = page.url
                    if "login" in curr_url or "checkpoint" in curr_url:
                        return {"status": "success", "profile": "ChÆ°a Ä‘Äƒng nháº­p Facebook"}
                    
                    # 1. Thá»­ láº¥y tá»« cÃ¡c Selector phá»• biáº¿n trÃªn trang cÃ¡ nhÃ¢n FB (bao gá»“m class cá»¥ thá»ƒ tá»« screenshot cá»§a user)
                    selectors = [
                        "h1",
                        "h1[dir='auto']",
                        "div[role='main'] h1",
                        "div.x1i10hfl.x1qjc9v5.xjqbq8w.xjqpnuy.xc5r6h4.xqeqjp1.x1phubyo.x13fuv20.x18b5jzi",
                        "div.x1i10hfl.x1qjc9v5.xjbqb8w.xjqpnuy.xc5r6h4.xqeqjp1.x1phubyo.x13fuv20.x18b5jzi.x1q0q8m5.x1t7ytsu.x972fbf.x10w94by.x1qhh985.x14e42zd.x9f619.x1ypdohk.xdl72j9.x2lah0s.x3ct3a4.xdj266r.x14z9mp.xat24cr.x1lziwak.x2lwn1j.xeuugli.xexx8yu.xyri2b.x18d9i69.x1c1uobl.x1n2onr6.x16tdsg8.x1hl2dhg.xggy1nq.x1ja2u2z.x1t137rt.x1fmog5m.xu25z0z.x140muxe.xo1y3bh.x3nfvp2.x1q0g3np.x87ps6o.x1lku1pv.x1a2a7pz",
                        "span.x1lliihq.x6ikm8r.x10wlt62.x1n2onr6.xlyipyv.xuxw1ft.x1j85h84"
                    ]
                    for sel in selectors:
                        try:
                            el = page.locator(sel).first
                            if el.count() > 0:
                                txt = el.inner_text().strip()
                                if txt and not any(w in txt.lower() for w in blacklist):
                                    name = txt
                                    break
                        except:
                            continue
                    
                    if name:
                        break
                    
                    # 2. Thá»­ láº¥y tá»« tiÃªu Ä‘á» tÃ i liá»‡u (document title)
                    title = page.title()
                    if title:
                        import re
                        clean_title = title.replace("| Facebook", "").replace("Facebook", "").strip()
                        clean_title = re.sub(r'^\(\d+\)\s*', '', clean_title) # XÃ³a sá»‘ thÃ´ng bÃ¡o dáº¡ng (1)
                        if clean_title and not any(w in clean_title.lower() for w in blacklist):
                            name = clean_title
                            break
                    
                    # Náº¿u rÆ¡i vÃ o tá»« khÃ³a há»‡ thá»‘ng, Ä‘á»£i 2 giÃ¢y Ä‘á»ƒ trang chuyá»ƒn hÆ°á»›ng hoÃ n táº¥t rá»“i thá»­ láº¡i
                    page.wait_for_timeout(2000)
                
                if name:
                    return {"status": "success", "profile": name}
                
                # 3. Fallback: Láº¥y username hoáº·c ID tá»« URL
                curr_url = page.url
                import urllib.parse
                parsed = urllib.parse.urlparse(curr_url)
                if 'profile.php' in parsed.path:
                    qs = urllib.parse.parse_qs(parsed.query)
                    if 'id' in qs:
                        return {"status": "success", "profile": f"ID: {qs['id'][0]}"}
                elif parsed.path.strip('/') and parsed.path.strip('/') != 'me':
                    username = parsed.path.strip('/').split('/')[0]
                    if username and not any(w in username.lower() for w in blacklist):
                        return {"status": "success", "profile": f"@{username}"}

                return {"status": "success", "profile": "KhÃ´ng xÃ¡c Ä‘á»‹nh (ÄÃ£ Ä‘Äƒng nháº­p)"}
            finally:
                try:
                    page.close() # ÄÃ³ng tab má»›i vá»«a má»Ÿ
                except:
                    pass
    except Exception as e:
        logger.error(f"Error detecting active profile: {e}")
        return {"status": "error", "message": f"Lá»—i khi quÃ©t thÃ´ng tin nick: {str(e)}"}

@app.get("/api/facebook/groups")
def get_facebook_groups():
    """Äá»c danh sÃ¡ch link group tá»« target_groups.txt."""
    file_path = "/app/scripts/target_groups.txt"
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"status": "success", "groups": content}
        return {"status": "success", "groups": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i Ä‘á»c danh sÃ¡ch nhÃ³m: {str(e)}")

@app.post("/api/facebook/groups")
def save_facebook_groups(payload: SaveGroupsRequest):
    """LÆ°u danh sÃ¡ch link group vÃ o target_groups.txt."""
    file_path = "/app/scripts/target_groups.txt"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(payload.groups)
        return {"status": "success", "message": "ÄÃ£ lÆ°u danh sÃ¡ch nhÃ³m thÃ nh cÃ´ng!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i ghi file: {str(e)}")

@app.post("/api/facebook/run-search-join")
def trigger_group_search_join(payload: SearchJoinRequest):
    """KÃ­ch hoáº¡t Celery task cháº¡y script tÃ¬m kiáº¿m vÃ  tham gia nhÃ³m."""
    try:
        celery_app.send_task("tasks.run_group_search_join_task", kwargs={"keyword": payload.keyword, "urls": payload.urls})
        msg = f"ÄÃ£ kÃ­ch hoáº¡t tá»± Ä‘á»™ng tham gia {len(payload.urls)} nhÃ³m Ä‘Æ°á»£c chá»n!" if payload.urls else f"ÄÃ£ kÃ­ch hoáº¡t tÃ¬m kiáº¿m vÃ  tham gia nhÃ³m vá»›i tá»« khÃ³a '{payload.keyword}'!"
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t task: {str(e)}")

@app.post("/api/facebook/run-group-poster")
def trigger_group_poster():
    """KÃ­ch hoáº¡t Celery task cháº¡y script tá»± Ä‘á»™ng Ä‘Äƒng bÃ i nhÃ³m."""
    try:
        celery_app.send_task("tasks.run_group_auto_poster_task")
        return {"status": "success", "message": "ÄÃ£ kÃ­ch hoáº¡t tá»± Ä‘á»™ng Ä‘Äƒng tuyá»ƒn dá»¥ng vÃ o cÃ¡c nhÃ³m!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t task: {str(e)}")

@app.post("/api/facebook/run-page-poster")
def trigger_page_poster():
    """KÃ­ch hoáº¡t Celery task tá»± Ä‘á»™ng Ä‘Äƒng bÃ i lÃªn 3 Fanpage."""
    try:
        celery_app.send_task("tasks.auto_post_facebook")
        return {"status": "success", "message": "ÄÃ£ kÃ­ch hoáº¡t tá»± Ä‘á»™ng Ä‘Äƒng bÃ i lÃªn 3 Fanpage!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t task: {str(e)}")

@app.post("/api/facebook/stop-tasks")
def stop_tasks():
    """Ngá»«ng táº¥t cáº£ cÃ¡c tÃ¡c vá»¥ tá»± Ä‘á»™ng hÃ³a Ä‘ang cháº¡y ngáº§m."""
    try:
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        revoked_count = 0
        
        target_tasks = [
            "tasks.run_group_search_join_task",
            "tasks.run_group_auto_poster_task",
            "tasks.run_custom_campaign_task",
            "tasks.run_group_crawler_task",
            "tasks.auto_post_facebook"
        ]
        
        if active_tasks:
            for worker, tasks_list in active_tasks.items():
                for t in tasks_list:
                    if t.get("name") in target_tasks:
                        celery_app.control.revoke(t.get("id"), terminate=True)
                        revoked_count += 1
                        
        log_file_path = "/app/scripts/joined_log.txt"
        if os.path.exists(log_file_path):
            with open(log_file_path, "a", encoding="utf-8") as lf:
                import time
                lf.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] ðŸ›‘ ÄÃƒ Gá»¬I YÃŠU Cáº¦U NGá»ªNG TÃC Vá»¤ KHáº¨N Cáº¤P. ÄÃ£ thu há»“i {revoked_count} tÃ¡c vá»¥.\n")
                
        return {"status": "success", "message": f"ÄÃ£ gá»­i yÃªu cáº§u dá»«ng {revoked_count} tÃ¡c vá»¥ thÃ nh cÃ´ng!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i khi dá»«ng tÃ¡c vá»¥: {str(e)}")

@app.get("/api/facebook/logs")
def get_facebook_logs():
    """Äá»c 100 dÃ²ng log má»›i nháº¥t tá»« joined_log.txt."""
    file_path = "/app/scripts/joined_log.txt"
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # Láº¥y 100 dÃ²ng cuá»‘i cÃ¹ng
            last_lines = lines[-100:]
            return {"status": "success", "logs": "".join(last_lines)}
        return {"status": "success", "logs": "ChÆ°a cÃ³ dá»¯ liá»‡u nháº­t kÃ½ (log)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i Ä‘á»c log: {str(e)}")

class CrawlRequest(BaseModel):
    keyword: str

class ImportGroupsRequest(BaseModel):
    urls: List[str]

@app.post("/api/facebook/run-crawl")
def trigger_group_crawler(payload: CrawlRequest):
    """KÃ­ch hoáº¡t Celery task cháº¡y script cÃ o nhÃ³m."""
    try:
        celery_app.send_task("tasks.run_group_crawler_task", args=[payload.keyword])
        return {"status": "success", "message": f"ÄÃ£ kÃ­ch hoáº¡t cÃ o nhÃ³m vá»›i tá»« khÃ³a '{payload.keyword}'!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t task: {str(e)}")

@app.get("/api/facebook/crawled-groups")
def get_crawled_groups(keyword: str = None):
    """Äá»c dá»¯ liá»‡u káº¿t quáº£ cÃ o nhÃ³m tá»« crawled_groups.json."""
    file_path = "/app/scripts/crawled_groups.json"
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {"status": "success", "data": data, "keywords": []}
            elif isinstance(data, dict):
                keywords = list(data.keys())
                if keyword:
                    return {"status": "success", "data": data.get(keyword, []), "keywords": keywords}
                if keywords:
                    return {"status": "success", "data": data[keywords[0]], "keywords": keywords}
                return {"status": "success", "data": [], "keywords": []}
        return {"status": "success", "data": [], "keywords": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i Ä‘á»c káº¿t quáº£ cÃ o: {str(e)}")

@app.post("/api/facebook/import-groups")
def import_groups(payload: ImportGroupsRequest):
    """Ná»‘i (import) danh sÃ¡ch link nhÃ³m Ä‘Æ°á»£c chá»n vÃ o target_groups.txt."""
    file_path = "/app/scripts/target_groups.txt"
    try:
        existing_groups = set()
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                existing_groups = {line.strip() for line in f if line.strip()}
        
        # Ná»‘i cÃ¡c nhÃ³m má»›i chÆ°a tá»“n táº¡i
        new_urls = [url for url in payload.urls if url.strip() and url.strip() not in existing_groups]
        
        if new_urls:
            with open(file_path, "a", encoding="utf-8") as f:
                # Náº¿u file khÃ´ng káº¿t thÃºc báº±ng newline, hÃ£y thÃªm vÃ o
                f.write("\n" + "\n".join(new_urls) + "\n")
            return {"status": "success", "message": f"ÄÃ£ thÃªm {len(new_urls)} nhÃ³m má»›i vÃ o danh sÃ¡ch má»¥c tiÃªu!"}
        return {"status": "success", "message": "Táº¥t cáº£ cÃ¡c nhÃ³m chá»n Ä‘Ã£ tá»“n táº¡i trong danh sÃ¡ch má»¥c tiÃªu."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i nháº­p nhÃ³m: {str(e)}")

class UploadContentRequest(BaseModel):
    content: str

class CampaignRequest(BaseModel):
    profile_type: str
    page_name: str
    content_source: str = "library"      # "library" | "manual" | "ai"
    content_file: str = ""
    content_text: str = ""
    content_keyword: str = ""
    content_vibe: str = "professional"
    image_source: str = "library"        # "none" | "library" | "upload" | "ai"
    image_file: str = ""
    image_prompt: str = ""
    groups: List[str]


class EnhancePromptRequest(BaseModel):
    prompt: str
    type: str

class GenerateContentOnlyRequest(BaseModel):
    keyword: str
    vibe: str = "professional"

class GenerateImageOnlyRequest(BaseModel):
    keyword: str
    aspect_ratio: str = "1:1"

class GenerateContentRequest(BaseModel):
    keyword: str
    vibe: str = "professional"
    aspect_ratio: str = "1:1"

@app.get("/api/facebook/library")
def get_library():
    """Láº¥y danh sÃ¡ch cÃ¡c bÃ i viáº¿t & áº£nh Ä‘Ã£ lÆ°u trong thÆ° viá»‡n."""
    content_dir = "/app/scripts/content"
    images_dir = "/app/scripts/images"
    try:
        contents = []
        images = []
        if os.path.exists(content_dir):
            for file in os.listdir(content_dir):
                if file.endswith(".txt"):
                    # Äá»c thá»­ má»™t pháº§n ná»™i dung preview
                    file_path = os.path.join(content_dir, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read(100) # Láº¥y 100 kÃ½ tá»± Ä‘áº§u
                    contents.append({"filename": file, "preview": text})
                    
        if os.path.exists(images_dir):
            for file in os.listdir(images_dir):
                if file.endswith((".jpg", ".jpeg", ".png")):
                    images.append({"filename": file})
                    
        # Sáº¯p xáº¿p file má»›i nháº¥t lÃªn Ä‘áº§u (dá»±a vÃ o timestamp á»Ÿ tÃªn file)
        contents.sort(key=lambda x: x["filename"], reverse=True)
        images.sort(key=lambda x: x["filename"], reverse=True)
        
        return {"status": "success", "contents": contents, "images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i Ä‘á»c thÆ° viá»‡n: {str(e)}")

@app.delete("/api/facebook/library/content/{filename}")
def delete_library_content(filename: str):
    """XÃ³a má»™t bÃ i viáº¿t khá»i thÆ° viá»‡n."""
    file_path = os.path.join("/app/scripts/content", filename)
    try:
        if ".." in filename or filename.startswith("/"):
            raise HTTPException(status_code=400, detail="TÃªn file khÃ´ng há»£p lá»‡.")
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "success", "message": f"ÄÃ£ xÃ³a bÃ i viáº¿t '{filename}'."}
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y bÃ i viáº¿t.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i khi xÃ³a bÃ i viáº¿t: {str(e)}")

@app.delete("/api/facebook/library/image/{filename}")
def delete_library_image(filename: str):
    """XÃ³a má»™t áº£nh khá»i thÆ° viá»‡n."""
    file_path = os.path.join("/app/scripts/images", filename)
    try:
        if ".." in filename or filename.startswith("/"):
            raise HTTPException(status_code=400, detail="TÃªn file khÃ´ng há»£p lá»‡.")
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "success", "message": f"ÄÃ£ xÃ³a áº£nh '{filename}'."}
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y áº£nh.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i khi xÃ³a áº£nh: {str(e)}")



@app.get("/api/facebook/task-status/{task_id}")
def get_task_status(task_id: str):
    """Láº¥y tráº¡ng thÃ¡i cá»§a Celery task."""
    try:
        task = AsyncResult(task_id, app=celery_app)
        return {
            "task_id": task_id,
            "status": task.state,
            "result": str(task.result) if task.result else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i khi láº¥y tráº¡ng thÃ¡i: {str(e)}")

@app.get("/api/facebook/active-tasks")
def get_active_tasks():
    """Láº¥y danh sÃ¡ch cÃ¡c tÃ¡c vá»¥ Celery Ä‘ang cháº¡y ngáº§m trÃªn worker."""
    try:
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        
        running_tasks = []
        target_tasks = [
            "tasks.run_group_search_join_task",
            "tasks.run_group_auto_poster_task",
            "tasks.run_custom_campaign_task",
            "tasks.run_group_crawler_task",
            "tasks.auto_post_facebook",
            "tasks.run_market_research_task",
            "tasks.export_to_zalo_crm_task",
            "tasks.generate_content_only_task"
        ]
        
        if active_tasks:
            for worker, tasks_list in active_tasks.items():
                for t in tasks_list:
                    task_name = t.get("name")
                    if task_name in target_tasks:
                        running_tasks.append({
                            "id": t.get("id"),
                            "name": task_name
                        })
        return {"status": "success", "tasks": running_tasks}
    except Exception as e:
        return {"status": "success", "tasks": []}

@app.post("/api/facebook/enhance-prompt")
def enhance_prompt(payload: EnhancePromptRequest):
    """Sá»­ dá»¥ng AI Ä‘á»ƒ lÃ m cho cÃ¢u prompt chi tiáº¿t vÃ  hay hÆ¡n."""
    from tasks import get_gemini_key, invoke_gemini_with_retry
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage
    
    api_key = get_gemini_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="Thiáº¿u GEMINI_API_KEYS")
        
    try:
        
        if payload.type == "content":
            sys_prompt = "Báº¡n lÃ  má»™t chuyÃªn gia Prompt Engineering. HÃ£y nÃ¢ng cáº¥p cÃ¢u mÃ´ táº£ sau thÃ nh má»™t yÃªu cáº§u viáº¿t bÃ i (prompt) cá»±c ká»³ chi tiáº¿t. NÃªu rÃµ bá»‘i cáº£nh, má»¥c tiÃªu, Ä‘á»‘i tÆ°á»£ng Ä‘á»™c giáº£ vÃ  giá»ng Ä‘iá»‡u mong muá»‘n. TUYá»†T Äá»I KHÃ”NG giáº£i thÃ­ch, khÃ´ng xin chÃ o, chá»‰ tráº£ vá» ná»™i dung prompt tiáº¿ng Viá»‡t."
        else:
            sys_prompt = "Báº¡n lÃ  má»™t chuyÃªn gia Prompt Engineering cho AI váº½ áº£nh. HÃ£y nÃ¢ng cáº¥p cÃ¢u mÃ´ táº£ sau thÃ nh má»™t prompt váº½ áº£nh báº±ng TIáº¾NG ANH cá»±c ká»³ chi tiáº¿t. Chá»‰ mÃ´ táº£ nhá»¯ng gÃ¬ hiá»ƒn thá»‹ trong áº£nh (bá»‘i cáº£nh, mÃ u sáº¯c, Ä‘á»‘i tÆ°á»£ng, Ã¡nh sÃ¡ng). QUAN TRá»ŒNG: HÃ£y thÃªm vÃ o cuá»‘i prompt yÃªu cáº§u tuyá»‡t Ä‘á»‘i KHÃ”NG chá»©a báº¥t ká»³ chá»¯ viáº¿t, vÄƒn báº£n hay sá»‘ nÃ o (vÃ­ dá»¥: NO TEXT, NO LETTERS, NO WORDS). TUYá»†T Äá»I KHÃ”NG giáº£i thÃ­ch, khÃ´ng viáº¿t cÃ¡c cÃ¢u nhÆ° 'Here is the prompt'. Chá»‰ tráº£ vá» ná»™i dung prompt tiáº¿ng Anh."
            
        response = invoke_gemini_with_retry([
            HumanMessage(content=f"{sys_prompt}\n\nCÃ¢u mÃ´ táº£ gá»‘c: '{payload.prompt}'")
        ])
        
        return {"status": "success", "enhanced_prompt": response.content.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i khi enhance prompt: {str(e)}")

@app.post("/api/facebook/generate-campaign-content-only")
def generate_campaign_content_only(payload: GenerateContentOnlyRequest):
    """KÃ­ch hoáº¡t Celery task táº¡o ná»™i dung chá»¯ báº±ng AI."""
    try:
        task = celery_app.send_task("tasks.generate_content_only_task", args=[payload.keyword, payload.vibe])
        return {"status": "success", "task_id": task.id, "message": f"ÄÃ£ kÃ­ch hoáº¡t AI sinh bÃ i viáº¿t cho tá»« khÃ³a '{payload.keyword}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t task: {str(e)}")

@app.post("/api/facebook/generate-campaign-image-only")
def generate_campaign_image_only(payload: GenerateImageOnlyRequest):
    """KÃ­ch hoáº¡t Celery task váº½ hÃ¬nh áº£nh báº±ng AI."""
    try:
        task = celery_app.send_task("tasks.generate_image_only_task", args=[payload.keyword, payload.aspect_ratio])
        return {"status": "success", "task_id": task.id, "message": f"ÄÃ£ kÃ­ch hoáº¡t AI váº½ áº£nh cho tá»« khÃ³a '{payload.keyword}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t task: {str(e)}")

@app.post("/api/facebook/generate-campaign-content")
def generate_campaign_content(payload: GenerateContentRequest):
    """KÃ­ch hoáº¡t Celery task táº¡o ná»™i dung vÃ  váº½ hÃ¬nh áº£nh báº±ng AI."""
    try:
        celery_app.send_task("tasks.generate_campaign_content_task", args=[payload.keyword, payload.vibe, payload.aspect_ratio])
        return {"status": "success", "message": f"ÄÃ£ kÃ­ch hoáº¡t AI sinh bÃ i viáº¿t & váº½ áº£nh ({payload.vibe}, tá»‰ lá»‡ {payload.aspect_ratio}) cho tá»« khÃ³a '{payload.keyword}'. Vui lÃ²ng Ä‘á»£i trong giÃ¢y lÃ¡t rá»“i táº£i láº¡i ThÆ° viá»‡n."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t task: {str(e)}")

@app.post("/api/facebook/library/upload-content")
def upload_content_manual(payload: UploadContentRequest):
    """LÆ°u bÃ i viáº¿t nháº­p tay vÃ o thÆ° viá»‡n."""
    timestamp = int(time.time())
    filename = f"manual_input_{timestamp}.txt"
    file_path = os.path.join("/app/scripts/content", filename)
    try:
        os.makedirs("/app/scripts/content", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(payload.content)
        return {"status": "success", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i lÆ°u ná»™i dung: {str(e)}")

@app.post("/api/facebook/library/save-content/{filename}")
def save_library_content(payload: UploadContentRequest, filename: str):
    """Cáº­p nháº­t ná»™i dung cá»§a má»™t bÃ i viáº¿t cá»¥ thá»ƒ trong thÆ° viá»‡n."""
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=400, detail="TÃªn file khÃ´ng há»£p lá»‡.")
    file_path = os.path.join("/app/scripts/content", filename)
    try:
        os.makedirs("/app/scripts/content", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(payload.content)
        return {"status": "success", "message": "ÄÃ£ cáº­p nháº­t bÃ i viáº¿t thÃ nh cÃ´ng!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i lÆ°u ná»™i dung: {str(e)}")

@app.post("/api/facebook/library/upload-image")
async def upload_image_manual(file: UploadFile = File(...)):
    """LÆ°u hÃ¬nh áº£nh táº£i lÃªn vÃ o thÆ° viá»‡n."""
    timestamp = int(time.time())
    ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
    filename = f"manual_upload_{timestamp}{ext}"
    file_path = os.path.join("/app/scripts/images", filename)
    try:
        os.makedirs("/app/scripts/images", exist_ok=True)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"status": "success", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i táº£i áº£nh: {str(e)}")

@app.post("/api/facebook/run-campaign")
def run_campaign(payload: CampaignRequest):
    """KÃ­ch hoáº¡t chiáº¿n dá»‹ch Ä‘Äƒng bÃ i tÃ¹y biáº¿n."""
    try:
        content_file = payload.content_file
        
        # Náº¿u tá»± nháº­p tay content, ghi nháº­n file trÆ°á»›c
        if payload.content_source == "manual":
            timestamp = int(time.time())
            content_file = f"manual_input_{timestamp}.txt"
            file_path = os.path.join("/app/scripts/content", content_file)
            os.makedirs("/app/scripts/content", exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(payload.content_text)
                
        config = {
            "profile_type": payload.profile_type,
            "page_name": payload.page_name,
            "content_source": payload.content_source,
            "content_file": content_file,
            "content_keyword": payload.content_keyword,
            "content_vibe": payload.content_vibe,
            "image_source": payload.image_source,
            "image_file": payload.image_file if payload.image_source != "none" else "",
            "image_prompt": payload.image_prompt,
            "groups": payload.groups
        }
        celery_app.send_task("tasks.run_custom_campaign_task", args=[config])
        return {"status": "success", "message": "ÄÃ£ báº¯t Ä‘áº§u kÃ­ch hoáº¡t chiáº¿n dá»‹ch Ä‘Äƒng bÃ i tÃ¹y chá»n!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t chiáº¿n dá»‹ch: {str(e)}")

class ResearchRequest(BaseModel):
    query: str
    sources: List[str] = ["google", "facebook"]
    limits: dict = {}

@app.post("/api/facebook/run-research")
def trigger_market_research(payload: ResearchRequest):
    """KÃ­ch hoáº¡t Celery task cháº¡y script nghiÃªn cá»©u thá»‹ trÆ°á»ng."""
    try:
        celery_app.send_task("tasks.run_market_research_task", args=[payload.query, payload.sources, payload.limits])
        return {"status": "success", "message": f"ÄÃ£ kÃ­ch hoáº¡t tá»± Ä‘á»™ng nghiÃªn cá»©u thá»‹ trÆ°á»ng cho tá»« khÃ³a '{payload.query}'!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t nghiÃªn cá»©u: {str(e)}")

@app.get("/api/facebook/research-results")
def get_research_results():
    """Äá»c dá»¯ liá»‡u káº¿t quáº£ nghiÃªn cá»©u thá»‹ trÆ°á»ng má»›i nháº¥t."""
    file_path = "/app/scripts/research_results.json"
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"status": "success", "data": data}
        return {"status": "success", "data": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i Ä‘á»c káº¿t quáº£ nghiÃªn cá»©u: {str(e)}")

@app.get("/api/facebook/research-history")
def get_research_history():
    """Danh sÃ¡ch cÃ¡c cuá»™c nghiÃªn cá»©u thá»‹ trÆ°á»ng Ä‘Ã£ lÆ°u."""
    history_dir = "/app/scripts/research_history"
    history_list = []
    try:
        if os.path.exists(history_dir):
            for filename in os.listdir(history_dir):
                if filename.startswith("research_") and filename.endswith(".json"):
                    file_path = os.path.join(history_dir, filename)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        history_list.append({
                            "filename": filename,
                            "query": data.get("query", "KhÃ´ng rÃµ"),
                            "keywords": data.get("keywords", []),
                            "result_count": len(data.get("results", [])),
                            "created_at": os.path.getmtime(file_path)
                        })
                    except Exception:
                        pass
        history_list.sort(key=lambda x: x["created_at"], reverse=True)
        return {"status": "success", "data": history_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/facebook/research-results/{filename}")
def get_specific_research_results(filename: str):
    """Äá»c káº¿t quáº£ nghiÃªn cá»©u cá»¥ thá»ƒ tá»« lá»‹ch sá»­."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="TÃªn tá»‡p khÃ´ng há»£p lá»‡")
    file_path = f"/app/scripts/research_history/{filename}"
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            try:
                main_path = "/app/scripts/research_results.json"
                with open(main_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            except Exception:
                pass
            return {"status": "success", "data": data}
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y tá»‡p káº¿t quáº£")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SaveResearchRequest(BaseModel):
    data: dict

@app.post("/api/facebook/research-results/{filename}")
def save_research_results(filename: str, payload: SaveResearchRequest):
    """LÆ°u vÃ  ghi Ä‘Ã¨ káº¿t quáº£ nghiÃªn cá»©u khi ngÆ°á»i dÃ¹ng chá»‰nh sá»­a."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="TÃªn tá»‡p khÃ´ng há»£p lá»‡")
    file_path = f"/app/scripts/research_history/{filename}"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload.data, f, ensure_ascii=False, indent=4)
        main_path = "/app/scripts/research_results.json"
        with open(main_path, "w", encoding="utf-8") as f:
            json.dump(payload.data, f, ensure_ascii=False, indent=4)
        return {"status": "success", "message": "ÄÃ£ lÆ°u chá»‰nh sá»­a thÃ nh cÃ´ng!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/facebook/research-results/{filename}")
def delete_research_results(filename: str):
    """XÃ³a tá»‡p nghiÃªn cá»©u khá»i lá»‹ch sá»­."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="TÃªn tá»‡p khÃ´ng há»£p lá»‡")
    file_path = f"/app/scripts/research_history/{filename}"
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "success", "message": "ÄÃ£ xÃ³a cuá»™c nghiÃªn cá»©u thÃ nh cÃ´ng!"}
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y tá»‡p Ä‘á»ƒ xÃ³a")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ExportCRMRequest(BaseModel):
    selected_links: List[str] = None

@app.post("/api/facebook/export-to-zalo-crm")
def trigger_export_to_zalo_crm(payload: ExportCRMRequest):
    """KÃ­ch hoáº¡t Celery task Ä‘á»“ng bá»™ dá»¯ liá»‡u qua Zalo CRM."""
    try:
        celery_app.send_task("tasks.export_to_zalo_crm_task", args=[payload.selected_links])
        return {"status": "success", "message": "ÄÃ£ kÃ­ch hoáº¡t Ä‘á»“ng bá»™ cÃ¡c liÃªn há»‡ Ä‘Æ°á»£c chá»n sang Zalo CRM!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lá»—i kÃ­ch hoáº¡t Ä‘á»“ng bá»™: {str(e)}")


@app.get("/api/facebook/posted-links")
def get_posted_links():
    """Láº¥y danh sÃ¡ch cÃ¡c link Ä‘Ã£ Ä‘Äƒng thÃ nh cÃ´ng."""
    import os, json
    posted_links_file = "/app/scripts/posted_links.json"
    if os.path.exists(posted_links_file):
        try:
            with open(posted_links_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

