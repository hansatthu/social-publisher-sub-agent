import os
import psycopg2

DB_URL = os.getenv("POSTGRES_URL", "postgresql://user:password@localhost:5432/automation_db")
url_sync = DB_URL.replace("postgresql://", "postgres://")

def get_db_connection():
    return psycopg2.connect(url_sync)

def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Bổ sung cột campaign_id nếu chưa có (vì database đã init trước đó)
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS campaign_id VARCHAR(255);")
        conn.commit()
    except Exception as e:
        print("Column campaign_id already exists or error:", e)
        conn.rollback()

    # 2. Xóa dữ liệu cũ
    cursor.execute("TRUNCATE TABLE ads_metrics CASCADE")
    cursor.execute("TRUNCATE TABLE orders CASCADE")
    
    # 3. Tạo dữ liệu giả lập cho ads_metrics
    ads_data = [
        ("CMP_FB_01", "facebook", 5000000, 2000, 50000, 50),
        ("CMP_TK_02", "tiktok", 8000000, 5000, 150000, 120),
        ("CMP_GG_03", "google", 2000000, 500, 10000, 10)
    ]
    
    for row in ads_data:
        cursor.execute(
            """INSERT INTO ads_metrics (campaign_id, platform, spend, clicks, impressions, purchases)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            row
        )
        
    # 4. Tạo dữ liệu giả lập cho orders map với campaign_id
    # FB_01 mang lại 20 triệu doanh thu (ROAS = 4)
    # TK_02 mang lại 12 triệu doanh thu (ROAS = 1.5 -> Kém)
    # GG_03 mang lại 10 triệu doanh thu (ROAS = 5)
    
    orders_data = [
        ("CMP_FB_01", 20000000),
        ("CMP_TK_02", 12000000),
        ("CMP_GG_03", 10000000)
    ]
    
    for row in orders_data:
        cursor.execute(
            """INSERT INTO orders (customer_id, customer_name, product_id, quantity, total_amount, campaign_id)
               VALUES ('CUS_01', 'Nguyen Van A', 1, 1, %s, %s)""",
            (row[1], row[0])
        )
        
    conn.commit()
    print("Seeded Ads and Orders successfully!")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
