import requests
import json
import time

URL_WEBHOOK = "http://localhost:8000/webhook"
URL_LOGISTICS = "http://localhost:8000/webhook/logistics"

print("1. Testing Idempotency Key Middleware...")
payload_webhook = {"message": "Tôi muốn mua một cái áo thun", "session_id": "test_idemp"}
headers = {"Idempotency-Key": "test-key-12345"}

start = time.time()
resp1 = requests.post(URL_WEBHOOK, json=payload_webhook, headers=headers)
print(f"Lần 1 (Không có cache): TTFT {(time.time()-start)*1000:.0f}ms")
print(resp1.json())

start = time.time()
resp2 = requests.post(URL_WEBHOOK, json=payload_webhook, headers=headers)
print(f"Lần 2 (Có cache): TTFT {(time.time()-start)*1000:.0f}ms")
print(resp2.json())

print("\n2. Testing Logistics Webhook...")
# Assuming order_id = 1 exists from seed_ads.py
payload_logistics = {"order_id": 1, "status": "SHIPPED"}
resp_logistics = requests.post(URL_LOGISTICS, json=payload_logistics)
print(resp_logistics.json())
