import os



import json



import psycopg2



import subprocess



import sys



from typing import List, Dict, Any



from langchain_google_genai import ChatGoogleGenerativeAI



from langchain_community.embeddings import OllamaEmbeddings



from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage



from langchain_core.tools import tool



from langchain_openai import ChatOpenAI







DB_URL = os.getenv("POSTGRES_URL", "postgresql://user:password@localhost:5432/automation_db")



url_sync = DB_URL.replace("postgresql://", "postgres://")



OLLAMA_BASE_URL = "http://ollama:11434"







def get_db_connection():



    return psycopg2.connect(url_sync)







def search_products(query: str) -> str:



    """Tìm kiếm sản phẩm trong database thông qua Vector Similarity."""



    embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL)



    query_vector = embeddings.embed_query(query)



    



    conn = get_db_connection()



    cursor = conn.cursor()



    



    # Tìm 3 sản phẩm gần nhất bằng cosine distance (<=>)



    cursor.execute(



        """



        SELECT product_name, price, stock_quantity, description 



        FROM inventory 



        ORDER BY embedding <=> %s::vector 



        LIMIT 3



        """,



        (query_vector,)



    )



    results = cursor.fetchall()



    cursor.close()



    conn.close()



    



    if not results:



        return "Không tìm thấy sản phẩm nào phù hợp trong kho."



        



    res_str = "Danh sách sản phẩm tìm thấy trong kho:\n"



    for row in results:



        res_str += f"- Tên: {row[0]}, Giá: {row[1]}, Tồn kho: {row[2]}, Mô tả: {row[3]}\n"



    return res_str







# Định nghĩa các Tools dành cho Master Agent điều phối



@tool



def search_local_inventory(query: str) -> str:



    """Tìm kiếm thông tin sản phẩm, giá bán hoặc số lượng tồn kho trong kho hàng nội bộ của Geta."""



    return search_products(query)







@tool



def run_market_research_tool(query: str) -> str:



    """Kích hoạt và thực thi trình cào tự động Playwright để nghiên cứu đối thủ cạnh tranh, giá sỉ và số điện thoại liên hệ của sản phẩm/từ khóa được yêu cầu trên các nền tảng Cốc Cốc, Facebook & Tiktok."""



    script_path = "/app/scripts/market_research.py"



    try:



        print(f"[*] Master Agent Tool Call: Running market research for '{query}'...")



        subprocess.run([sys.executable, script_path, "--query", query], capture_output=True, text=True, check=True)



        



        # Đọc dữ liệu cào được trả về



        results_file = "/app/scripts/research_results.json"



        if os.path.exists(results_file):



            with open(results_file, "r", encoding="utf-8") as f:



                data = json.load(f)



                results = data.get("results", [])



                images = data.get("images", [])



                



                if results:



                    summary = f"Đã cào dữ liệu đối thủ thành công cho '{query}'.\n"



                    for r in results[:5]:



                        phone = r.get("phone") or "Chưa rõ"



                        price = f"{r['price']:,} đ" if r.get("price") else "Liên hệ"



                        summary += f"- {r['title']} ({r['platform']}), SĐT: {phone}, Giá sỉ: {price}, Link: {r['link']}\n"



                    if images:



                        summary += f"Đã quét được {len(images)} ảnh mẫu sản phẩm.\n"



                    return summary



        return "Đã chạy cào nhưng không tìm thấy dữ liệu đối thủ phù hợp."



    except Exception as e:



        return f"Lỗi khi chạy công cụ cào nghiên cứu thị trường: {str(e)}"







@tool



def export_leads_to_zalo_crm() -> str:



    """Đồng bộ danh bạ số điện thoại và thông tin đối thủ cạnh tranh mới nhất vừa thu thập được từ tệp kết quả nghiên cứu vào cơ sở dữ liệu Zalo CRM để liên hệ."""



    script_path = "/app/scripts/export_to_zalo_crm.py"



    try:



        print("[*] Master Agent Tool Call: Exporting leads to Zalo CRM...")



        result = subprocess.run([sys.executable, script_path], capture_output=True, text=True, check=True)



        return f"Đồng bộ Zalo CRM thành công! Chi tiết: {result.stdout.strip()}"



    except Exception as e:



        return f"Lỗi khi thực hiện đồng bộ Zalo CRM: {str(e)}"







@tool



def get_cron_jobs_status() -> str:



    """Xem trạng thái bật/tắt hiện tại của các tiến trình tự động (cron jobs)."""



    config_path = "/app/task_config.json"



    if not os.path.exists(config_path):



        return "Tất cả các tiến trình đều đang bật (Mặc định)."



    try:



        with open(config_path, "r", encoding="utf-8") as f:



            config = json.load(f)



        status_str = "Trạng thái các tiến trình:\n"



        for k, v in config.items():



            status_str += f"- {k}: {'BẬT' if v else 'TẮT'}\n"



        return status_str



    except Exception as e:



        return f"Lỗi đọc cấu hình: {e}"







@tool



def toggle_cron_job(job_name: str, state: bool) -> str:



    """Bật hoặc Tắt một tiến trình tự động. Truyền vào job_name (ví dụ 'auto_post_blog' hoặc 'auto_post_facebook') và state (True để bật, False để tắt)."""



    config_path = "/app/task_config.json"



    config = {}



    if os.path.exists(config_path):



        try:



            with open(config_path, "r", encoding="utf-8") as f:



                config = json.load(f)



        except:



            pass



    config[job_name] = state



    try:



        with open(config_path, "w", encoding="utf-8") as f:



            json.dump(config, f, indent=4)



        return f"Đã {'BẬT' if state else 'TẮT'} tiến trình '{job_name}' thành công."



    except Exception as e:



        return f"Lỗi lưu cấu hình: {e}"







@tool

def write_blog_now(keyword: str) -> str:

    """Yêu cầu viết bài Blog (SEO) ngay lập tức với từ khóa được truyền vào.

    QUAN TRỌNG: Công cụ này sẽ trả về một chuỗi bắt đầu bằng __COMMAND__. Bạn PHẢI BÊ NGUYÊN CHUỖI ĐÓ vào trong câu trả lời của bạn cho người dùng, không được thay đổi hoặc lược bớt nó!

    """

    return f"__COMMAND__:start_blog_workflow_with_keyword:{keyword}"

def submit_blog_task_to_celery(keyword: str, target_site: str = None, source_images: str = None) -> str:

    try:

        import sys

        import os

        blog_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../blog_tool'))

        if blog_dir not in sys.path:

            sys.path.append(blog_dir)

            

        from database.session import init_db

        from services.article_repository import ArticleRepository

        from celery_app import celery_app

        

        from database.models import ArticleStatus

        

        init_db()

        

        # Thêm từ khóa vào database với trạng thái PENDING

        article = ArticleRepository.add_keyword(

            keyword=keyword, 

            status=ArticleStatus.PENDING, 

            target_site=target_site, 

            source_images=source_images

        )

        

        # Gọi Celery Task generate_blog_task

        try:

            celery_app.send_task("tasks.generate_blog_task")

        except Exception:

            import subprocess

            tasks_script = os.path.abspath(os.path.join(os.path.dirname(__file__), 'tasks.py')).replace('\\', '/')

            env = os.environ.copy()

            env["PYTHONIOENCODING"] = "utf-8"

            subprocess.Popen([sys.executable, "-c", f"import sys, os; sys.path.append(os.path.dirname('{tasks_script}')); from tasks import generate_blog_task; generate_blog_task()"], env=env)

            

        return f"Đã thêm từ khóa '{keyword}' vào hàng đợi và kích hoạt tiến trình viết bài ngay lập tức! (Mã bài: {article.id}). Vui lòng chờ vài phút, Tôm sẽ gửi bài viết cho sếp duyệt trước khi đăng."

    except Exception as e:

        import traceback

        traceback.print_exc()

        return f"Lỗi nội bộ khi khởi tạo task: {e}"

@tool



def create_faceless_tiktok(topic: str, duration_seconds: int = 30) -> str:



    """Ra lệnh tự động dựng một video TikTok (chuẩn dọc 9:16) hoàn chỉnh. Đầu vào gồm chủ đề (topic) và thời lượng tuỳ chỉnh bằng giây (duration_seconds, mặc định 30s).



    Tiến trình này sẽ tự động sinh kịch bản, đọc AI voice và cắt ghép B-roll."""



    try:



        from video_engine.assembler import generate_faceless_tiktok



        



        # Gọi tool trực tiếp (trong thực tế nên đưa vào Celery nếu chạy quá lâu, nhưng tạm thời chạy đồng bộ để trả kết quả ngay)



        output_path = generate_faceless_tiktok(topic=topic, duration_seconds=duration_seconds)



        return f"Tuyệt vời! Video Tiktok của bạn về chủ đề '{topic}' (thời lượng {duration_seconds}s) đã được tạo thành công.\nBạn có thể xem file tại: {output_path}"



    except Exception as e:



        return f"Lỗi khi dựng video: {str(e)}"







def get_state(session_id: str) -> List[Any]:



    """Lấy lịch sử chat từ database."""



    conn = get_db_connection()



    cursor = conn.cursor()



    cursor.execute("SELECT state FROM agent_states WHERE session_id = %s", (session_id,))



    row = cursor.fetchone()



    cursor.close()



    conn.close()



    



    if row and row[0]:



        state_dict = row[0]



        messages = []



        for msg in state_dict.get("messages", []):



            if msg["type"] == "human":



                messages.append(HumanMessage(content=msg["content"]))



            elif msg["type"] == "ai":



                messages.append(AIMessage(content=msg["content"]))



        return messages



    return []







def save_state(session_id: str, messages: List[Any]):



    """Lưu lịch sử chat vào database."""



    state_msgs = []



    for msg in messages:



        if isinstance(msg, HumanMessage):



            state_msgs.append({"type": "human", "content": msg.content})



        elif isinstance(msg, AIMessage):



            state_msgs.append({"type": "ai", "content": msg.content})



            



    state_json = json.dumps({"messages": state_msgs})



    



    conn = get_db_connection()



    cursor = conn.cursor()



    cursor.execute(



        """



        INSERT INTO agent_states (session_id, thread_id, state) 



        VALUES (%s, %s, %s) 



        ON CONFLICT (session_id) DO UPDATE SET state = EXCLUDED.state, updated_at = CURRENT_TIMESTAMP



        """,



        (session_id, session_id, state_json)



    )



    conn.commit()



    cursor.close()



    conn.close()







def get_gemini_keys() -> List[str]:



    keys_str = os.getenv("GEMINI_API_KEYS", "")



    if not keys_str:



        return []



    return [k.strip() for k in keys_str.split(",") if k.strip()]







def run_agent(session_id: str, user_message: str) -> str:



    messages = get_state(session_id)



    



    sys_prompt = """Bạn là trợ lý ảo và Master Agent điều phối cao cấp của hệ thống Geta.

Bạn được cung cấp các công cụ (tools) để tương tác trực tiếp với cơ sở dữ liệu và hệ thống cào.



QUY TẮC CỰC KỲ QUAN TRỌNG:

1. NẾU sếp yêu cầu "viết bài", "viết blog", "tạo bài", "đăng blog",... hoặc cung cấp từ khóa/chủ đề bài viết (như "ngành in ly tây ninh", "ly nhựa giá sỉ", "in ly Tây Ninh"), bạn BẮT BUỘC phải sử dụng công cụ `write_blog_now`. TUYỆT ĐỐI KHÔNG được gọi phòng Nghiên Cứu đối với các chủ đề bài viết.

2. Công cụ `write_blog_now` sẽ trả về một chuỗi bắt đầu bằng __COMMAND__:start_blog_workflow_with_keyword:. Bạn PHẢI BÊ NGUYÊN CHUỖI ĐÓ vào trong câu trả lời cuối cùng cho người dùng, không được thay đổi hoặc lược bớt nó!

3. Bạn phải sử dụng công cụ `run_market_research_tool` để cào dữ liệu thực tế mỗi khi người dùng yêu cầu tìm sản phẩm, tìm đối thủ hoặc nghiên cứu thị trường.

4. TUYỆT ĐỐI KHÔNG TỰ BỊA ĐẶT các tệp tin kết quả. Tệp tin duy nhất được lưu trên máy của người dùng sau khi cào là "scripts/research_results.json".

5. Nếu người dùng yêu cầu kiểm tra giá bán hoặc tồn kho của một sản phẩm trong kho của Geta -> hãy dùng công cụ `search_local_inventory`.

6. Nếu người dùng yêu cầu đồng bộ, lưu trữ danh sách liên hệ hoặc thông tin đối thủ thu thập được vào Zalo CRM -> hãy dùng công cụ `export_leads_to_zalo_crm`.

7. Nếu người dùng yêu cầu kiểm tra trạng thái của các luồng chạy tự động (cron jobs) -> dùng công cụ `get_cron_jobs_status`.

8. Nếu người dùng yêu cầu bật/tắt (hoặc kích hoạt/vô hiệu hóa) một luồng chạy tự động -> dùng công cụ `toggle_cron_job`.

9. Nếu người dùng yêu cầu làm video TikTok (Faceless) về một chủ đề nào đó -> dùng công cụ `create_faceless_tiktok`. Cố gắng trích xuất số giây nếu người dùng có yêu cầu (ví dụ: '15s', '60 giây').

10. Nếu người dùng chỉ hỏi han thông thường hoặc chat xã giao -> trả lời lịch sự không cần gọi công cụ.

"""



    current_msgs = [SystemMessage(content=sys_prompt)] + messages + [HumanMessage(content=user_message)]



    



    # Danh sách tools đăng ký với LLM



    agent_tools = [search_local_inventory, run_market_research_tool, export_leads_to_zalo_crm, get_cron_jobs_status, toggle_cron_job, write_blog_now, create_faceless_tiktok]



    tools_map = {t.name: t for t in agent_tools}



    



    llm = None



    deepseek_key = os.getenv("DEEPSEEK_API_KEY")



    



    # 1. Khởi tạo LLM (Thử DeepSeek trước, fallback sang Gemini)



    if deepseek_key:



        try:



            llm = ChatOpenAI(



                api_key=deepseek_key, 



                base_url="https://api.deepseek.com/v1", 



                model="deepseek-v4-flash",



                temperature=0.1



            )



        except Exception as e:



            print(f"DeepSeek init error: {e}")



            llm = None



            



    if not llm:



        gemini_keys = get_gemini_keys()



        for key in gemini_keys:



            try:



                llm = ChatGoogleGenerativeAI(



                    model="gemini-2.5-flash",



                    temperature=0.1,



                    google_api_key=key



                )



                break



            except Exception as e:



                print(f"Gemini init error: {e}")



                continue



                



    if not llm:



        return "Xin lỗi, hệ thống AI đang quá tải (Tất cả API Keys đều lỗi)."



        



    try:



        # 2. Ràng buộc các công cụ vào LLM



        llm_with_tools = llm.bind_tools(agent_tools)



        print(f"[*] Calling Master Agent with message: '{user_message}'")



        response = llm_with_tools.invoke(current_msgs)



        



        # Nhận diện ý định từ tin nhắn để kích hoạt Fail-safe nếu LLM không gọi tool



        msg_lower = user_message.lower()



        has_research_keyword = any(k in msg_lower for k in ["tìm các", "tìm kiếm", "nghiên cứu", "tìm mẫu", "tìm sản phẩm", "quét giá", "giúp tôi tìm", "cào", "quét", "làm lại", "chạy lại", "quét lại", "đối thủ", "nhà cung cấp", "supplier"])



        has_inventory_keyword = any(k in msg_lower for k in ["kho", "tồn kho", "giá bán", "trong kho", "sản phẩm"])



        has_crm_keyword = any(k in msg_lower for k in ["crm", "zalo", "đồng bộ", "export", "lưu"])



        has_blog_keyword = any(k in msg_lower for k in ["viết bài", "đăng bài blog", "đăng blog", "post bài", "viết blog", "tạo blog", "viết blog về", "blog"])



        has_cron_toggle = any(k in msg_lower for k in ["tắt tự động", "bật tự động", "tắt tiến trình", "bật tiến trình", "tắt auto", "bật auto"])



        has_cron_status = any(k in msg_lower for k in ["trạng thái tiến trình", "trạng thái tự động", "trạng thái auto"])



        has_video_keyword = any(k in msg_lower for k in ["làm video", "tạo video", "dựng video", "edit video", "tiktok"])







        



        # 3. Kiểm tra xem LLM có kích hoạt Tool Call nào không



        # Xử lý trường hợp DeepSeek trả về DSML raw text thay vì tool_calls JSON



        if "<｜｜DSML｜｜toolcalls>" in response.content and "createfacelesstiktok" in response.content.lower():



            import re



            topic_match = re.search(r'<｜｜DSML｜｜parameter name="topic" string="true">(.*?)</｜｜DSML｜｜parameter>', response.content)



            topic = topic_match.group(1) if topic_match else "video"



            tool_result = create_faceless_tiktok.invoke({"topic": topic, "duration_seconds": 15})



            if "__COMMAND__" in str(tool_result):



                return str(tool_result)







        if response.tool_calls:



            print(f"[+] Master Agent decided to call tools: {response.tool_calls}")



            current_msgs.append(response)



            



            # Map tools không phân biệt hoa thường và dấu gạch dưới



            tools_map_clean = {k.lower().replace("_", ""): v for k, v in tools_map.items()}



            



            for tool_call in response.tool_calls:



                t_name = tool_call["name"]



                t_args = tool_call["args"]



                t_name_clean = t_name.lower().replace("_", "")



                tool_obj = tools_map_clean.get(t_name_clean)



                



                if tool_obj:



                    # Chạy công cụ và lấy kết quả



                    tool_result = tool_obj.invoke(t_args)



                    print(f"[+] Tool '{t_name}' execution result: {tool_result}")



                    current_msgs.append(ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"]))



            



            # Gọi lại LLM để tổng hợp kết quả của Tool Call thành câu trả lời tự nhiên



            final_response = llm.invoke(current_msgs)



            ai_reply = final_response.content



            



        elif has_research_keyword and not has_blog_keyword:



            # FAIL-SAFE: Buộc gọi tool cào nghiên cứu thị trường nếu LLM lười/bị lừa



            print("[!] Fail-safe triggered: Forcing run_market_research_tool...")



            clean_query = user_message



            for kw in ["giúp tôi tìm các", "giúp tôi tìm", "tìm các", "tìm kiếm", "nghiên cứu", "tìm mẫu", "tìm sản phẩm", "quét giá", "cào", "quét", "làm lại", "chạy lại", "quét lại"]:



                clean_query = clean_query.replace(kw, "")



            clean_query = clean_query.strip()



            if not clean_query:



                clean_query = "gạch decor"



                



            tool_result = run_market_research_tool.invoke({"query": clean_query})



            current_msgs.append(AIMessage(content="", tool_calls=[{"name": "run_market_research_tool", "args": {"query": clean_query}, "id": "forced_call_research"}]))



            current_msgs.append(ToolMessage(content=str(tool_result), tool_call_id="forced_call_research"))



            



            final_response = llm.invoke(current_msgs)



            ai_reply = final_response.content



            



        elif has_crm_keyword:



            # FAIL-SAFE: Buộc gọi tool đồng bộ Zalo CRM



            print("[!] Fail-safe triggered: Forcing export_leads_to_zalo_crm...")



            tool_result = export_leads_to_zalo_crm.invoke()



            current_msgs.append(AIMessage(content="", tool_calls=[{"name": "export_leads_to_zalo_crm", "args": {}, "id": "forced_call_crm"}]))



            current_msgs.append(ToolMessage(content=str(tool_result), tool_call_id="forced_call_crm"))



            



            final_response = llm.invoke(current_msgs)



            ai_reply = final_response.content



            



        elif has_inventory_keyword:



            # FAIL-SAFE: Buộc gọi tool tra cứu kho hàng



            print("[!] Fail-safe triggered: Forcing search_local_inventory...")



            tool_result = search_local_inventory.invoke({"query": user_message})



            current_msgs.append(AIMessage(content="", tool_calls=[{"name": "search_local_inventory", "args": {"query": user_message}, "id": "forced_call_inv"}]))



            current_msgs.append(ToolMessage(content=str(tool_result), tool_call_id="forced_call_inv"))



            



            final_response = llm.invoke(current_msgs)



            ai_reply = final_response.content



            



        elif has_blog_keyword:

            print("[!] Fail-safe triggered: Forcing write_blog_now...")

            clean_query = user_message

            # Xóa các từ khóa hành động

            for kw in ["viết blog về", "viết blog", "viết bài blog về", "viết bài blog", "viết bài về", "viết bài", "đăng bài blog", "đăng blog", "post bài", "tạo bài", "tạo blog", "chủ đề", "từ khóa"]:

                clean_query = re.sub(rf'(?i)\\b{re.escape(kw)}\\b', '', clean_query)

            # Xóa các phần bổ trợ ở cuối hoặc đầu

            clean_query = re.sub(r'(?i)\\b(có chèn ảnh|chèn ảnh|chuẩn seo|seo|ngay|nhé|cho tôi|về)\\b', '', clean_query)

            clean_query = clean_query.strip().strip('"').strip("'").strip(',')

            

            if not clean_query or clean_query.lower() in ["viết blog", "viết bài", "blog", "content", "bài viết"]:

                ai_reply = "Dạ sếp, Tôm đã sẵn sàng! Sếp muốn viết bài blog về chủ đề hoặc từ khóa nào cụ thể thế ạ? Nhắn cho Tôm từ khóa (ví dụ: 'in ly Tây Ninh'), Tôm sẽ kích hoạt luồng chọn ảnh và tạo bài ngay nhé! 📝"

            else:

                tool_result = write_blog_now.invoke({"keyword": clean_query})

                current_msgs.append(AIMessage(content="", tool_calls=[{"name": "write_blog_now", "args": {"keyword": clean_query}, "id": "forced_call_blog"}]))

                current_msgs.append(ToolMessage(content=str(tool_result), tool_call_id="forced_call_blog"))

                final_response = llm.invoke(current_msgs)

                ai_reply = final_response.content

        elif has_cron_toggle:



            print("[!] Fail-safe triggered: Forcing toggle_cron_job...")



            state = "bật" in msg_lower



            job_name = "auto_post_blog" if "blog" in msg_lower else "auto_post_facebook"



            tool_result = toggle_cron_job.invoke({"job_name": job_name, "state": state})



            current_msgs.append(AIMessage(content="", tool_calls=[{"name": "toggle_cron_job", "args": {"job_name": job_name, "state": state}, "id": "forced_call_toggle"}]))



            current_msgs.append(ToolMessage(content=str(tool_result), tool_call_id="forced_call_toggle"))



            



            final_response = llm.invoke(current_msgs)



            ai_reply = final_response.content



            



        elif has_cron_status:



            print("[!] Fail-safe triggered: Forcing get_cron_jobs_status...")



            tool_result = get_cron_jobs_status.invoke({})



            current_msgs.append(AIMessage(content="", tool_calls=[{"name": "get_cron_jobs_status", "args": {}, "id": "forced_call_status"}]))



            current_msgs.append(ToolMessage(content=str(tool_result), tool_call_id="forced_call_status"))



            



            final_response = llm.invoke(current_msgs)



            ai_reply = final_response.content



            



        elif has_video_keyword:



            print("[!] Fail-safe triggered: Forcing create_faceless_tiktok...")



            # Xử lý lấy duration từ message (ví dụ: '15s', '15 giây')



            import re



            duration = 30



            match = re.search(r'(\d+)\s*(s|giây)', msg_lower)



            if match:



                duration = int(match.group(1))



                



            clean_query = user_message



            for kw in ["làm video", "tạo video", "dựng video", "edit video", "tiktok", "giúp tôi", "nhé", "về"]:



                clean_query = clean_query.replace(kw, "")



            clean_query = re.sub(r'\d+\s*(s|giây)', '', clean_query, flags=re.IGNORECASE).strip()



            



            tool_result = create_faceless_tiktok.invoke({"topic": clean_query, "duration_seconds": duration})



            current_msgs.append(AIMessage(content="", tool_calls=[{"name": "create_faceless_tiktok", "args": {"topic": clean_query, "duration_seconds": duration}, "id": "forced_call_video"}]))



            current_msgs.append(ToolMessage(content=str(tool_result), tool_call_id="forced_call_video"))



            



            final_response = llm.invoke(current_msgs)



            ai_reply = final_response.content



            



        else:



            ai_reply = response.content



            



    except Exception as e:



        print(f"Error executing agent tool calling loop: {e}")



        # Fallback về gọi LLM thường nếu tool call bị crash



        try:



            resp = llm.invoke(current_msgs)



            ai_reply = resp.content



        except:



            return "Gặp sự cố khi xử lý tác vụ điều phối."







    # Lưu state



    messages.append(HumanMessage(content=user_message))



    messages.append(AIMessage(content=ai_reply))



    save_state(session_id, messages[-10:])



    



    return ai_reply



