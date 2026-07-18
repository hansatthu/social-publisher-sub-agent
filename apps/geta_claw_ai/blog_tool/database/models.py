import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class ArticleStatus(enum.Enum):
    """Định nghĩa Data State Machine cho pipeline"""
    AWAITING_SITE = "AWAITING_SITE" # Chờ chọn website đăng
    PENDING = "PENDING"       # Mới nạp keyword, chờ xử lý
    PROCESSING = "PROCESSING" # Đang call LLM API
    GENERATE_FAILED = "GENERATE_FAILED" # Lỗi ở bước generate nội dung
    GENERATED = "GENERATED"   # Đã sinh xong text & metadata
    UPLOAD_FAILED = "UPLOAD_FAILED" # Lỗi ở bước upload/publish lên WordPress
    PUBLISHED = "PUBLISHED"   # Đã push thành công lên WordPress
    FAILED = "FAILED"         # Legacy status (backward compatibility)

class Article(Base):
    __tablename__ = 'articles'

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Input Data
    keyword = Column(String(255), nullable=False)
    context = Column(Text, nullable=True) 
    long_tail_keywords = Column(Text, nullable=True)  # JSON hoặc CSV của 5 long-tail keywords đi kèm primary keyword
    language = Column(String(50), nullable=True)
    category_id = Column(Integer, nullable=True)
    category_name = Column(String(255), nullable=True)
    source_images = Column(Text, nullable=True)
    target_site = Column(String(255), nullable=True)
    
    # Output Data
    title = Column(String(255), nullable=True)
    meta_description = Column(String(500), nullable=True)
    slug = Column(String(255), nullable=True)
    content_markdown = Column(Text, nullable=True)
    content_html = Column(Text, nullable=True)
    
    # Integration & Tracking
    target_sites = Column(String(500), nullable=True)
    status = Column(Enum(ArticleStatus), default=ArticleStatus.PENDING)
    wp_post_id = Column(Integer, nullable=True)
    wp_post_url = Column(String(500), nullable=True)
    error_log = Column(Text, nullable=True)
    seo_score = Column(Integer, nullable=True)
    seo_notes = Column(Text, nullable=True)
    
    # Audit Trails
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Article(id={self.id}, keyword='{self.keyword}', status={self.status})>"


class Product(Base):
    __tablename__ = 'products'

    # Primary Key
    product_id = Column(Integer, primary_key=True, autoincrement=True)

    # Product Data (nullable theo yêu cầu)
    name = Column(String(255), nullable=True)
    regular_price = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    short_description = Column(Text, nullable=True)
    sku = Column(String(100), nullable=True)
    stock_quantity = Column(Integer, nullable=True)
    categories = Column(Text, nullable=True)
    images = Column(Text, nullable=True)
    local_images = Column(Text, nullable=True)

    # Integration Tracking
    wc_remote_id = Column(Integer, nullable=True)
    product_url = Column(String(500), nullable=True)
    status = Column(String(50), nullable=True)
    error_log = Column(Text, nullable=True)

    # Audit Trails
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Product(product_id={self.product_id}, sku='{self.sku}', name='{self.name}')>"