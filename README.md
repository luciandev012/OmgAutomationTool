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
- Sau khi thua, tool đóng kết quả, chọn lại dấu kiếm tại vị trí ải đang mở trên
  cùng map; không dò sang map khác. Nếu có bảng Chiến thì đối chiếu tên ải với
  trận trước. Hỗ trợ game vào trận ngay khi chọn ải. Vị trí ải thay đổi, tên không
  khớp hoặc không xác nhận được đường quay lại sẽ dừng với `retry_unverified`.
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
  Không cần đủ 30/30 sao. Tool chờ tên map thay đổi ổn định rồi chọn dấu kiếm của
  ải đầu tiên; cũng hỗ trợ trường hợp nút đưa về danh sách map. Có thể chạy tool
  ngay trên map đã hoàn thành đang hiện Chương kế. Nếu map cũ vẫn đứng yên sau
  khi bấm, tool dừng theo thời gian chờ, không bấm lặp hoặc chọn lại boss cũ.
- Dấu kiếm của ải 1 có thể bị thanh tên map che phần dưới. Tool nhận diện phần
  lưỡi kiếm còn lộ phía trên và giữ điểm chạm vào nhân vật, thay vì thanh tiêu đề.
- Khi không thấy ải đang mở, tool chờ ảnh mới và quét map theo cả hai chiều:
  tối đa 3 lần về phía ải sau, rồi tối đa 6 lần ngược lại để phủ phần đầu map.
  Ảnh từng vùng được lưu ở `runtime/dungeon_scan/scan_00.png` đến `scan_09.png`.
  Không suy ra đã hoàn thành chương từ việc mất dấu kiếm; chỉ chuyển chương khi
  xác nhận nút **Chương kế**. Nếu vẫn không tìm thấy, giữ nguyên map để kiểm tra.
- Với dấu kiếm bị cắt ở mép trên (thường gặp ở boss ải 10), nhận diện phần biểu
  tượng còn nhìn thấy với ngưỡng chặt, khôi phục vị trí đầy đủ và xác nhận qua hai
  ảnh liên tiếp trước khi chọn nhân vật. Ảnh lóe đơn lẻ, ứng viên đổi vị trí hoặc
  nền bị làm tối phía sau bảng thông báo không được dùng để chọn ải.
- Ảnh cuối lần chạy được lưu cục bộ ở `runtime/dungeon_last_screen.png`.

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


**Cập nhật nút 5 lần (21/10/2026):** đã thử qua GUI trên Gia Cát Lượng,
56 → 61 bằng đúng một lượt `5 lần` (`batch_actions=1, single_actions=0`).
Tool nhận diện cấp 61, số sách giảm và dừng đúng mốc. Báo cáo:
`runtime/level/batch_gui_verified.json`; ảnh `verified_batch_5.png`.
Đã sửa nhận diện số vàng 6 bị nhầm với 0 bằng mẫu đúng phông chữ của game.
Bộ kiểm thử hiện có **117 trường hợp đạt**, gồm batch 5 cấp, chuyển sang từng
lần gần mốc và batch dừng sớm do hết sách/giới hạn.
