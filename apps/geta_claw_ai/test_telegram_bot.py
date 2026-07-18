import os
import sys

# Đảm bảo đường dẫn
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from backend.core_agent import run_agent
from dotenv import load_dotenv
from unittest.mock import patch, MagicMock

# Tải biến môi trường
load_dotenv(".env")

@patch('backend.core_agent.get_db_connection')
def test_telegram_bot(mock_get_db_connection):
    test_session = "test_user_123"
    
    # Mock Database connection to avoid Postgres connection refused error
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None
    mock_get_db_connection.return_value = mock_conn
    
    print("==================================================")
    print("🧪 BẮT ĐẦU TEST BOT TELEGRAM (TẤT CẢ CÁC TÁC VỤ) 🧪")
    print("==================================================\n")
    
    test_cases = [
        # 1. Chat thông thường (không gọi tool)
        "Xin chào, bạn có thể giúp tôi việc gì?",
        
        # 2. Check trạng thái tiến trình (Cron status)
        "Kiểm tra trạng thái tiến trình tự động giúp tôi",
        
        # 3. Viết bài blog (Write blog now)
        "Viết bài blog về hướng dẫn mua nhà chung cư cho người mới",
        
        # 4. Làm video tiktok (Video Engine)
        "Làm video tiktok dài 15s về ly giữ nhiệt",
        
        # 5. Tắt/Bật tiến trình (Toggle Cron)
        "Tắt tiến trình đăng bài lên Facebook",
        
        # 6. Tìm kiếm thông tin nội bộ (Search Local)
        "Tìm cho tôi thông tin về căn hộ 2 phòng ngủ ở quận 7",
        
        # 7. Phân tích thị trường
        "Nghiên cứu thị trường bán lẻ cà phê ở Việt Nam"
    ]
    
    for query in test_cases:
        print(f"👤 USER: {query}")
        print("⏳ Bot đang suy nghĩ và thực thi...")
        try:
            response = run_agent(test_session, query)
            print(f"🤖 BOT: {response}")
        except Exception as e:
            print(f"❌ LỖI: {e}")
        print("-" * 50)

if __name__ == "__main__":
    test_telegram_bot()
