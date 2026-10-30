# OMG Automation Tool

Ứng dụng Windows điều khiển OMG 3Q trên MuMuPlayer / LDPlayer qua ADB.

Mở `Mo-tool-OMG-3Q.cmd`; xem `HUONG-DAN-OMG-3Q.txt` để sử dụng.
Trên máy mới, cài Python 3.11 rồi chạy `Cai-dat.cmd`.

## Phiên bản giả lập và cấu hình test

Thông tin kiểm tra trên máy phát triển ngày **21/10/2026**. Phiên bản ứng dụng
giả lập được đọc từ bản cài trên Windows; MuMuPlayer 6.8.5.0 bên dưới đang dùng
instance **Android 12** (số phiên bản ứng dụng và phiên bản Android là hai thông tin riêng).

| Giả lập đang cài | Phiên bản | Link tải chính thức |
| --- | --- | --- |
| LDPlayer 9 | **9.5.41.0** | [Tải LDPlayer 9 cho Windows](https://res.ldrescdn.com/download/package/LDPlayer9.0.exe?n=LDPlayer9.0_ens_1001_ld.exe) · [Lịch sử phiên bản](https://www.ldplayer.net/other/version-history-and-release-notes.html) |
| MuMuPlayer | **6.8.5.0** | [Tải MuMuPlayer cho Windows](https://www.mumuplayer.com/download/) |

Các link trên là nguồn tải chính thức của hãng, có thể cung cấp bản mới hơn theo
thời điểm tải. Chưa xác minh được link bộ cài cố định đúng build **9.5.41.0** và
**6.8.5.0**; kiểm tra lại phiên bản sau khi cài nếu cần tái lập môi trường test.

**Thiết lập instance hiện tại:** đọc từ cấu hình của instance 0 và 1 của mỗi loại;
đây là giá trị cấu hình, chưa phải kết quả đo hiệu năng hay số máy chạy ổn định.

| Thiết lập mỗi instance | MuMuPlayer (Android 12) | LDPlayer 9 |
| --- | --- | --- |
| CPU cấp cho giả lập | 2 vCPU | 4 vCPU |
| RAM cấp cho giả lập | 4 GB | 4096 MB |
| Độ phân giải | 1920 × 1080 (16:9) | 1920 × 1080 (16:9) |
| DPI | 280 | 280 |
| FPS trong cấu hình | `fps_limit=30`, `fps_limit_low=15`, `fps_limit_real=60` | 60 |

Bộ ảnh nhận diện hiện được kiểm tra ở **1920 × 1080**. Cần kiểm thử lại khi đổi
độ phân giải hoặc phiên bản giả lập.

## Chọn và điều khiển instance MuMu / LDPlayer

Tool tự phát hiện giả lập được cài đặt. Nếu có một loại, tool tự chọn loại đó;
nếu có cả hai, chọn MuMu hoặc LDPlayer ở thanh trên rồi bấm Mở.
Có thể đặt `OMG_MUMU_MANAGER` hoặc `OMG_LDMULTIPLAYER` nếu cài ở đường dẫn riêng.

Hộp thoại hiển thị tên instance trong Multi, bao gồm máy đang tắt.
Tích chọn số lượng tùy ý rồi bấm **Khởi động**: mỗi instance có luồng mở riêng,
khởi động đồng thời, chờ Android và tự mở OMG 3Q. Không tự đăng nhập tài khoản.
Mỗi dòng hiển thị tiến độ / lỗi riêng. Một máy lỗi không dừng các máy khác.

**Dấu tích tự xóa ngay sau khi nhận mỗi lệnh**. Việc bỏ tích không hủy tác vụ đã gửi.
Ví dụ: tích A+B → Khởi động; tích lại A → Tạm dừng, B vẫn chạy;
tích lại A → Tiếp tục. Chọn tất cả / Bỏ chọn tất cả giúp chọn nhanh.
Làm mới nạp lại danh sách và bỏ các dấu tích, không làm mất tác vụ đang chạy.

- **Tạm dừng**: chặn các thao tác tiếp theo của tool trên các máy được tích,
  kể cả tác vụ đăng nhập / phó bản / trang bị sau khi mở game.
- **Tiếp tục**: cho các máy được tích tiếp tục tác vụ đang tạm dừng.
- **Dừng tác vụ**: hủy tác vụ trên các máy được tích; không tắt game hay giả lập.
  Muốn chạy lại cần chủ động gửi lệnh mới. Tiếp tục không khôi phục tác vụ đã hủy.
- Lệnh ADB đã gửi có thể hoàn tất trước khi tạm dừng / dừng có hiệu lực.
- **Đóng**: đóng hộp thoại; tác vụ và trạng thái điều khiển vẫn thuộc tool.
  Mở lại hộp thoại để điều khiển tiếp. Thoát toàn bộ tool sẽ yêu cầu dừng mọi tác vụ.

Ở cửa sổ chính, chọn **Thao tác trên** theo tên máy đã kết nối trước khi chạy
đăng nhập, phó bản, trang bị. Có thể bắt đầu tác vụ trên A rồi chuyển
sang B để chạy tác vụ khác. Mỗi máy chỉ nhận một tác vụ tại một thời điểm;
đổi máy trên giao diện không đổi đích ADB của tác vụ đã chạy. Các thao tác chính
áp dụng cho máy ở ô Thao tác trên; checkbox trong hộp thoại dùng để gửi lệnh điều khiển.

IP/ID chỉ dùng nội bộ cho ADB. Các instance dùng cờ dừng,
trạng thái tạm dừng, đồng hồ và thư mục ảnh chẩn đoán riêng.
Không thay ADB của giả lập hoặc tắt tất cả instance khi dừng một tác vụ.

## Tài khoản Excel và Script A / B / C

Thông tin đăng nhập lấy hoàn toàn từ `account.xlsx`, không dùng danh sách TXT
hay ô mật khẩu chung. Đóng Excel trước khi chạy để tool có thể lưu tệp.
Cấu trúc: `STT | TK | MK | Status | 1 … 15 | Hoàn Thành`;
dòng ngay dưới tài khoản cuối là `Tổng đã hoàn thành`.
Tool đọc số lượng tài khoản theo danh sách hiện có, tự chuyển dòng tổng xuống cuối
và cập nhật công thức khi thêm tài khoản; không cố định số hàng. Tài khoản và mật
khẩu phải được lưu dưới dạng văn bản để giữ nguyên số 0 đầu và ký tự đặc biệt.

Mở và kết nối các instance, chọn tệp rồi bấm một trong ba nút:

- **Script A**: tài khoản chưa hoàn thành ngày 1; thành công ghi `1` ở ngày 1.
- **Script B**: tổng Hoàn Thành từ 1 đến 14, các ngày đã xong liên tiếp;
  thành công ghi `1` ở ngày tiếp theo. Mỗi tài khoản chỉ chạy một ngày trong một lượt.
- **Script C**: tổng Hoàn Thành ít nhất 2; không thay đổi các cột ngày.

Ba nút hiện dùng cùng chu trình thử, chưa triển khai nhiệm vụ riêng từng ngày:
đăng nhập → vào sảnh Cỗ Máy Thời Gian → đóng/mở game → xác nhận thông báo.
Chỉ sau khi thấy thông báo, tool mới lưu Status `V` và số `1` của A/B,
trước khi đóng thông báo để đăng nhập tài khoản kế tiếp.
Chu trình đóng/mở là dấu hiệu hoàn thành của bài thử, không phải xóa phiên ZingID;
bước Đổi Tài Khoản ở lượt tiếp theo vẫn phải xác thực tài khoản Excel mới.

Các instance lấy hàng từ trên xuống, bỏ qua Status không trống, lưu `X` trước
khi đăng nhập. Một bộ ghi Excel chung giữ việc nhận hàng và lưu kết quả tuần tự.
Hoàn Thành và dòng tổng được cập nhật cả công thức lẫn giá trị tính sẵn.
Status chuyển `X` → `V` khi hoàn thành. `V` và `ERR` được giữ nguyên sau khi
tắt instance hoặc kết thúc lượt; tool không tự xóa Status. Hàng lỗi/gián đoạn
giữ `X` nếu chưa xác nhận hoàn thành. Chỉ các hàng có Status trống được nhận tiếp.
Hết tài khoản thì tự tắt instance; tất cả tắt thành công sẽ báo `Đã xong`.
Nếu gặp lỗi, giữ nguyên hàng chưa hoàn thành và báo lỗi, không ghi thành công giả.

## Luồng đăng nhập

`omg3q_tool.py` cung cấp giao diện Tkinter thu gọn và kết nối ADB nội bộ qua instance.
Gói OMG 3Q được dùng cố định; không cần nhập địa chỉ ADB hoặc chọn gói game thủ công.
Cửa sổ tool và hộp điều khiển instance đều có thể kéo thay đổi kích thước.
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

- `account.xlsx`: TK/MK, Status X/V/ERR, các ngày 1–15 và tổng Hoàn Thành.
- `runtime/`: nhật ký test, bản Excel sao lưu và ảnh chẩn đoán.
- `.venv/`: môi trường Python cục bộ.

Các tệp tài khoản, mật khẩu, môi trường và dữ liệu chạy thử được loại khỏi Git.
Mật khẩu được chuyển tới ADB qua stdin, không xuất hiện trong tham số tiến trình Windows.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Đã kiểm tra trực tiếp luồng đăng nhập với OMG 3Q (`com.gs2.omg`) trên MuMu Android 12,
độ phân giải 1920×1080. Bộ nhận diện co ảnh về tỉ lệ tham chiếu 16:9.

`work/` chứa công cụ phát triển và ảnh quan sát cục bộ, không phải thành phần chạy của tool.

## Phiên test đăng nhập Excel trên hai MuMu

Nút **Test Excel · 2 MuMu × 3 lượt** tự mở hai instance MuMu có sẵn.
Instance tới màn hình đăng nhập trước sẽ nhận hàng phù hợp đầu tiên từ trên xuống.
Mỗi instance chạy tối đa ba tài khoản: đóng thông báo, giữ chỗ `X`, đăng nhập,
xác nhận vào sảnh, thoát game, ghi `V` và `1` ở ngày 1, rồi mở lại game để đổi tài khoản.
Sau lượt cuối vẫn mở lại và đóng thông báo; giữ nguyên Status để đối chiếu Excel.

Lần test bỏ timeout phải được chọn riêng bằng cờ `--test-no-timeout`; nút test
thông thường vẫn dùng timeout mặc định. Cờ này chỉ có hiệu lực cho lượt chạy đó.
Các chế độ chạy bình thường giữ timeout cũ. Lệnh ADB riêng lẻ vẫn có giới hạn để
có thể kiểm tra lại khi kết nối bị kẹt. Tạm dừng/Dừng vẫn có hiệu lực theo instance.
Lỗi thực sự không được ghi thành công: hàng đang làm giữ `X` để kiểm tra.

Các lần ghi `X`, `V` và ngày 1 được ghi sau khi lưu Excel thành công vào
`runtime/excel_login_test.jsonl`; nhật ký không chứa tên đăng nhập hoặc mật khẩu.
Bản Excel trước mỗi phiên test được sao lưu trong `runtime/`.
Có thể mở trực tiếp phiên test bằng `.venv\Scripts\pythonw.exe omg3q_tool.py --excel-login-test`.


## Sai thông tin đăng nhập — lỗi 8011

Sau khi gửi đăng nhập, tool chỉ xử lý khi ảnh `invalid_credentials_8011.png`
và `ok_button.png` cùng khớp ngưỡng 0,99 trên một ảnh màn hình.
Tool bấm OK, lưu ngay `ERR` ở Status của hàng đang giữ chỗ, xác nhận lại biểu mẫu,
xóa hai ô TK/MK rồi lấy hàng phù hợp có Status trống gần nhất từ trên xuống.
Các hàng X, V, ERR đều được bỏ qua; không ghi số 1 cho tài khoản sai.
ERR vẫn được giữ khi tắt instance. Nếu lưu ERR thất bại hoặc không xác nhận lại
được biểu mẫu thì chưa chuyển sang tài khoản khác.
Lỗi 8011 không tính là một lượt test thành công và không dừng các instance khác.


## Giao diện hiện tại

Đã tích hợp giao diện thu gọn từ Auto-Clone: bỏ dòng nhập ADB/gói game,
bỏ phần ảnh giả lập và kịch bản chạm thủ công cùng code liên quan.
Giữ Script A/B/C, quản lý instance, phó bản, trang bị và chế độ test Excel.
Cửa sổ chính tự vừa nội dung; hộp instance mặc định 640×300 và cả hai đều co giãn được.
