import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const resources = {
  vi: {
    translation: {
      dashboard: 'Bảng Điều Khiển Automation',
      total_revenue: 'Tổng Doanh Thu',
      total_orders: 'Tổng Đơn Hàng',
      inventory_status: 'Trạng Thái Tồn Kho',
      ads_roas: 'Hiệu Quả Quảng Cáo (ROAS)',
      spend: 'Chi phí',
      revenue: 'Doanh thu',
      roas: 'Chỉ số ROAS',
      product: 'Sản phẩm',
      stock: 'Tồn kho',
      price: 'Giá bán',
      campaign: 'Chiến dịch',
      platform: 'Nền tảng',
      loading: 'Đang tải dữ liệu...',
      error: 'Lỗi tải dữ liệu'
    }
  },
  en: {
    translation: {
      dashboard: 'Automation Dashboard',
      total_revenue: 'Total Revenue',
      total_orders: 'Total Orders',
      inventory_status: 'Inventory Status',
      ads_roas: 'Ads Performance (ROAS)',
      spend: 'Spend',
      revenue: 'Revenue',
      roas: 'ROAS Index',
      product: 'Product',
      stock: 'Stock',
      price: 'Price',
      campaign: 'Campaign',
      platform: 'Platform',
      loading: 'Loading data...',
      error: 'Error loading data'
    }
  }
};

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: 'vi',
    fallbackLng: 'en',
    interpolation: { escapeValue: false }
  });

export default i18n;
