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

## Phó bản Cỗ Máy Thời Gian

Nút **Tự động vượt phó bản** dùng phiên nhân vật đang mở trong game. Không cần
tạo kịch bản bấm tay. Đường đi: Cỗ Máy Thời Gian → Phó Bản của sự kiện → map có
dấu hai thanh kiếm → ải có dấu hai thanh kiếm → Chiến.

`dungeon_engine.py` nhận diện theo ảnh, giữ đúng hình dạng biểu tượng khi thay đổi
tỉ lệ màn hình. Các mẫu giao diện nằm trong `assets/dungeon/` và chỉ chứa vùng
nút/biểu tượng, không chứa thông tin tài khoản trong ảnh gốc.

- Thắng với số sao nào cũng tiếp tục; không suy ra số ải đã qua từ tổng sao/30.
- Thua thì giữ nguyên màn hình kết quả và dừng.
- `Dừng sau số ải thắng = 0`: chạy đến khi thua. Số lớn hơn 0 giới hạn số trận thắng
  trong lần chạy này. Nút Dừng dùng chung với đăng nhập.
- Chỉ gửi nút Chiến một lần và chờ kết quả; màn hình kết quả đứng yên không được
  tính thêm trận. Màn hình lạ, mất kết nối hoặc quá thời gian sẽ dừng.
- Tự đóng bảng giới thiệu khi vào sự kiện. Nếu có nút Bỏ qua của game, tool dùng
  nút đó một lần để bỏ hoạt ảnh và chờ kết quả. Không cần bật Tự động ải kế trong game.
- Chờ bảng thưởng và vùng chạm đóng kết quả xuất hiện đầy đủ; cũng xử lý được
  trường hợp game tự về map hoặc chuyển thẳng vào trận.
- Khi không thấy ải đang mở, tool tìm trong phần còn lại của map rồi kiểm tra map
  tiếp theo. Nếu không xác nhận được map mới, tool dừng để người dùng kiểm tra.
- Ảnh cuối lần chạy được lưu cục bộ ở `runtime/dungeon_last_screen.png`.

**Đã kiểm tra trực tiếp ngày 18/10/2026:** MuMu Android 12, 1920×1080, phó bản
Kinh Châu Ma Trận. Đã lấy ảnh Thắng (cả 1 sao và 3 sao), Bại và vùng chạm đóng
kết quả từ game thật. Lần kiểm tra cuối gọi tác vụ từ `App.run_dungeon`, chạy đủ
worker, cập nhật ảnh và hàng đợi Tkinter: thắng 3 trận, tự tiếp tục, rồi dừng với
`status=defeat, wins=3`. Ảnh kết thúc giữ nguyên màn hình Bại. Chuyển sang map sau
ải thứ 10 chưa được kiểm tra trực tiếp vì nhân vật đã thua trước mốc đó.

Khi thiếu bộ ảnh kết quả trong bản cài, tool trả về `needs_samples` và không bắt
đầu trận. `work/` chứa biên bản và ảnh chạy thử trên máy, không đưa lên Git.

## Skill trang bị trong Cỗ Máy Thời Gian

- Nút **Trang bị + Cường hóa toàn đội** chạy trên phiên game đang mở, tự duyệt
  tối đa **6 tướng** trong Đội Hình; không đăng nhập lại.
- Bắt đầu ở sảnh sự kiện hoặc màn hình Đội Hình của sự kiện. Từ sảnh, tool nhận
  diện Đội Hình, mở Cường Hóa Trang Bị, chọn Trang Bị Nhanh rồi Cường Hóa Nhanh.
- Tool cuộn về đầu danh sách, chọn lần lượt các chân dung, cuộn tiếp để tìm các
  tướng còn lại. Chỉ xử lý chân dung đầy đủ, bỏ ô dấu + và tránh trùng tướng khi
  cuộn. Mỗi lần chuyển tướng phải xác nhận dấu chọn trên đúng chân dung qua hai ảnh.
- Tướng không còn thay đổi (`no_action`) vẫn chuyển sang tướng tiếp theo. Nếu
  không đọc được màn hình, chọn tướng thất bại hoặc có hộp thoại lạ, dừng toàn lượt
  và giữ các kết quả đã có. Nút Dừng có hiệu lực cả khi chọn/cuộn danh sách.
- Với mỗi tướng, gửi mỗi thao tác một lần. Chỉ xác nhận hộp nâng cấp có đúng nội dung
  **Bạc cường hóa tất cả trang bị**; không tự xác nhận hộp thoại khác.
- Đóng bảng thành tựu cường hóa trang bị nếu xuất hiện; đọc HP/công/hai chỉ số
  phòng ngự ổn định qua hai ảnh trước và sau. Không tăng thì trả `no_action`;
  ảnh lạ, chữ số chưa rõ hoặc quá thời gian thì trả `blocked`, không bấm lặp.
- `TeamEquipmentSkill` điều phối đội hình và gọi `EquipmentSkill` cho từng tướng;
  dùng chung `AdbDevice`, stop event, progress/preview callbacks. Hàm nâng cấp một
  tướng vẫn có thể gọi riêng từ bộ điều phối dungeon sau này.
- Mỗi lượt lưu ảnh trước, sau trang bị, xác nhận Bạc, thành tựu (nếu có), ảnh cuối
  và `result.json` trong một thư mục riêng dưới `runtime/equipment/`.
- Mỗi lượt toàn đội có `result.json` tổng hợp, kết quả từng tướng trong các thư mục
  `hero_01` đến `hero_06`; trạng thái trên GUI hiển thị tiến độ `Tướng n/6`.
- Bộ nhận diện đã kiểm tra trên MuMu 1920×1080; cần kiểm chứng profile khác trước
  khi chạy nhiều instance với độ phân giải khác. Đây là skill riêng, chưa tự gọi
  khi thua phó bản.

**Kiểm tra trực tiếp 19/10/2026:** nhân vật chính được trang bị nhanh, HP
43.310 → 60.828. Tôn Sách cường hóa bốn món từ cấp 122 → 208 bằng Bạc, HP
294.204 → 371.378, công 42.964 → 55.328, lực chiến riêng 928.204 → 1.172.067.
Trong lúc kiểm thử đã bổ sung hộp xác nhận Bạc, bảng thành tựu và đọc chữ số
dính nhau. Ảnh và biên bản chạy thử nằm trong `work/equipment/` và `runtime/`,
được loại khỏi Git.

**Kiểm tra toàn đội 19/10/2026:** đã chạy qua GUI với đủ 6 tướng, tự cuộn danh
sách và không lặp chân dung. Trong quá trình thử đã nâng cấp Tư Mã Ý và Gia Cát
Lượng, xử lý hộp Bạc và bảng thành tựu. Lượt xác minh cuối hoàn tất `processed=6`,
`status=no_action` do các tướng không còn thay đổi sau những lượt nâng cấp trước.
Kết quả tổng hợp và ảnh từng tướng được lưu trong thư mục của lượt chạy.

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
