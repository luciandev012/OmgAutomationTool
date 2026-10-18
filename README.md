# OMG Automation Tool

Ứng dụng Windows điều khiển OMG 3Q trên MuMu Player 12 qua ADB.

Mở `Mo-tool-OMG-3Q.cmd`; xem `HUONG-DAN-OMG-3Q.txt` để sử dụng.
Trên máy mới, cài Python 3.11 rồi chạy `Cai-dat.cmd`.

Sau khi tải mã từ Git, chép `account.example.txt` thành `account.txt` và điền tài khoản,
mỗi dòng một tên. Chép `credentials.example.json` thành `credentials.local.json`
rồi điền mật khẩu chung trên máy của bạn. Có thể chép `login_settings.example.json`
thành `login_settings.json` để thiết lập các lựa chọn; mặc định chưa cho phép tích ô điều khoản.

## Luồng đăng nhập

`omg3q_tool.py` cung cấp giao diện Tkinter, kết nối ADB và kịch bản nâng cao.
`login_engine.py` nhận diện ảnh từ `assets/login/`, xử lý ZingID, đổi phiên đã lưu,
chọn server có nhân vật và xác nhận màn hình chính qua hai lần quan sát liên tiếp.
Các lần nhập đều xóa cả hai phía con trỏ vì Ctrl+A không hoạt động trong biểu mẫu game.
Tool không coi phiên đã lưu là thành công trước khi đã gửi thông tin tài khoản được chọn.

Danh sách server đã chơi được game sắp xếp; mặc định chọn nhân vật đầu tiên.
Danh sách rỗng dừng với trạng thái `needs_character`. Màn hình lạ hoặc quá hạn dừng
và ghi ảnh chẩn đoán đã che vùng thông tin đăng nhập trong `runtime/`.
Tool không tự thử lại mật khẩu khi xác thực không thành công.

## Tệp riêng trên máy

- `account.txt`: mỗi dòng một tên đăng nhập, UTF-8, hỗ trợ BOM.
- `credentials.local.json`: thuộc tính `common_password` chứa mật khẩu chung.
- `login_settings.json`: lựa chọn vào game, server đã chơi và quyền tích ô điều khoản.
- `omg3q_steps.json`: kết nối và kịch bản nâng cao; không chứa mật khẩu.

Tài khoản, mật khẩu, lựa chọn cá nhân, môi trường Python và tệp chạy thử được loại khỏi Git.
Mật khẩu được chuyển tới ADB qua stdin, không xuất hiện trong tham số tiến trình Windows.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Đã kiểm tra trực tiếp luồng đăng nhập với OMG 3Q (`com.gs2.omg`) trên MuMu Android 12,
độ phân giải 1920×1080. Bộ nhận diện co ảnh về tỉ lệ tham chiếu 16:9.

`work/` chứa công cụ phát triển và ảnh quan sát cục bộ, không phải thành phần chạy của tool.
