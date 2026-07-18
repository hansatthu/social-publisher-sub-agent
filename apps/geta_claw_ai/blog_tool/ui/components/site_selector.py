import streamlit as st
from ui.state import get_site_options, load_sites_config

def render_site_selector():
    # Cấu hình header & font
    st.markdown(
        """
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
        <style>
        .selector-header {
            font-family: 'Outfit', sans-serif;
            text-align: center;
            margin-top: 2rem;
            margin-bottom: 2.5rem;
        }
        .selector-title {
            font-size: 2.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #60A5FA 0%, #3B82F6 50%, #1D4ED8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        .selector-subtitle {
            font-size: 1.1rem;
            color: #94A3B8;
            font-weight: 300;
        }
        .site-card-wrapper {
            font-family: 'Outfit', sans-serif;
            background: rgba(30, 41, 59, 0.45);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 20px;
            padding: 28px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            backdrop-filter: blur(10px);
            margin-bottom: 1.5rem;
            height: 480px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .site-card-wrapper:hover {
            transform: translateY(-8px);
            border-color: rgba(59, 130, 246, 0.6);
            box-shadow: 0 15px 35px rgba(59, 130, 246, 0.25);
            background: rgba(30, 41, 59, 0.6);
        }
        .site-header {
            text-align: center;
            margin-bottom: 20px;
        }
        .site-icon {
            font-size: 3.5rem;
            margin-bottom: 10px;
            display: inline-block;
            transition: transform 0.3s ease;
        }
        .site-card-wrapper:hover .site-icon {
            transform: scale(1.15) rotate(5deg);
        }
        .site-name-title {
            font-size: 1.45rem;
            font-weight: 700;
            color: #F8FAFC;
            margin: 5px 0;
            letter-spacing: -0.02em;
        }
        .site-url-link {
            font-size: 0.88rem;
            color: #3B82F6;
            text-decoration: none;
            font-family: monospace;
            opacity: 0.9;
        }
        .site-desc-text {
            font-size: 0.92rem;
            color: #CBD5E1;
            line-height: 1.5;
            text-align: center;
            margin-bottom: 20px;
            min-height: 55px;
        }
        .site-bullet-list {
            list-style: none;
            padding: 0;
            margin: 0 0 25px 0;
            flex-grow: 1;
        }
        .site-bullet-item {
            font-size: 0.85rem;
            color: #94A3B8;
            margin-bottom: 10px;
            padding-left: 20px;
            position: relative;
            line-height: 1.4;
        }
        .site-bullet-item::before {
            content: "✦";
            position: absolute;
            left: 0;
            top: 0;
            color: #3B82F6;
            font-size: 0.75rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="selector-header">
            <div class="selector-title">SEO Automation Workspace</div>
            <div class="selector-subtitle">Vui lòng chọn Website bạn muốn làm việc dưới đây</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sites = load_sites_config()
    
    # Metadata bổ sung để hiển thị UI đẹp hơn cho từng site
    ui_metadata = {
        "mocbaibavet.com": {
            "emoji": "🏗️",
            "title_vi": "Mộc Bài Bavet",
            "desc": "Chuyên trang thiết kế nội thất, thi công xây dựng & gia công bảng hiệu quảng cáo.",
            "tags": [
                "Thi công xây dựng & F&B",
                "Thiết kế thi công nội thất",
                "Quảng cáo & Signage",
                "Tối ưu SEO ngành xây dựng"
            ]
        },
        "innhanhgeta.com": {
            "emoji": "🖨️",
            "title_vi": "In Nhanh GETA",
            "desc": "Chuyên trang in ấn kỹ thuật số, offset, ấn phẩm văn phòng & bao bì thương mại.",
            "tags": [
                "In nhanh & In Offset chất lượng",
                "Ấn phẩm văn phòng & Tiếp thị",
                "Tem nhãn & Bao bì sản phẩm",
                "Tối ưu hóa phễu CTA Báo giá"
            ]
        },
        "quangcao.getagroup.vn": {
            "emoji": "📣",
            "title_vi": "Quảng Cáo GETA",
            "desc": "Chuyên trang làm bảng hiệu, hộp đèn chữ nổi & bộ nhận diện thương hiệu doanh nghiệp.",
            "tags": [
                "Bảng hiệu quảng cáo & Chữ nổi",
                "Booth sự kiện & POSM",
                "Decal, Băng rôn & Standee",
                "Định vị thương hiệu GETA Group"
            ]
        }
    }

    cols = st.columns(len(sites), gap="medium")
    
    for idx, site in enumerate(sites):
        name = site["name"]
        wp_site_url = site["wp_site_url"]
        
        meta = ui_metadata.get(name, {
            "emoji": "🌐",
            "title_vi": name,
            "desc": "Hệ thống quản lý nội dung và tự động hóa SEO.",
            "tags": ["Tự động viết bài AI", "Đồng bộ Google Sheets", "Tự động đăng bài"]
        })
        
        with cols[idx]:
            bullets_html = "".join(
                f'<li class="site-bullet-item">{tag}</li>' for tag in meta["tags"]
            )
            
            st.markdown(
                f"""
                <div class="site-card-wrapper">
                    <div class="site-header">
                        <span class="site-icon">{meta["emoji"]}</span>
                        <div class="site-name-title">{meta["title_vi"]}</div>
                        <a href="{wp_site_url}" target="_blank" class="site-url-link">{name}</a>
                    </div>
                    <div class="site-desc-text">{meta["desc"]}</div>
                    <ul class="site-bullet-list">
                        {bullets_html}
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            
            if st.button(f"Làm việc với {meta['title_vi']} 🚀", key=f"btn_select_{name}", use_container_width=True, type="primary"):
                st.session_state["active_site"] = name
                st.rerun()
