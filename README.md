# Vaithuhayho Web Application

Nền tảng Webapp tập trung các Tool-Offline của OB VND, được phát triển bởi [VND] Hoàng Mập - OB.

## 📋 Tính năng

- ✅ **Scan Tool** - Quản lý điểm danh nhân viên (In/Out/Task)
- ✅ **Handover Tool** - Quản lý bàn giao đơn hàng (SPX, GHN)
- ✅ **Real-time sync** với Firebase Realtime Database
- ✅ **Export báo cáo Excel** tự động
- ✅ **Responsive design** cho mobile
- ✅ **Unified CSS** - Single stylesheet cho toàn bộ webapp

## 🚀 Cài đặt

### Yêu cầu

- Python 3.8+
- Firebase Admin SDK credentials

### Các bước cài đặt

1. **Clone repository hoặc tải source code**

2. **Cài đặt dependencies:**

```powershell
pip install -r requirements.txt
```

3. **Cấu hình Firebase:**
   - Đặt file `handover-4.json` (Firebase service account) vào thư mục gốc
   - Hoặc chỉnh sửa đường dẫn trong `config.py`

4. **Cấu hình biến môi trường (optional):**

Tạo file `.env` hoặc set environment variables:

```powershell
$env:FLASK_HOST="127.0.0.1"
$env:FLASK_PORT="9090"
```

5. **Chạy ứng dụng:**

```powershell
python app.py
```

Hoặc với watchdog (auto-reload khi code thay đổi):

```powershell
python VNWB-XX.py
```

6. **Truy cập:**

Mở trình duyệt và truy cập: `http://127.0.0.1:9090`

## 📁 Cấu trúc thư mục

```
webapp_project/
├── app.py                  # Main Flask application
├── config.py               # Configuration settings
├── requirements.txt        # Python dependencies
├── VNWB-XX.py             # Development server with watchdog
│
├── routes/                 # API Routes
│   ├── __init__.py
│   ├── wms.py             # WMS proxy endpoints
│   └── report.py          # Report generation
│
├── utils/                  # Utility modules
│   ├── __init__.py
│   ├── firebase_config.py # Firebase initialization
│   ├── firebase.py        # Firebase wrapper
│   ├── seatalk.py         # SeaTalk integration
│   ├── report.py          # Report generation
│   ├── excel.py           # Excel utilities
│   └── timeutils.py       # Time helpers
│
├── templates/              # HTML templates
│   ├── base.html          # Base template
│   ├── home.html          # Home page
│   ├── scan.html          # Scan Tool
│   ├── handover.html      # Handover Tool
│   └── about.html         # About page
│
└── static/                 # Static assets
    ├── css/
    │   └── main.css       # All styles (unified)
    ├── js/
    │   └── handover.js    # Handover logic
    ├── sounds/            # Audio files
    └── reports/           # Generated reports
```

## 🔧 Cấu hình

### Firebase

Chỉnh sửa trong `config.py`:

```python
FIREBASE_SERVICE_ACCOUNT = "path/to/your/service-account.json"
FIREBASE_DATABASE_URL = "https://your-project.firebaseio.com"
```

### Server Settings

Trong `config.py`:

```python
FLASK_HOST = "0.0.0.0"  # Bind to all interfaces
FLASK_PORT = 9090       # Port number
FLASK_THREADS = 8       # Number of worker threads
```

### SeaTalk Webhook

Để gửi báo cáo qua SeaTalk, đặt biến môi trường trước khi chạy server:

```powershell
$env:SEATALK_WEBHOOK_URL = "https://openapi.seatalk.io/webhook/group/xxxxxx"
```
Hoặc thêm vào hệ thống/CI. Nếu không khai báo, endpoint `/api/report/run` vẫn tạo file Excel và trả link tải về, nhưng sẽ không gửi được lên SeaTalk.

## 📡 API Endpoints

### WMS Proxy

- `GET /wms/info/<vendor_code>` - Lấy thông tin nhân viên
- `POST /wms/info` - Lấy thông tin từ QR code
- `POST /wms/attendance` - Điểm danh (In/Out)
- `POST /wms/activity` - Ghi nhận activity (break, task)

### Report

- `POST /api/report/run` - Tạo và gửi báo cáo

### Pages

- `GET /` - Trang chủ
- `GET /scan` - Scan Tool
- `GET /handover` - Handover Tool
- `GET /about` - About page

## 🎯 Sử dụng

### Scan Tool

1. Chọn Warehouse (VNDB/VNN)
2. Chọn Ca làm việc
3. Scan QR code hoặc nhập WFM
4. Hệ thống tự động ghi nhận và đồng bộ

### Handover Tool

1. Chọn Channel (SPX/GHN)
2. Nhập tên người bàn giao
3. Scan mã vận đơn
4. Click "Report" để xuất báo cáo Excel

## 🔊 Audio Files

Đặt các file âm thanh trong `static/sounds/`:

- `ok.mp3` - Scan thành công
- `error.mp3` - Lỗi
- `cancel.mp3` - Đơn hủy
- `sys_success.mp3` - Hệ thống thành công
- `sys_error.mp3` - Lỗi hệ thống

## 🐛 Troubleshooting

### Firebase connection issues

- Kiểm tra file service account JSON
- Kiểm tra database URL trong config
- Xem log trong terminal

### Port already in use

```powershell
# Windows: Tìm process đang dùng port 9090
netstat -ano | findstr :9090

# Kill process
taskkill /PID <PID> /F
```

### Module not found errors

```powershell
pip install -r requirements.txt --upgrade
```

## 📝 Development

### Auto-reload với Watchdog

```powershell
python VNWB-XX.py
```

Tự động restart khi có thay đổi trong:
- `VNWB-XX.py`
- `Task.py`
- `templates/**`
- `static/**`

### Debug mode

Set trong Flask app:

```python
app.debug = True
```

## 📄 License

Internal tool for VND OB team.

## 👤 Author

**[VND] Hoàng Mập - OB**

---

**Version:** 1.0.0
**Last Updated:** October 2025
"# vaithuhayho"  git init git add README.md git commit -m "first commit" git branch -M main git remote add origin https://github.com/hoangph-385/vaithuhayho.git git push -u origin main
