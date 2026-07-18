import requests
import json
import time

URL = "http://localhost:8000/webhook"
SESSION_ID = "test_user_phase4_retry"

messages = [
    "Tôi đang tìm mua một đôi giày",
    "Cho tôi hỏi mua đôi giày đó có màu trắng không?",
    "Cho tôi xin giá tiền của đôi giày đó nhé?",
    "Đôi giày siêu nhẹ đó còn hàng để mua không shop?",
    "Ok, tôi chốt mua đôi siêu nhẹ đó nhé."
]

for msg in messages:
    print(f"\nUser: {msg}")
    payload = {"message": msg, "session_id": SESSION_ID}
    start = time.time()
    try:
        resp = requests.post(URL, json=payload, timeout=60)
        res_data = resp.json()
        print(f"Agent: {res_data.get('reply')}")
        print(f"[Intent: {res_data.get('intent')} | TTFT: {(time.time() - start)*1000:.0f}ms]")
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(1)
