# Changelog

All notable changes to Vaithuhayho Web Application will be documented in this file.

## [1.0.0] - 2025-10-22

### 🎉 Initial Release

#### Added
- **Backend Refactoring**
  - Tách VNWB-XX.py thành app.py với cấu trúc module rõ ràng
  - Tổ chức routes theo blueprint (wms, report)
  - Tách utils thành modules riêng (firebase, seatalk, excel, report)
  - Config file tập trung

- **Frontend Organization**
  - Tách CSS thành files riêng (main.css, handover.css, scan.css)
  - Tạo base template để tái sử dụng
  - Tổ chức JavaScript thành modules

- **3 Main Routes**
  - `/` - Trang chủ
  - `/scan` - Scan Tool (điểm danh nhân viên)
  - `/handover` - Handover Tool (bàn giao đơn hàng)
  - `/about` - About page

- **Features**
  - Real-time sync với Firebase Realtime Database
  - Export báo cáo Excel tự động
  - Integration với SeaTalk webhook
  - Responsive design cho mobile
  - Sound notifications
  - Pagination cho tables
  - Search functionality

- **API Endpoints**
  - WMS proxy endpoints (info, attendance, activity)
  - Report generation endpoint
  - Health check endpoints

- **Documentation**
  - README.md với hướng dẫn đầy đủ
  - .env.example cho cấu hình
  - Code comments và docstrings
  - CHANGELOG.md

- **Development Tools**
  - requirements.txt
  - .gitignore
  - run.bat script cho Windows
  - Watchdog auto-reload support

#### Changed
- Cấu trúc thư mục được tổ chức lại hoàn toàn
- Code được refactor theo best practices
- Improved error handling và logging

#### Technical Details
- **Backend**: Flask 3.0.0 + Waitress
- **Database**: Firebase Realtime Database
- **Frontend**: HTML5, CSS3, JavaScript ES6+
- **Excel**: openpyxl
- **Python**: 3.8+

---

## Future Plans

### Planned Features
- [ ] User authentication
- [ ] Dashboard với statistics
- [ ] Dark mode
- [ ] Multi-language support
- [ ] API documentation với Swagger
- [ ] Unit tests
- [ ] Docker support
- [ ] CI/CD pipeline

### Under Consideration
- [ ] SQLite local cache
- [ ] Offline mode
- [ ] Push notifications
- [ ] Mobile app
- [ ] Advanced reporting với charts

---

**Note**: Version format follows [Semantic Versioning](https://semver.org/)
