# Simple Unicode fix for scan.html
$file = "templates\scan.html"
$content = Get-Content $file -Raw -Encoding UTF8

# Basic fixes that work in PowerShell
$content = $content.Replace('NgÃ y', 'Ngày')
$content = $content.Replace('Mã£', 'Mã')
$content = $content.Replace('NhÃ  tháº§u', 'Nhà thầu')
$content = $content.Replace('Giá»›i tÃ­nh', 'Giới tính')
$content = $content.Replace('Nghá»‰ TrÆ°a', 'Nghỉ Trưa')
$content = $content.Replace('VÃ o Ca', 'Vào Ca')
$content = $content.Replace('Nghá»‰ OT', 'Nghỉ OT')
$content = $content.Replace('nhÃ¢n sá»±', 'nhân sự')
$content = $content.Replace('vÃ  TÃªn', 'và Tên')
$content = $content.Replace('TrÆ°a', 'Trưa')
$content = $content.Replace('Há»', 'Họ')
$content = $content.Replace('táº¥t cáº£', 'tất cả')
$content = $content.Replace('bá»™ lá»c', 'bộ lọc')
$content = $content.Replace('Táº£i Excel', 'Tải Excel')
$content = $content.Replace('Lá»c', 'Lọc')
$content = $content.Replace('dá»¯ liá»‡u', 'dữ liệu')
$content = $content.Replace('TÃ¬m kiáº¿m', 'Tìm kiếm')
$content = $content.Replace('XÃ³a', 'Xóa')
$content = $content.Replace('Há»§y', 'Hủy')
$content = $content.Replace('Ãp dá»¥ng', 'Áp dụng')
$content = $content.Replace('dÃ²ng', 'dòng')
$content = $content.Replace('ðŸ"„', '🔄')

# Write back to file
Set-Content $file -Value $content -Encoding UTF8
Write-Host "Basic Unicode fixes applied successfully!"
