# Hướng dẫn đổi mật khẩu

## Mật khẩu mặc định
- **Mật khẩu hiện tại**: `vaithuhayho2025`

## Cách đổi mật khẩu mới

### Cách 1: Dùng Python (Khuyến nghị)
```bash
python -c "import hashlib; print(hashlib.sha256(b'mat_khau_moi_cua_ban').hexdigest())"
```

Thay `mat_khau_moi_cua_ban` bằng mật khẩu bạn muốn.

### Cách 2: Dùng PowerShell
```powershell
$password = "mat_khau_moi_cua_ban"
$hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($password))
-join ($hash | ForEach-Object { $_.ToString("x2") })
```

## Cập nhật mật khẩu vào hệ thống

### Option 1: Sửa file `config.py`
Mở file `config.py`, tìm dòng:
```python
AUTH_PASSWORD_HASH = os.getenv("AUTH_PASSWORD_HASH", "...")
```

Thay giá trị trong `"..."` bằng hash mới.

### Option 2: Dùng biến môi trường (Bảo mật hơn)
Tạo file `.env` hoặc set biến môi trường:

**Windows PowerShell:**
```powershell
$env:AUTH_PASSWORD_HASH = "hash_cua_ban"
```

**Linux/Mac:**
```bash
export AUTH_PASSWORD_HASH="hash_cua_ban"
```

## Khởi động lại server
```bash
python app.py
```

## Lưu ý bảo mật
- ⚠️ **KHÔNG** commit file có chứa mật khẩu thật vào Git
- ✅ Sử dụng `.env` file và thêm vào `.gitignore`
- ✅ Đổi `SESSION_SECRET_KEY` thành một chuỗi ngẫu nhiên mạnh
