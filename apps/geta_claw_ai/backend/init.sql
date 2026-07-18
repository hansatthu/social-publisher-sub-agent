CREATE EXTENSION IF NOT EXISTS vector;

-- Bảng lưu trữ Kho hàng
CREATE TABLE IF NOT EXISTS inventory (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    stock_quantity INT DEFAULT 0,
    embedding vector(768), -- Cho text embeddings sau này
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bảng lưu trữ Đơn hàng
CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255),
    customer_name VARCHAR(255),
    product_id INT REFERENCES inventory(product_id),
    quantity INT NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING',
    idempotency_key VARCHAR(255) UNIQUE,
    campaign_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bảng lưu trữ trạng thái hội thoại LangGraph
CREATE TABLE IF NOT EXISTS agent_states (
    session_id VARCHAR(255) PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL,
    state JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bảng lưu trữ log chi phí quảng cáo (sẽ lấy từ webhook/API ngoài)
CREATE TABLE IF NOT EXISTS ads_metrics (
    metric_id SERIAL PRIMARY KEY,
    campaign_id VARCHAR(255),
    platform VARCHAR(50), -- e.g., 'facebook', 'tiktok'
    spend DECIMAL(10, 2) DEFAULT 0,
    clicks INT DEFAULT 0,
    impressions INT DEFAULT 0,
    purchases INT DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- B?ng luu tr? c?u h�nh Browser Profiles cho Automation RPA
CREATE TABLE IF NOT EXISTS browser_profiles (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL, -- 'FACEBOOK', 'TIKTOK', 'WORDPRESS'
    profile_name VARCHAR(255) NOT NULL, -- e.g., 'Profile 1'
    profile_path VARCHAR(500) NOT NULL, -- e.g., 'C:\Users\Admin\AppData\Local\Google\Chrome\User Data\Profile 1'
    status VARCHAR(50) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
