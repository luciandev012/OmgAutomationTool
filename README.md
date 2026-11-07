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

## Nhiệm vụ hằng ngày ở sảnh chính

Trong nhóm **Sảnh chính · Nhiệm vụ hằng ngày**, bấm **Mở nhiệm vụ hằng ngày**.
Luồng độc lập trong `daily_tasks_skill.py`, dùng đúng thiết bị ADB đang chọn;
không gọi điều hướng hay các kỹ năng của Cỗ Máy Thời Gian.

- Xác nhận sảnh chính bằng hai biểu tượng riêng của sảnh, nhận diện icon cuộn
  giấy Nhiệm vụ ở góc trên bên phải và mở một lần. Vị trí chạm lấy từ ảnh đang
  quan sát, co theo độ phân giải thiết bị.
- Nếu đang ở tab Thành tựu, chuyển sang Nhiệm vụ; nếu đã mở đúng bảng thì xác
  nhận lại và giữ nguyên. Mỗi màn hình được xác nhận qua hai ảnh.
- Bước đầu chỉ điều hướng và dừng ở bảng Nhiệm vụ. Chưa bấm Nhận, Đến, Nhận
  nhanh, rương mốc hay Năng động Điểm danh. Các kỹ năng thực hiện từng nhiệm
  vụ sẽ được thêm theo hướng dẫn tiếp theo của người dùng.
- Ở Cỗ Máy Thời Gian hoặc màn hình chưa nhận diện thì dừng và yêu cầu về sảnh
  chính. Không tự gọi nâng tướng hay vượt phó bản của sự kiện.
- Dùng chung nút Dừng và cơ chế chỉ chạy một thao tác của giao diện. Nếu bảng
  không mở, không bấm lại icon liên tục. Kết quả/ảnh lưu trong
  `runtime/daily_tasks/<lượt chạy>/`.

Đã kiểm tra 13 trường hợp riêng cho luồng mở bảng, gồm tab Thành tựu, đã mở
sẵn, ảnh lóe, bảng không chuyển, màn lạ, dừng/hủy và tỉ lệ ảnh ngang khác nhau.
Đã thử qua luồng worker/GUI thật trên MuMu ở cả ba điểm bắt đầu: sảnh chính,
Thành tựu và bảng đã mở sẵn; không gửi thao tác nhiệm vụ hay thưởng. Biên bản:
`runtime/daily_tasks/gui_verification.json`; ảnh `verified_page.png`.

## Phó bản Cỗ Máy Thời Gian

Nút **Tự động vượt phó bản** dùng phiên nhân vật đang mở trong game. Không cần
tạo kịch bản bấm tay. Đường đi: Cỗ Máy Thời Gian → Phó Bản của sự kiện → map có
dấu hai thanh kiếm → ải có **ba sao tối hoặc dấu kiếm Chiến** → Chiến.

`dungeon_engine.py` nhận diện theo ảnh, giữ đúng hình dạng biểu tượng khi thay đổi
tỉ lệ màn hình. Các mẫu giao diện nằm trong `assets/dungeon/` và chỉ chứa vùng
nút/biểu tượng, không chứa thông tin tài khoản trong ảnh gốc.

- Thắng với số sao nào cũng tiếp tục; không suy ra số ải đã qua từ tổng sao/30.
- Mặc định **Spam khi thua** tắt: thua thì giữ nguyên màn hình kết quả và dừng.
- Bật **Spam khi thua**, đặt **Số lần/ải** (mặc định **100**, số nguyên lớn hơn 0)
  để đánh lại ải vừa thua. Giới hạn này tính **các trận đánh lại sau lần thua đầu
  tiên**: 100 nghĩa là tối đa 1 trận ban đầu + 100 trận đánh lại ở mỗi ải.
  Thắng thì sang ải tiếp theo và đặt lại bộ đếm của ải; tổng số trận đánh lại vẫn
  được ghi trong kết quả. Chỉ tính lượt khi xác nhận có trận hoặc kết quả mới.
- Nếu trận đánh lại cuối cùng vẫn thua, tool dừng ở kết quả **Bại** và hiện hộp
  thoại **Đã hết lượt spam**. Chọn **Có** để chạy một lượt mới với số lần đã đặt;
  chọn **Không** để dừng. Tool không tự mở lượt mới khi chưa có lựa chọn của bạn.
  Cũng có thể bấm lại **Tự động vượt phó bản** sau đó để bắt đầu lượt mới.
- Sau khi thua, tool đóng kết quả, chọn lại ải bằng sao tối hoặc dấu kiếm tại vị trí đang mở trên
  cùng map; không dò sang map khác. Nếu có bảng Chiến thì đối chiếu tên ải với
  trận trước. Hỗ trợ game vào trận ngay khi chọn ải. Vị trí ải thay đổi, tên không
  khớp hoặc không xác nhận được đường quay lại sẽ dừng với `retry_unverified`.
- Nếu cả sao tối và dấu kiếm bị khuất khi đánh lại, quét tới hai mép để tìm lại, giữ nguyên
  cùng chương. Sau khi kéo, kiểm tra tên map giữ nguyên và nhận diện dấu hiệu ải ở vị
  trí mới qua hai ảnh liên tiếp; vị trí màn hình được phép đổi vì map đã cuộn.
  Nếu không thực hiện kéo, kiểm tra vị trí cũ vẫn áp dụng. Nhánh này không bấm
  Chương kế, không tiêu lượt Spam chỉ vì kéo map hoặc nhìn thấy sao.
- `Dừng sau số ải thắng = 0`: không giới hạn số trận thắng. Số lớn hơn 0 giới hạn
  số trận thắng trong lần chạy này, kể cả khi bật Spam. Nút Dừng dùng chung với
  đăng nhập và có thể dừng giữa lượt spam.
- Chỉ gửi nút Chiến một lần và chờ kết quả; màn hình kết quả đứng yên không được
  tính thêm trận. Màn hình lạ, mất kết nối hoặc quá thời gian sẽ dừng.
- Tự đóng bảng giới thiệu khi vào sự kiện. Trong trận, nhận diện **Auto đang bật**
  (nền xanh) hoặc **đang tắt** (nền tối) qua hai ảnh liên tiếp. Chỉ bấm Auto khi
  đang tắt rồi chờ xác nhận bật; không bấm lại khi Auto đã bật. Nếu Auto bị tắt
  trong cùng trận, tool kiểm tra và bật lại, với giới hạn bảo vệ 3 lần/trận.
- Sau khi xác nhận Auto bật, bấm **Bỏ qua** khi nút khả dụng, tối đa một lần mỗi
  trận; sau đó vẫn đọc kết quả Thắng/Bại. Mỗi trận mới kiểm tra lại Auto và được
  bấm Bỏ qua một lần mới. Không cần bật Tự động ải kế trong game.
- Nếu chưa nhận diện/xác nhận Auto bật trong 8 giây khi màn trận đã hiện, dừng
  với `auto_unverified`; không đoán trạng thái hoặc bấm lặp nút bật/tắt. Sau khi
  đã xác nhận Auto, các pha chuyển cảnh mất nút tạm thời vẫn chờ kết quả theo
  giới hạn trận. Không thao tác Auto/Bỏ qua trên bảng kết quả hoặc ngoài trận.
- Chờ bảng thưởng và vùng chạm đóng kết quả xuất hiện đầy đủ; cũng xử lý được
  trường hợp game tự về map hoặc chuyển thẳng vào trận.
- Sau ải 10, nhận diện **Chương kế** trên map và bấm một lần để sang chương mới.
  Không cần đủ 30/30 sao. Tool chờ tên map thay đổi ổn định rồi chọn dấu hiệu của
  ải đầu tiên; cũng hỗ trợ trường hợp nút đưa về danh sách map. Có thể chạy tool
  ngay trên map đã hoàn thành đang hiện Chương kế. Nếu map cũ vẫn đứng yên sau
  khi bấm, tool dừng theo thời gian chờ, không bấm lặp hoặc chọn lại boss cũ.
- Ở ải 1, dùng sao tối dưới thanh tên map hoặc phần đầu kiếm còn lộ để chọn nhân vật.
- Khi không thấy ải đang mở, tool chờ ảnh mới và quét map theo cả hai chiều.
  Không dùng số lần kéo cố định để kết luận đã quét hết: so khớp các điểm trên
  cảnh map để đo dịch chuyển thật sau mỗi lần kéo. Còn dịch chuyển thì tiếp tục
  cùng chiều; ba điểm kéo khác nhau đều không di chuyển mới xác nhận tới mép.
  Sau mép cuối, quét ngược tới mép đầu nếu vẫn chưa tìm được ải, rồi quay lại
  kiểm tra phía phải lần cuối. Lượt quét không tìm được ải kết thúc ở bên phải,
  không kéo ngược về đầu map rồi hiện popup như bản trước.
  Ưu tiên kéo map sang trái để làm lộ hàng sao bị che ở phía bên phải. Sau mỗi
  lần kéo, chụp lại và xác nhận sao tối/dấu kiếm ổn định qua hai ảnh trước khi chọn ải.
  Ảnh từng vùng được lưu ở `runtime/dungeon_scan/scan_XX.png`.
  Không suy ra đã hoàn thành chương từ việc không thấy sao tối hoặc dấu kiếm; chỉ chuyển chương khi
  xác nhận nút **Chương kế**. Nếu vẫn không tìm thấy, giữ nguyên map để kiểm tra.
- Với hàng sao bị cắt ở mép trên (thường gặp ở boss ải 10), nhận diện phần sao
  còn nhìn thấy với ngưỡng chặt, khôi phục vị trí đầy đủ và xác nhận qua hai
  ảnh liên tiếp trước khi chọn nhân vật. Ảnh lóe đơn lẻ, ứng viên đổi vị trí hoặc
  nền bị làm tối phía sau bảng thông báo không được dùng để chọn ải.
- Ảnh cuối lần chạy được lưu cục bộ ở `runtime/dungeon_last_screen.png`.
- Kết hợp **ba sao tối hoặc dấu kiếm Chiến** để tìm ải đang mở. Sao tối rõ thì
  dùng sao; khi nền khiến sao khó nhận, dấu kiếm là tín hiệu độc lập để tiếp tục.
  Khôi phục mẫu kiếm đầy đủ, các pha hoạt ảnh, so phần kiếm bỏ nền và kiếm bị
  cắt ở mép trên/che bởi tiêu đề. Cả hai cách đều cần vị trí ổn định qua hai ảnh.
  Nếu cả hai cùng rõ nhưng chỉ hai nhân vật khác nhau thì chờ ảnh mới, không
  chọn tùy ý. Không đọc các dấu hiệu trên nền bị làm tối sau bảng thông báo.
  Cách chọn map trên danh sách chương giữ nguyên.
- Kết quả dừng và thông báo popup được lưu ở `runtime/dungeon_last_result.json`;
  nhật ký chiều kéo, dịch chuyển, hai mép, lượt quay lại và tên ảnh tương ứng ở
  `runtime/dungeon_scan/latest.json`, phục vụ đối chiếu đúng lần chạy.

**Khôi phục nhận diện kết hợp (25/10/2026):** áp dụng cho cả chọn ải mới và
đánh lại sau thua. Kiểm thử bao gồm sao không đọc được nhưng kiếm còn rõ,
kiếm bị cắt, kiếm phát sáng, hai nguồn chỉ vị trí khác nhau, nhận một ảnh lóe
và đánh lại có giới hạn. Các cải tiến sao trên nền phức tạp và Chương kế trên
nền sáng vẫn giữ nguyên.
Toàn bộ **279 kiểm thử đạt**, gồm 97 cho vượt ải. Lượt thử GUI cố tình tắt
nhận diện sao trong riêng bộ kiểm tra đã xác nhận chọn ải bằng dấu kiếm và
bấm Chiến; sau đó game quay về thông báo trước đăng nhập nên chưa xác nhận
kết quả trận và đã dừng lượt thử, không ghi nhận thắng. Ảnh tại
`runtime/dungeon_combined_sword_fallback/live.png`.

Các mục dưới đây là nhật ký các phiên bản trước, gồm giai đoạn chỉ dùng sao;
quy tắc hiện tại là kết hợp sao tối và dấu kiếm như mô tả ở trên.

**Chuyển sang chỉ dùng ba sao tối (25/10/2026):** bỏ toàn bộ nhánh so khớp dấu
kiếm đầy đủ, có mặt nạ, bị cắt và đầu lưỡi kiếm khi chọn ải/chọn lại sau thua.
Bổ sung mẫu sao trên nền xanh, đêm và cát; luôn xác nhận qua hai ảnh. Kiểm thử
bao gồm kiếm vẫn rõ nhưng sao thiếu, đã có sao vàng hoặc nhiều hàng sao tối;
những trường hợp này không được chọn chỉ nhờ dấu kiếm.
Đã chạy qua GUI trên MuMu, thắng liên tiếp hai ải bằng nhận diện sao tối và
dừng đúng giới hạn thử hai ải; Auto/Bỏ qua hoạt động ở cả hai trận. Báo cáo:
`runtime/dungeon_stars_only/gui_result.json`. Toàn bộ **270 kiểm thử đạt**,
gồm 88 trường hợp cho vượt ải.

**Sửa bỏ sót sao trên nền khác (25/10/2026):** đã tái hiện popup tại Quân
Hoàng Cái 3 của **Trí Toán Hoa Dung–Thượng** (8/30 sao), rồi kiểm tra cả Quân
Hoàng Cái 4 trên nền nâu. Biên ảnh mẫu cũ bao gồm chi tiết nền nên loại nhầm
hàng ba sao tối dù còn hiện rõ. Bổ sung mẫu hình học chỉ có đường viền ba sao,
độc lập với nền; kiểm tra phần tô sao tối, đều màu để loại nét nhân vật có thể
trùng hình. Giữ loại sao vàng, nhiều ứng viên và xác nhận hai ảnh; không thêm
mẫu nền riêng cho từng ải, không dùng lại dấu kiếm. Cho phép một sao có nền
chi tiết hiện xuyên qua (Quân Hoàng Cái 6 nằm trên tượng đá); cả ba vẫn phải
thỏa điều kiện sao tối. Ba ảnh thực tế được giữ trong
`tests/fixtures/dungeon/hoang_cai_*_stars.png`. Kiểm tra nền quanh sao thay vì
chỉ hai góc trên; cách lấy vùng nền rộng hơn cần mức khớp hình chặt hơn để
không nhận nhầm nét nhân vật. Có ảnh Chu Thái nằm trước hàng rào để hồi quy.
Nút Chương kế được so phần chữ/viền, bỏ ảnh nền phía sau và kiểm tra độ sáng
trên chính phần chữ để loại bảng thông báo làm tối map.

Thử trực tiếp từ vị trí bị kẹt đã thắng **7 ải còn lại**, hoàn thành map ở
**26/30 sao** và bấm Chương kế sang map mới, rồi chủ động dừng trước trận mới.
Các lượt hiệu chỉnh được giữ riêng ở `runtime/dungeon_hoang_cai_fix*`;
biên bản tổng `runtime/dungeon_hoang_cai_fix_verified.json` phân biệt các lần
dừng trung gian với bước chuyển chương đã xác nhận. Bộ kiểm thử cuối có
**277 trường hợp đạt**, trong đó 95 cho vượt ải.

**Sửa popup dừng ở đầu map ngày 25/10/2026:** tái hiện tại **Xích Bích Chiến**,
10/30 sao. Ảnh ở phía phải cho thấy Đào Vong Binh 4 còn ba sao tối, trong khi
gần như toàn bộ dấu kiếm nằm ngoài mép trên. Popup "đã xác nhận quét tới cả hai
mép nhưng chưa nhận được dấu Chiến" phản ánh lỗi nhận diện, không phải hoàn
thành map. Chuyển hàng ba sao tối thành dấu hiệu chính; bổ sung so khớp biên sao
và kiểm tra độ tối theo vùng nền để chịu hiệu ứng lửa, không dùng ngưỡng RGB tối
cố định. Bộ quét có thêm lượt cuối quay về mép phải sau khi xác nhận hai mép.
Đã kiểm tra thật lượt quét ba chặng trên map này: dịch chuyển khoảng +316.8 và
-316.8 pixel tham chiếu, kết thúc bên phải sau 11 thao tác kéo. Ảnh và biên bản:
`runtime/dungeon_coverage/coverage.json`; chuỗi thử GUI:
`runtime/dungeon_popup_fix/`. Có ảnh hồi quy khi kiếm gần hết ra ngoài ảnh, hàng
sao chịu lửa, nhiều hàng sao tối cùng hiện và một sao đã chuyển vàng.

Lượt thử trực tiếp thắng tiếp 5 ải tới Trương Liêu, rồi phát hiện Tào Tháo có
cả dấu kiếm và phần trên hàng sao nằm ngoài ảnh. Đã bổ sung so khớp phần sao
còn nhìn thấy, chỉ cho phép tại sát mép trên; giữ kiểm tra cả ba sao tối và hai
ảnh ổn định. Lượt thử tiếp theo nhận đúng Tào Tháo, thắng, bấm Chương kế và
chuyển sang **Trí Toán Hoa Dung–Thượng**, rồi chủ động dừng trước khi đánh map
mới. Báo cáo/ảnh: `runtime/dungeon_clipped_stars/gui_result.json` và `result.png`.
Bộ kiểm thử sau thay đổi: **268 trường hợp đạt**, trong đó 86 cho vượt ải.

**Sửa quét chưa hết map ngày 25/10/2026:** thay giới hạn 3/6 lần kéo của bản trước
bằng `MapSweep`, đo dịch chuyển ngang bằng điểm đặc trưng ORB của cảnh map (loại
vùng giao diện cố định). Dùng ba đường kéo khác nhau khi ảnh không đổi để tránh
nhầm một lần kéo trúng nhân vật với việc đã tới mép. Bộ quét hỗ trợ cả nhánh
thường và Spam. Chỉ nút **Chương kế** xác nhận đã hoàn thành map; tổng sao không
phải số ải. Nếu đã xác nhận hai mép mà vẫn không đọc được dấu, báo lỗi nhận diện,
giữ nguyên chương. Nếu ảnh không đủ bằng chứng và chạm ngưỡng bảo vệ 60 lần,
báo `scan_unverified` (chưa xác nhận kéo hết), không báo map hoàn thành.
Thêm so khớp có mặt nạ chỉ giữ hình kiếm, bỏ nền cảnh, để xử lý dấu cùng hình
nhưng nằm trên nền khác mà không hạ ngưỡng chung. Đã xác nhận thật cả hai mép
map hiện tại trong 8 thao tác kéo, với dịch chuyển đo được khoảng +436 và +414
pixel tham chiếu khi quét ngược; báo cáo `runtime/dungeon_coverage/coverage.json`.
Bộ kiểm thử **264 trường hợp** đạt, gồm map cần 11 lần kéo mới thấy ải, xác nhận
hai mép qua ba đường kéo, không suy ra mép khi ảnh thiếu đặc trưng, đo dịch chuyển
thật, nhận dấu kiếm trên nền khác, và các nhánh Spam/Chương kế đã có.
Sau kiểm tra hai mép, chạy GUI từ đầu map **Đoạt Mồi Lửa-Thượng**: tự kéo hai lần,
tìm Mạnh Hoạch, thắng rồi tự chọn **Chúc Dung (ải 10)**. Trận Chúc Dung thua nên
lượt thử tắt Spam dừng đúng với `status=defeat`, `wins=1`, `battle_skips=2`;
không còn dừng vì `no_frontier` ở lượt này. Báo cáo và ảnh của cả chuỗi:
`runtime/dungeon_full_route/gui_result.json`, `revealed_selected.png`, `result.png`.

**Bổ sung kéo làm lộ dấu Chiến ngày 25/10/2026:** ảnh thực tế tại **Đoạt Mồi
Lửa-Thượng**, 13/30 sao, cho thấy dấu của **Sa Ma Kha** nằm ngoài cạnh phải.
Kéo sang trái làm lộ dấu. Bổ sung mẫu dấu kiếm bắt chéo, tách hai lưỡi và phát
sáng trên nền map sáng; không giảm ngưỡng nhận diện chung. Chuẩn hóa tâm dấu
giữa các pha để chọn cùng nhân vật. Phần nhận diện tên map loại nền cảnh bên
ngoài khung tên, tránh báo sai đổi map khi kéo. Cả vòng vượt ải và vòng Spam
đều hỗ trợ kéo để tìm lại dấu, với giới hạn và xác nhận trên ảnh mới.
Đã chạy worker GUI thật từ đúng màn hình bị khuất: tự kéo trái, xác nhận dấu,
chọn Sa Ma Kha, xác nhận Auto, Bỏ qua và thắng. Lượt thử dừng theo giới hạn 1
trận thắng (`status=limit`, `wins=1`, `battle_skips=1`). Báo cáo và ảnh:
`runtime/dungeon_pan/gui_result.json`, `before_pan.png`, `revealed_selected.png`,
`result.png`. Bộ kiểm thử **259 trường hợp** chạy thành công; có kiểm tra các
pha hoạt ảnh, quét trái, dấu xuất hiện một ảnh đơn lẻ, nút Dừng trước kéo, vị trí
đổi sau kéo trong cùng map và chặn đánh lại nếu tên map đổi.

**Sửa bỏ sót ải 10 ngày 25/10/2026:** ảnh lỗi thực tế tại
**Thất Tinh Đàn Phong-Trung**, boss **Tư Mã Ý**, cho thấy phần trên dấu kiếm nằm
ngoài ảnh. Bộ nhận diện nay so phần dưới còn thấy với mẫu gốc ở mép trên, khôi
phục tâm biểu tượng rồi xác nhận vị trí qua hai ảnh liên tiếp. Giữ ngưỡng chặt
và kiểm tra độ sáng; không hạ ngưỡng nhận diện toàn màn hình. Kết quả nhận diện
được tái sử dụng trong cùng ảnh để tránh tính lặp. Quét thiếu dấu kiếm theo hai
chiều, lưu ảnh từng vùng; bỏ suy luận “không thấy dấu kiếm = đã xong map”.
Đã chạy từ GUI thật trên MuMu 1920×1080: nhận đúng boss ải 10, chạm vào nhân vật,
xác nhận Auto đang bật, Bỏ qua một lần và đọc Bại. Lượt thử tắt Spam nên dừng
đúng tại Bại (`status=defeat`, `wins=0`, `battle_skips=1`). Không còn dừng
`no_frontier` ở màn lỗi này. Ảnh/báo cáo: `runtime/dungeon_stage10/`.
**254 kiểm thử** chạy thành công; có ảnh lỗi thật, dấu kiếm bị cắt ở nhiều độ
sâu, nền tối, nhiễu, vị trí lóe đơn lẻ/đổi chỗ, quét ngược và giữ nguyên map chưa
hoàn thành. Nhánh Spam vẫn kiểm tra đúng vị trí boss trước khi đánh lại.

**Cập nhật Chương kế ngày 24/10/2026:** bổ sung mẫu `next_chapter.png` và mẫu
lưỡi kiếm bị che `stage_frontier_tip.png`. Chỉ bấm Chương kế trên màn map, sau
hai lần nhận diện; chờ tên map mới ổn định hoặc danh sách chương trước khi tiếp
tục. Không đếm chuyển chương thành trận thắng. Giới hạn số ải thắng, Auto/Bỏ qua
và ngân sách Spam vẫn áp dụng; nhánh đánh lại sau khi thua không chuyển chương.
Đã kiểm tra trực tiếp nút Chương kế của **Bắc Quân Dụng Võ-Hạ (105)** chuyển
sang **Thất Tinh Đàn Phong-Thượng (106)**. Lượt đầu phát hiện dấu kiếm của ải 1
bị thanh tên che; sau khi bổ sung mẫu, chạy GUI vào **Y Quan 1**, xác nhận Auto,
bấm Bỏ qua và thắng, dừng theo giới hạn thử 1 trận thắng (`wins=1`,
`battle_skips=1`). Ảnh và báo cáo GUI: `runtime/dungeon_chapter/`.
Bộ kiểm thử **248 trường hợp** chạy thành công, bao gồm ải 10 → Chương kế →
ải đầu map mới, cả hai chế độ Spam, nút đứng yên, tiêu đề map chưa đổi, lớp kết
quả che nút, giới hạn số trận thắng và dấu kiếm bị che một phần.

**Cập nhật Spam ngày 24/10/2026:** `DungeonEngine.run(spam=False, spam_limit=100)`;
`DungeonResult` bổ sung `retries` (tổng số trận đánh lại trong lượt) và
`stage_retries` (số trận đánh lại của ải hiện tại). Khi hết ngân sách, trả về
`spam_limit`; GUI thông báo và chỉ khởi động lượt tiếp theo khi người dùng chọn Có.
Đã thử qua worker/ảnh xem trước/hàng đợi GUI thật trên MuMu 1920×1080, tại
**Bắc Quân Dụng Võ-Hạ**, đánh lại **Hạ Hầu Đôn** 2 lần bằng chế độ vào trận trực
tiếp khi chọn ải. Cả 2 trận xác nhận Auto có sẵn và bấm Bỏ qua, cùng thua rồi dừng
đúng `spam_limit`, `retries=2`, `stage_retries=2`, `battle_skips=2`.
Hộp thoại được kiểm tra với lựa chọn Không; lựa chọn Có, đặt lại bộ đếm khi thắng
và ngưỡng mặc định 100 được kiểm tra bằng mô phỏng. Không chạy 100 trận trên
tài khoản để thử giới hạn. Báo cáo và ảnh: `runtime/dungeon_spam/gui_result.json`,
`runtime/dungeon_spam/result.png`. Bộ đếm khởi động lại từ 0 mỗi lượt, không lưu
để khôi phục sau khi đóng tool. Bổ sung mẫu chữ Cỗ Máy Thời Gian và dấu kiếm map
từ giao diện hiện tại; đã đối chiếu nhận diện trên ảnh thật của lượt thử.

**Đã kiểm tra trực tiếp ngày 18/10/2026:** MuMu Android 12, 1920×1080, phó bản
Kinh Châu Ma Trận. Đã lấy ảnh Thắng (cả 1 sao và 3 sao), Bại và vùng chạm đóng
kết quả từ game thật. Lần kiểm tra cuối gọi tác vụ từ `App.run_dungeon`, chạy đủ
worker, cập nhật ảnh và hàng đợi Tkinter: thắng 3 trận, tự tiếp tục, rồi dừng với
`status=defeat, wins=3`. Ảnh kết thúc giữ nguyên màn hình Bại. Chuyển sang map sau
ải thứ 10 chưa được kiểm tra trực tiếp vì nhân vật đã thua trước mốc đó.

Khi thiếu bộ ảnh kết quả trong bản cài, tool trả về `needs_samples` và không bắt
đầu trận. `work/` chứa biên bản và ảnh chạy thử trên máy, không đưa lên Git.

**Cập nhật Auto + Bỏ qua ngày 23/10/2026:** thêm mẫu Auto bật/tắt và mẫu Bỏ qua
từ giao diện hiện tại, kiểm tra màu để phân biệt hai nền nút dù cùng chữ Auto.
Thiếu mẫu điều khiển trận cũng trả về `needs_samples` trước khi bấm Chiến.
`DungeonResult` có thêm `auto_activations` và `battle_skips` để ghi số thao tác.
Đã thử qua GUI thật trên MuMu 1920×1080: Auto có sẵn ở trạng thái bật nên không
bị bấm lại (`auto_activations=0`), Bỏ qua đúng một lần (`battle_skips=1`), nhận
Bại và dừng với `wins=0`. Ảnh và báo cáo nằm ở
`runtime/dungeon_controls/` (`battle_auto_on.png`, `result.png`, `gui_result.json`).
Nhánh bật Auto từ trạng thái tắt được kiểm tra bằng ảnh thật và mô phỏng; chưa
thử chuyển Auto tắt→bật trực tiếp trong lượt game này. Bộ kiểm thử hiện đạt
**183 trường hợp**, gồm bật trước Bỏ qua, Auto đã bật, xác nhận chậm/không rõ,
kiểm tra lại mỗi trận, nút Bỏ qua xuất hiện muộn và tiếp tục thắng/dừng khi thua.

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

## Skill tiến cấp tướng trong Cỗ Máy Thời Gian

Trong khung **Cỗ Máy Thời Gian · Tiến cấp tướng**, chọn:

- **Tướng đang chọn**: mở Đội Hình và chọn chân dung trước khi chạy. Tool ghi
  nhớ tướng, xác minh lại sảnh sự kiện rồi chọn lại đúng chân dung. Nếu đang ở
  trang chi tiết Tướng, quay về Đội Hình trước; game có thể đổi tướng đang chọn
  khi thoát trang chi tiết.
- **Toàn đội tối đa 6 tướng**: cuộn về đầu, duyệt các tướng đang có, bỏ ô trống
  dấu cộng và không lặp chân dung. Đội có ít hơn 6 tướng sẽ kết thúc ở cuối danh sách.
- **Tự dừng khi không thể**: tiến cấp đến khi game báo giới hạn, thiếu Tiến cấp
  đơn, thiếu mảnh tướng hoặc chưa đủ điều kiện. Trong chế độ toàn đội, các lý do
  này chỉ kết thúc tướng hiện tại rồi chuyển sang tướng tiếp theo.
- **Dừng ở bậc mục tiêu**: nhập bậc tuyệt đối do người dùng quyết định, ví dụ
  nhập `10` để dừng ở +10. Tướng đã đạt hoặc vượt mốc được bỏ qua. Nhập `0`
  có thể dùng để kiểm tra điều hướng/đọc bậc mà không tiến cấp.

Skill xác minh dấu hiệu riêng của sảnh Cỗ Máy Thời Gian trước khi chạy; không
tiến cấp đội hình ở sảnh thường. Với một tướng, tool mở ảnh tướng → tab Tiến cấp
→ đọc bậc, điều kiện và chi phí → gửi một lần Tiến cấp → xác nhận bậc tăng qua
hai ảnh trước khi tiếp tục. Chủ tướng chỉ cần Tiến cấp đơn; tướng khác kiểm tra
thêm mảnh tướng. Chưa xác nhận được kết quả, hộp thoại lạ, OCR không rõ hoặc quá
thời gian sẽ dừng cả lượt, không bấm lại, không tự mua tài nguyên hay dùng Tăng Nhanh.

`AdvanceSkill.run(target_rank=None)` và
`TeamAdvanceSkill.run(target_rank=None, max_heroes=6)` có thể gọi độc lập từ bộ
điều phối sau này. Mỗi skill dùng thiết bị ADB cụ thể, tín hiệu Dừng và các
callback tiến độ/ảnh; chưa tự ghép vào vòng chạy phó bản. Có giới hạn bảo vệ
100 lần tiến cấp mỗi tướng trong một lượt, tách biệt với giới hạn do game báo.

**Nhận diện số:** dùng Windows OCR tiếng Anh `en-US` có sẵn trên máy thử,
không gửi ảnh lên dịch vụ ngoài. Cần Windows PowerShell và bộ nhận diện này;
thiếu OCR thì skill dừng và báo lỗi. Bậc +10 bị OCR đọc thành chữ được xác minh
bằng mẫu ảnh số +10 riêng. Đã kiểm tra MuMu 1920×1080; chưa chứng nhận các bố cục
hoặc độ phân giải giả lập khác. Lượt OCR phụ thu nhỏ ảnh để đọc số mảnh màu đỏ.

Kết quả trước/sau mỗi bước, bậc đầu/cuối, số lần thành công, tài nguyên và lý do
dừng được lưu dưới `runtime/advance/<lượt>/`. Lượt toàn đội có báo cáo tổng và
thư mục riêng cho từng tướng. Nút Dừng của tool có hiệu lực trong skill.

**Kiểm tra trực tiếp 21/10/2026:** chủ tướng sự kiện +10 được nhận diện là đã đạt
cấp tối đa dù nút Tiến cấp vẫn màu cam. Tôn Sách +7 được chọn lại đúng sau khi
xác minh sự kiện; tool đọc 159.860/12.000 Tiến cấp đơn, 265/640 mảnh và tự dừng
vì thiếu mảnh. Màn hình cũng yêu cầu Lv60. Chưa xác minh trực tiếp lần tăng bậc
thành công trên tài khoản này; điều kiện dừng sau tăng bậc được kiểm tra bằng
mô phỏng. Ảnh và báo cáo thử nghiệm ở `runtime/advance/`, được loại khỏi Git.

Lượt qua GUI đã hoàn tất cả hai chế độ trên đúng 5 tướng hiện có (giới hạn tối đa
6), không chọn ô trống. Lượt mốc +0 không tiến cấp; lượt tự dừng báo chủ tướng
tối đa, bốn tướng +7 thiếu mảnh (265/640, 100/640, 105/640, 265/640). Kết quả ở
`team_gui_verified.json` và `team_passive_verified.json`. Đã bổ sung kiểm thử ô
dấu cộng sáng/tối/ẩn và chờ danh sách ổn định sau cuộn. Toàn bộ **89 kiểm thử**
đạt, gồm kiểm thử cũ và tiến cấp mới.

## Skill tăng cấp tướng trong Cỗ Máy Thời Gian

Khung **Tăng cấp tướng** có cùng lựa chọn với Tiến cấp:

- **Tướng đang chọn** hoặc **Toàn đội tối đa 6 tướng**.
- **Tự dừng khi không thể** hoặc **Dừng ở cấp mục tiêu** do người dùng nhập.
  Cấp mục tiêu là cấp tuyệt đối; tướng đã bằng hoặc cao hơn mốc được bỏ qua.
  Mốc `0` dùng để kiểm tra điều hướng mà không dùng sách.
- Với chế độ một tướng, chọn chân dung trong Đội Hình trước khi chạy. Nếu đang
  ở trang chi tiết Tướng, quay về Đội Hình trước.
- Chủ tướng không có tab tăng cấp bằng sách EXP trong bố cục đã kiểm tra, nên
  được bỏ qua; các tướng khác mở ảnh tướng → tab **Tăng cấp** → nút **Tăng cấp**.

Tool ưu tiên nút **5 lần** trong chế độ tự dừng, hoặc khi còn ít nhất 5 cấp
đến mốc người dùng đặt. Khi chỉ còn 1–4 cấp đến mốc, tool dùng nút **Tăng cấp**
từng lần để không vượt mốc. Nút một lần cũng được dùng khi bộ điều phối cung
cấp giới hạn cấp còn dưới 5. Một thao tác có thể tiêu nhiều sách EXP.
Sau mỗi lượt phải xác nhận cấp/EXP tăng và số sách giảm ổn định qua hai ảnh
trước khi tiếp tục. Lượt 5 lần được chấp nhận tăng tối đa 5 cấp; tool chờ các
trạng thái trung gian ổn định. Nếu lượt dừng sớm, ghi nhận số cấp thực tăng và
dừng tướng này, không gửi lại lượt 5 lần. Tool ghi
lại số sách đã dùng theo từng loại. Sách được đọc bằng bộ chữ số hiện có; số cấp
màu vàng dùng thêm mẫu quan sát thực tế khi Windows OCR bỏ sót.

Hết sách, nút không khả dụng hoặc nhận diện được thông báo giới hạn thì dừng
tướng hiện tại. Màn hình không rõ, hộp thoại lạ hay không xác nhận được thay đổi
sau một lần bấm sẽ dừng cả lượt với `blocked`, giữ ảnh và không gửi lại lệnh.
Không tự bấm dấu cộng lấy sách, mua tài nguyên, thay/gỡ tướng hoặc dùng kim nguyên.
Giới hạn bảo vệ là 300 thao tác đã xác nhận cho mỗi tướng trong một lượt.

`LevelSkill.run(target_level=None)` và
`TeamLevelSkill.run(target_level=None, max_heroes=6)` là skill độc lập, dùng thiết
bị ADB cụ thể, tín hiệu Dừng và callback tiến độ/ảnh như các skill khác. Điều
hướng giữ tướng và quay về Đội Hình được dùng chung với Tiến cấp trong
`hero_navigation.py`. Skill xác minh đúng sảnh sự kiện trước khi dùng tài nguyên;
chưa được tự ghép vào vòng chạy phó bản.

Kết quả từng lượt nằm trong `runtime/level/`: cấp đầu/cuối, số cấp tăng, số thao
tác đã xác nhận (tách `batch_actions` và `single_actions`), số sách dùng theo
từng loại, ảnh trước/sau và `result.json`.
Bản toàn đội có báo cáo tổng và thư mục riêng cho mỗi tướng. Cần Windows OCR
`en-US` như Tiến cấp; hiện kiểm tra trên MuMu 1920×1080.

**Kiểm tra 21/10/2026:** Tôn Sách đã tăng thật 50 → 51, dùng 3 sách, dừng đúng mốc.
Các điều kiện thiếu sách, hết giới hạn, không đủ điều kiện, không có thay đổi,
Dừng và mốc mục tiêu có kiểm thử mô phỏng. Chưa chạy trực tiếp đến hết tài nguyên
hoặc đến giới hạn cấp cuối của game.

Lượt qua GUI đã hoàn tất đúng 5 tướng: bỏ qua chủ tướng, bỏ qua tướng đã đạt/
vượt mốc, nâng tướng còn thiếu đến cấp 51 rồi kết thúc. Qua các lượt thử, Tôn
Sách, Tả Từ và Gia Cát Lượng tăng thật từ 50 → 51, tổng 9 sách EXP; Tư Mã Ý
đang cấp 52 nên giữ nguyên. Chế độ một tướng cũng đã thử qua GUI tại mốc 51,
giữ đúng tướng đã chọn và không dùng thêm sách. Báo cáo cuối:
`runtime/level/team_gui_verified.json`, `selected_gui_verified.json`.
Toàn bộ **112 kiểm thử đạt**, gồm các skill cũ, ảnh thật đã che thông tin, thiếu
sách, mốc dừng, không có thay đổi, hủy và duyệt tối đa 6 tướng.

## Skill cường hóa bảo vật trong Cỗ Máy Thời Gian

Khung **Cường hóa bảo vật** hỗ trợ **Tướng đang chọn** hoặc **Toàn đội tối đa
6 tướng**, với **Tự dừng khi không thể** hoặc **Dừng ở bậc mục tiêu** do người
dùng nhập. Bậc mục tiêu là bậc tuyệt đối, ví dụ `1` tương ứng +1; mốc `0`
kiểm tra điều hướng mà không nâng.

Luồng trong game: sảnh sự kiện → Đội Hình → ô bảo vật cuối cùng bên phải →
tab **Tiến cấp** → nút **Tiến cấp**. Vị trí ô được xác định từ mốc menu Cường Hóa
Trang Bị đã nhận diện. Tướng chưa trang bị bảo vật được bỏ qua; tướng chính cũng
được xử lý nếu đang có bảo vật. Chế độ một tướng ghi nhớ chân dung trước khi
xác minh lại sảnh sự kiện. Nếu đang ở trang chi tiết, trở về Đội Hình trước khi
chạy chế độ một tướng.

Skill dùng vòng nâng cấp đã có của `AdvanceSkill`, với nhận diện riêng cho
Bảo Vật và tài nguyên **Đá Tiến Cấp Bảo Vật + Bạc**; các bậc yêu cầu thêm
bảo vật trùng loại sẽ kiểm tra riêng số lượng nguyên liệu đó. Khi số lượng
chưa đọc được, skill dừng trước thao tác. Mỗi lần gửi một thao tác
Tiến cấp, xác minh bậc tăng đúng +1 qua hai ảnh và số đá giảm khớp chi phí đã
đọc trước khi tiếp tục. Bạc hiển thị theo **Vạn** được quy đổi theo cận dưới:
14.759 Vạn được coi là tối thiểu 147.590.000 Bạc. Đơn vị tiền không nhận diện
được thì dừng; không đoán theo số chữ số.

Hết đá, thiếu Bạc/bảo vật trùng loại, đạt giới hạn hoặc chưa đủ điều kiện thì
dừng tướng hiện tại.
Màn hình lạ, mất phiên game hoặc chưa xác minh được kết quả sẽ dừng cả lượt và
giữ ảnh, không gửi lại thao tác. Tín hiệu Dừng và giới hạn bảo vệ 100 lần nâng
mỗi tướng được dùng chung với tiến cấp tướng. Chưa ghép tự động vào vòng phó bản.

`TreasureSkill.run(target_rank=None)` và
`TeamTreasureSkill.run(target_rank=None, max_heroes=6)` dùng thiết bị ADB cụ thể,
callback tiến độ/ảnh và dữ liệu kết quả giống tiến cấp tướng:
`initial_rank`, `final_rank`, `upgrades`, `resources`, `reason`.
Ảnh trước/sau, báo cáo từng tướng và báo cáo tổng nằm ở `runtime/treasure/`.

Đã kiểm tra mẫu Ngọc Phượng Bội +0: lên +1 cần 50 đá và 5.000 Bạc; kiểm thử
ô chưa trang bị, chi phí tăng theo bậc, thiếu từng tài nguyên, hủy, mốc dừng,
số đá không khớp và duyệt tối đa 6 tướng. Cần Windows OCR `en-US` như các skill
khác; hiện dùng bộ ảnh MuMu 1920×1080.

**Thử trực tiếp ngày 21/10/2026:** đã chạy GUI toàn đội 5 tướng trong sự kiện,
hoàn tất mốc +1; chủ tướng, Tả Từ, Tư Mã Ý và Gia Cát Lượng đều có bảo vật +1.
Bảo vật Tôn Sách đã +18 nên được bỏ qua. Tổng 4 lần nâng +0 → +1 qua các lượt
thử dùng 200 đá (12.139 → 11.939). Các lần thử bị ngắt được giữ báo cáo riêng;
lượt cuối duyệt đủ 5 tướng và không hiện cảnh báo. Ảnh kết quả:
`runtime/treasure/verified_treasure.png`; báo cáo toàn đội:
`runtime/treasure/team_gui_verified.json`.

Đã sửa đọc chi phí Bạc từ 10.000 trở lên và thêm OCR toàn màn hình 900p khi
các tỷ lệ 1080p/720p bỏ sót dấu `/` của số đá. Tool chỉ chấp nhận tỷ lệ có dấu
phân cách được nhận diện. Bộ kiểm thử hiện đạt **142 trường hợp**. Chưa thử
trực tiếp việc dùng hết đá, hết Bạc hoặc nâng đến giới hạn game; các điều kiện
dừng đó được kiểm tra bằng mô phỏng, còn yêu cầu bảo vật trùng loại có ảnh thật.

## Skill Đột Phá và Giác Tỉnh tướng trong Cỗ Máy Thời Gian

Hai nút **Đột Phá tướng** và **Giác Tỉnh tướng** dùng chung phần điều hướng,
chọn tướng, kiểm tra trạng thái và lưu bằng chứng trong `evolution_skill.py`.
Mỗi skill có chế độ **Tướng đang chọn** / **Toàn đội tối đa 6 tướng**, cùng
**Tự dừng khi không thể** / **Dừng ở bậc mục tiêu**. Chỉ chạy sau khi xác minh
sảnh Cỗ Máy Thời Gian; không dùng nguyên liệu ở đội hình thường.

Luồng: sảnh sự kiện → Đội Hình → bấm thân tướng → Thông tin → icon Đột Phá
hoặc Giác Tỉnh → kiểm tra bậc, nguyên liệu và điều kiện → nâng từng bước.
Nếu đang ở tab Tăng cấp/Tiến cấp, skill chọn lại tab Thông tin trước.
Tướng không có icon chức năng được bỏ qua sau hai lần quan sát trang Thông tin.
Chế độ một tướng cần bắt đầu ở Đội Hình với chân dung tướng đã chọn.

- Đột Phá: mốc hiện tại là **Đỏ-Bậc**, ví dụ `1` = Đỏ-Bậc 1. Nếu đổi sang
  một dạng giao diện/bậc chưa nhận diện, tool dừng để lưu ảnh.
- Giác Tỉnh: mốc có **Sao + Lv**, ví dụ `1 sao, Lv0` hoặc `0 sao, Lv1`.
  So sánh theo thứ tự sao rồi Lv. Bước chuyển sao lấy trực tiếp từ giao diện;
  không giả định mỗi sao có một số Lv cố định. Để Lv = 0 khi chỉ cần đạt số sao.
- Nguyên liệu: **Đột phá đơn / Giác tỉnh đơn** và **mảnh tướng khi có ô yêu cầu**.
  Một số bước Giác Tỉnh đang quan sát chỉ hiện một ô đơn. Không đoán số lượng
  nếu OCR bỏ mất dấu `/`; đọc lại toàn khung hình ở tỷ lệ 720p/900p rồi dừng
  nếu vẫn chưa chắc chắn.
- **Chữ đỏ báo thiếu điều kiện cạnh nút nâng chặn thao tác trước khi đọc nguyên
  liệu**. Các tiêu đề bậc màu đỏ và chấm thông báo đỏ nằm ngoài vùng điều kiện
  không phải tín hiệu chặn. Tướng bị chặn/thiếu nguyên liệu được bỏ qua để tiếp
  tục duyệt tướng khác trong chế độ toàn đội.
- Sau mỗi thao tác, xác minh đúng bậc kế tiếp qua hai ảnh; kiểm tra số nguyên
  liệu giảm khi bộ đếm vẫn hiển thị. Màn hình không rõ hoặc kết quả chưa xác
  nhận thì dừng cả lượt, lưu ảnh và không gửi lại lệnh. Có nút Dừng và giới hạn
  bảo vệ tối đa 100 bước/tướng.

API dùng `BreakthroughSkill.run(target_rank=(1,))`,
`AwakeningSkill.run(target_rank=(1, 0))`; truyền `None` để tự dừng theo điều kiện.
Các lớp toàn đội tương ứng: `TeamBreakthroughSkill` / `TeamAwakeningSkill`,
nhận thêm `max_heroes=6`. Kết quả giữ `initial_rank` / `final_rank` dạng tuple
(trong JSON là mảng), `upgrades`, `resources`, `reason`, ảnh và thư mục bằng chứng.
Dữ liệu chạy được lưu riêng ở `runtime/breakthrough/` và `runtime/awakening/`.

**Thử trực tiếp ngày 22/10/2026:** cả hai skill đã chạy qua GUI trên toàn đội
5 tướng trong sự kiện. Chủ tướng không có icon chức năng nên được bỏ qua;
Tôn Sách, Tả Từ, Tư Mã Ý và Gia Cát Lượng đều dừng do chữ đỏ báo điều kiện.
Không gửi thao tác nâng, không tiêu nguyên liệu. Ví dụ Gia Cát Lượng cần
cấp 80 và Tiến cấp +10. Ảnh: `runtime/breakthrough/verified_conditions.png`,
`runtime/awakening/verified_conditions.png`; báo cáo tương ứng:
`runtime/<skill>/team_gui_verified.json`.

Toàn bộ **169 kiểm thử đạt**, bao gồm chi phí hai loại nguyên liệu, Giác Tỉnh
chỉ dùng đơn ở bước hiện tại, chuyển Lv sang sao mới, mốc sao/Lv, chữ đỏ,
chấm đỏ ngoài vùng điều kiện, nền tiêu đề đổi theo tướng, hủy và kết quả không rõ.
Luồng nâng thành công/thiếu nguyên liệu đã kiểm thử bằng mô phỏng; chưa xác nhận
một lần nâng thành công trong game vì đội hiện tại chưa đủ điều kiện. Khi giao
diện hoặc kiểu bậc mới chưa nhận diện được, skill giữ ảnh và dừng để bổ sung mẫu.

## Skill mở rương trong Cỗ Máy Thời Gian

Nút **Mở hết 4 loại rương** chạy trên phiên game đang mở. Bắt đầu ở sảnh
Cỗ Máy Thời Gian hoặc trang Rương; tool quay về xác minh sảnh sự kiện trước
khi sử dụng rương. Luồng: sảnh sự kiện → Rương → lần lượt bốn tab **Nguyên Liệu,
Tăng Phẩm Chất, Tướng, Thần Binh**. Mỗi tab được xác nhận bằng tên trên đầu trang.

- Đọc số lượng, level, EXP hiện có/cần, EXP mỗi rương và số mở trên nút.
  Cỡ lô được đọc lại sau mỗi lần nâng level: ví dụ Nguyên Liệu level 2 mở
  tối đa 100, level 3 tối đa 150; các loại khác có số mở và EXP riêng.
- **Ưu tiên Tăng cấp khi thanh EXP đầy**, kể cả khi số rương đã về 0.
  Xác minh level tăng đúng 1, số rương giữ nguyên và EXP tích lũy giữ nguyên;
  không mặc định EXP về 0 sau tăng cấp. EXP có thể vượt ngưỡng, ví dụ
  `4002/4000`; phần dư vẫn được giữ sau tăng level.
- Gửi mỗi lần Mở một lệnh, đóng bảng **Chúc mừng nhận được** đã nhận diện,
  rồi xác nhận số lượng giảm và EXP tăng khớp qua hai ảnh ổn định. Game có thể
  mở ít hơn số trên nút khi sắp đầy EXP hoặc chỉ còn ít rương. Chỉ chấp nhận
  mức giảm trong giới hạn đã đọc; không đoán tỷ lệ EXP nếu OCR mất dấu `/`.
- Hết rương thì chuyển loại khác; nút mở/nâng level không khả dụng thì ghi lý
  do và xử lý các loại còn lại. Sau một vòng, kiểm tra lại cả bốn loại để xử lý
  rương mới nếu có và xác nhận hết rương. Chỉ báo hoàn tất khi cả bốn loại đã
  hết và không có bước tăng level đang bị chặn.
- Màn hình lạ, số lượng/EXP không khớp hoặc chưa xác nhận kết quả thì dừng cả
  lượt, không gửi lại thao tác. Nút Dừng dùng chung; khi đã gửi lệnh mà chưa xác
  nhận xong, báo cáo giữ `pending_action` để không coi số đếm đã xác minh là
  toàn bộ lượng rương có thể vừa mở.

`ChestSkill(device).run(max_actions=500)` dùng thiết bị ADB cụ thể, callback
progress/preview và stop event như các skill khác. Giới hạn bảo vệ 500 thao tác
Mở/Tăng cấp và 10 vòng kiểm tra; chạm giới hạn trả `blocked`, không báo hết rương.
Kết quả có `types`, `opened`, `level_ups`, `pending_action`; mỗi loại có số lượng
đầu/cuối, level đầu/cuối, số lần mở/nâng và lý do dừng. Ảnh trước/sau, thưởng và
JSON nằm ở `runtime/chest/<lượt chạy>/`. Hiện đã hiệu chỉnh cho MuMu
1920×1080 với Windows OCR en-US như các skill số liệu khác.

**Thử trực tiếp ngày 23/10/2026:** đã mở hết tồn ban đầu **2.995 rương** qua
các lượt khảo sát/chạy GUI: Nguyên Liệu 560, Tăng Phẩm Chất 2.010, Tướng 215,
Thần Binh 210. Tất cả bốn loại được kiểm tra lại và còn 0; cả bốn đang level 3.
Nguyên Liệu tăng level 2 → 3 trong bước khảo sát; Tăng Phẩm Chất tự tăng
1 → 2 → 3 qua GUI. Các lượt cuối dưới cỡ lô, EXP dư `4002/4000` và `10002/10000`
đều được xử lý. Lượt GUI cuối xác nhận mở 1.768 rương, tăng level 2 lần;
con số đó chỉ tính phần tồn còn lại của lượt cuối. Tổng kiểm kê nằm ở
`runtime/chest/verified_inventory_audit.json`, báo cáo cuối ở
`runtime/chest/gui_verified.json`, ảnh `runtime/chest/verified_chests.png`.

Trong quá trình hiệu chỉnh, tool đã dừng khi chưa đọc rõ bộ đếm hoặc thanh EXP;
các báo cáo đó vẫn giữ `pending_action`. Đã chuyển số lượng sang ảnh gốc 1080p,
bổ sung mẫu phông số và loại bỏ tỷ lệ EXP bị OCR cắt dở trước khi đọc lại.
Bộ kiểm thử hiện có **213 trường hợp**, gồm hết rương, tự nâng level trước khi mở,
EXP dư, số mở thay đổi, thiếu điều kiện, dừng/hủy và không gửi lại lệnh chưa xác nhận.

## Quần Anh Tranh Bá trong nhiệm vụ hằng ngày

Từ sảnh chính, bấm **Quần Anh Tranh Bá** trong nhóm nhiệm vụ hằng ngày.
Tool mở Khiêu Chiến, tìm thẻ Quần Anh Tranh Bá và mua phần còn lại trong
giới hạn **4 lượt mua mỗi ngày**. Đã mua đủ thì dùng số lượt đang có;
không mua lại khi chạy tiếp. Tổng giá đã xác nhận trong game là **800 NB**
cho 4 lượt, cộng 3 lượt ban đầu thành 7. Nếu giá vượt 800 NB hoặc số lượt
được phép mua vượt 4, tool dừng để kiểm tra.

- Theo giờ Việt Nam, ưu tiên **Tự động ghép** từ 12:00 đến trước 14:00
  và từ 18:00 đến trước 22:00. Ngoài giờ dùng **Tạo đội → Mời nhanh**.
- Chờ đủ 4 đồng đội sẵn sàng, bấm Chiến rồi chờ ghép đối thủ và trận đấu
  tự chạy. Giới hạn chờ đủ đội là 3 phút, ghép đối thủ và trận đấu là
  5 phút mỗi bước; quá hạn thì báo lý do và lưu ảnh.
- Đóng lần lượt bảng **Kết Thúc** và bảng thưởng bằng vùng trống phía dưới,
  xác nhận số lượt giảm rồi mới bắt đầu trận tiếp theo. Hết lượt thì dừng.
- Nút Dừng dùng chung. Nếu đang ghép đối thủ, tool thử hủy ghép; trận đã
  bắt đầu vẫn do game tự xử lý. Ảnh và kết quả lưu trong `runtime/daily_tasks/`.

**Thử trực tiếp ngày 05/11/2026:** mua 4 lượt với 800 NB, hoàn thành tổng
7 trận trong khung giờ Tự động ghép và xác nhận còn 0 lượt. Nhánh Tạo đội
→ Mời nhanh cũng đã mời đủ 4 đồng đội sẵn sàng, không đánh thêm khi hết lượt.

## Trợ thủ trong nhiệm vụ hằng ngày

Nút **Trợ thủ · 5 tab** chạy từ sảnh chính hoặc trang Trợ thủ đang mở,
theo thứ tự sau:

| Tab | Cấu hình trước khi Chấp hành hiện tại |
| --- | --- |
| Phó bản | Giữ cấu hình hiện có |
| Đấu trường | Tổng 30 lượt khiêu chiến |
| Tháp Ma Hồn | Tạo mới và càn quét 2; Luyện ngục 8; cuộn xuống đặt Tinh anh 6 |
| Vượt ải trảm tướng | Thí luyện trảm tướng: càn quét 6 |
| Thần binh | Thần binh chủng: khiêu chiến 6 |

Tool đọc số đang hiển thị và chỉ cộng/trừ đến đúng mốc, không cộng thêm
nếu đã đủ. Mục đang hiển thị 0 lượt được giữ nguyên; tab không còn mục
cần chạy được bỏ qua. Vì vậy có thể chạy tiếp sau khi bị gián đoạn mà
không tự mua lại các mục đã về 0. Việc tăng số lượt có thể tiêu NB khi
bấm Chấp hành hiện tại, theo giá trong game.

Mỗi tab chỉ gửi Chấp hành hiện tại một lần, chờ bảng Càn quét ổn định,
chạm vùng trống phía dưới để đóng rồi xác nhận số lượt về 0. Không phụ
thuộc dòng hướng dẫn chạm vùng trống vì dòng này có thể biến mất. Nếu
chưa đọc rõ số, số chưa đổi sau cộng/trừ hoặc kết quả chưa xác nhận,
tool dừng và lưu ảnh, không bấm lặp lại. Nút Dừng ngăn thao tác tiếp theo;
lượt càn quét đã bắt đầu vẫn do game xử lý.

Ảnh trước mỗi thao tác, ảnh sau từng tab và báo cáo được lưu ở
`runtime/daily_tasks/<lượt chạy>/`.

**Kiểm chứng ngày 05/11/2026:** Phó bản và Đấu trường 30 lượt đã chạy trong
lượt khảo sát trước. Lượt rà soát sau chạy qua GUI hoàn tất Tháp Ma Hồn
2 / 8 / 6, Trảm tướng 6 và Thần binh 6, đóng kết quả và xác nhận các lượt
về 0. Chạy lại cả 5 tab khi đã hết lượt không gửi thêm lệnh cộng lượt hoặc
Chấp hành. Đã sửa lỗi đọc số 6 trên ảnh thu nhỏ bằng cách ưu tiên đọc số từ
ảnh gốc; kiểm thử ảnh ở 1920×1080, 1280×720 và 960×540.

## Quét map mảnh Điển Vi trong nhiệm vụ hằng ngày

Nút **Quét mảnh Điển Vi** đi theo luồng sảnh chính → Tướng / Túi tướng
→ Mảnh Tướng → Nhận Nhiều. Tool mở một danh sách chọn mới, tìm đúng tên
**Mảnh Điển Vi**, xác nhận chỉ một tướng được tích rồi bấm **C.Quét nhanh**.
Nếu Điển Vi chưa hiện, tool cuộn tìm trong danh sách.

Trước khi gửi OK, tool xác nhận đủ ba tùy chọn:

- Tự dùng Thể Lực Đơn bổ sung thể lực.
- Tự tiêu diệt kẻ địch mạnh bằng Chiến Lệnh.
- Đồng thời càn quét Phó Bản Tinh Anh.

Ô đã được tích sẵn được giữ nguyên. OK chỉ gửi một lần; sau đó chờ nút
**Dừng quét** chuyển thành **Càn quét hoàn thành**, xác nhận kết quả, đóng
danh sách chọn và dừng. Nút Dừng của tool cũng gửi Dừng quét nếu đã nhận
diện đúng một lượt quét mảnh đang chạy. Khi chưa rõ màn hình hoặc chưa
xác nhận được lựa chọn, tool lưu ảnh và dừng, không tự khởi động lượt mới.

**Thử trực tiếp ngày 05/11/2026:** chọn riêng Điển Vi, bật đủ ba ô, game
quét 50 lần; nhận 9 mảnh Điển Vi, số mảnh tăng 537 → 546. Đã xác nhận
kết quả và trở lại Mảnh Tướng. Ảnh và báo cáo nằm trong
`runtime/daily_tasks/<lượt chạy>/` như các chức năng nhiệm vụ ngày khác.

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

**Cập nhật nút 5 lần (21/10/2026):** đã thử qua GUI trên Gia Cát Lượng,
56 → 61 bằng đúng một lượt `5 lần` (`batch_actions=1, single_actions=0`).
Tool nhận diện cấp 61, số sách giảm và dừng đúng mốc. Báo cáo:
`runtime/level/batch_gui_verified.json`; ảnh `verified_batch_5.png`.
Đã sửa nhận diện số vàng 6 bị nhầm với 0 bằng mẫu đúng phông chữ của game.
Bộ kiểm thử hiện có **117 trường hợp đạt**, gồm batch 5 cấp, chuyển sang từng
lần gần mốc và batch dừng sớm do hết sách/giới hạn.


## Hợp nhất quản lý nhiều instance và các skill hiện có

Các nút nhiệm vụ hằng ngày, nâng tướng, mở rương và spam phó bản vẫn được giữ.
Chúng chạy trên instance đang chọn, với ADB, cờ dừng và đồng hồ riêng đã chốt
khi bắt đầu; đổi lựa chọn không đổi đích của tác vụ đang chạy. Script A/B/C
vẫn chỉ có chu trình thử đã mô tả ở trên, chưa tự ghép các skill daily thành chuỗi.
Các skill tự đọc và đóng bảng kết quả của mình; tự đóng popup chung của luồng
Excel không can thiệp vào những bảng kết quả này.
