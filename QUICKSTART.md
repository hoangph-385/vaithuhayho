# 🚀 Quick Start Guide - Vaithuhayho

Hướng dẫn nhanh để chạy ứng dụng trong 5 phút!

## ⚡ Cách nhanh nhất

### Windows:

1. **Double-click file `run.bat`**
   - Script sẽ tự động:
     - Tạo virtual environment (nếu chưa có)
     - Cài đặt dependencies
     - Chạy server

2. **Mở trình duyệt:**
   ```
   http://127.0.0.1:9090
   ```

✅ Done!

---

## 📋 Cách thủ công

### Bước 1: Cài đặt dependencies

```powershell
pip install -r requirements.txt
```

### Bước 2: Cấu hình Firebase

Đảm bảo file `handover-4.json` có trong thư mục gốc.

### Bước 3: Chạy server

```powershell
python app.py
```

### Bước 4: Truy cập

Mở trình duyệt: `http://127.0.0.1:9090`

---

## 🎯 Sử dụng ngay

### Scan Tool (`/scan`)

1. Chọn Warehouse: VNDB hoặc VNN
2. Chọn Ca làm việc
3. **Scan In**: Scan QR code nhân viên
4. **Scan Task**: Ghi nhận break/task
5. **Scan Out**: Kết thúc ca

### Handover Tool (`/handover`)

1. Chọn Channel: SPX hoặc GHN
2. Nhập tên người bàn giao
3. Scan mã vận đơn (Enter để submit)
4. **Report**: Xuất báo cáo Excel

---

## 🔧 Troubleshooting

### "Port 9090 already in use"

```powershell
# Tìm process
netstat -ano | findstr :9090

# Kill process (thay <PID> bằng số thực tế)
taskkill /PID <PID> /F
```

### "Firebase error"

- Kiểm tra file `handover-4.json` có tồn tại
- Kiểm tra quyền đọc file
- Xem log trong terminal

### "Module not found"

```powershell
pip install -r requirements.txt --upgrade
```

---

## 📱 Access từ Mobile

### Cùng WiFi:

1. Tìm IP của máy tính:
   ```powershell
   ipconfig
   ```
   Tìm "IPv4 Address" (vd: 192.168.1.100)

2. Sửa trong `config.py`:
   ```python
   FLASK_HOST = "0.0.0.0"
   ```

3. Trên mobile, truy cập:
   ```
   http://192.168.1.100:9090
   ```

---

## 💡 Tips

### Development Mode (Auto-reload)

```powershell
python VNWB-XX.py
```

Server sẽ tự động restart khi code thay đổi.

### View Logs

Terminal sẽ hiện log real-time:
- Request/Response
- Firebase operations
- Errors

### Test API

```powershell
# Health check
curl http://127.0.0.1:9090/healthz

# Test WMS
curl http://127.0.0.1:9090/wms/_ping
```

---

## 📚 Next Steps

- Đọc [README.md](README.md) để hiểu chi tiết
- Xem [CHANGELOG.md](CHANGELOG.md) để biết updates
- Check [API Documentation](#) (coming soon)

---

## 🆘 Need Help?

- Check terminal logs
- Đọc error messages
- Contact: [VND] Hoàng Mập - OB

---

**Happy coding! 🎉**
