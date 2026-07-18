import os
import psycopg2
from pgvector.psycopg2 import register_vector
from langchain_community.embeddings import OllamaEmbeddings

DB_URL = os.getenv("POSTGRES_URL", "postgresql://user:password@localhost:5432/automation_db")
OLLAMA_BASE_URL = "http://ollama:11434"

# Dữ liệu giả lập
PRODUCTS = [
    {"name": "Giày chạy bộ nam siêu nhẹ", "price": 1500000, "stock": 50, "desc": "Giày chạy bộ thiết kế công thái học, màu trắng/đen, size 39-44. Phù hợp chạy bộ đường dài."},
    {"name": "Áo thun cotton nam", "price": 250000, "stock": 200, "desc": "Áo thun 100% cotton thoáng mát, thấm hút mồ hôi. Màu đen/trắng/xám, freesize."},
    {"name": "Balo laptop chống nước", "price": 850000, "stock": 30, "desc": "Balo laptop 15.6 inch, chất liệu vải oxford chống nước cao cấp. Có cổng sạc USB."},
    {"name": "Mũ lưỡi trai thể thao", "price": 120000, "stock": 100, "desc": "Mũ thể thao che nắng, form chuẩn. Màu đen tuyền, có quai dán điều chỉnh."},
    {"name": "Giày sneaker nữ đế cao", "price": 1200000, "stock": 45, "desc": "Giày sneaker thời trang cho nữ, đế cao 5cm, êm chân. Phù hợp đi chơi, dạo phố. Màu trắng/hồng."}
]

def get_db_connection():
    url = DB_URL.replace("postgresql://", "postgres://")
    return psycopg2.connect(url)

def main():
    print("Connecting to DB...")
    conn = get_db_connection()
    register_vector(conn)
    cursor = conn.cursor()

    # Xóa dữ liệu cũ
    cursor.execute("TRUNCATE TABLE inventory CASCADE")
    
    print("Khởi tạo OllamaEmbeddings...")
    embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL)

    for item in PRODUCTS:
        print(f"Tạo vector cho: {item['name']}...")
        text_to_embed = f"Tên sản phẩm: {item['name']}\nGiá: {item['price']}\nMô tả: {item['desc']}"
        vector = embeddings.embed_query(text_to_embed)
        
        cursor.execute(
            """
            INSERT INTO inventory (product_name, description, price, stock_quantity, embedding)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (item['name'], item['desc'], item['price'], item['stock'], vector)
        )
        
        # Thêm vào bảng kho của geta-finance
        import uuid
        cursor.execute(
            """
            INSERT INTO inventory_items (id, item_code, item_name, current_stock, is_active, updated_at)
            VALUES (%s, %s, %s, %s, true, NOW())
            ON CONFLICT (item_code) DO UPDATE SET current_stock = EXCLUDED.current_stock
            """,
            (str(uuid.uuid4()), f"PROD-{PRODUCTS.index(item)+1}", item['name'], item['stock'])
        )
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Hoàn tất chèn dữ liệu và vector!")

if __name__ == "__main__":
    main()
