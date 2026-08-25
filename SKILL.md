---
name: lich-truyen-hinh-baomoi
description: Cào (scrape) lịch phát sóng truyền hình từ trang baomoi.com/tien-ich-lich-truyen-hinh.epi và xuất ra một file Excel (.xlsx) riêng biệt cho mỗi kênh truyền hình. Dùng skill này khi người dùng yêu cầu lấy/cập nhật lịch truyền hình từ baomoi, xuất lịch phát sóng ra Excel theo từng kênh, hoặc thiết lập chạy tự động (cron) hàng ngày cho việc này.
---

# Lịch truyền hình Baomoi -> Excel (mỗi kênh 1 file)

## Khi nào dùng skill này

Dùng skill này khi người dùng muốn:
- Lấy lịch phát sóng truyền hình mới nhất từ `https://baomoi.com/tien-ich-lich-truyen-hinh.epi`.
- Xuất lịch phát sóng ra file Excel (.xlsx), **mỗi kênh truyền hình một file riêng**.
- Lấy lịch cho **tất cả các kênh** có trên trang (không giới hạn danh sách).
- Thiết lập chạy việc này **tự động theo lịch** (ví dụ: mỗi ngày một lần) bằng cơ chế cron job của OpenClaw.

## Yêu cầu môi trường

Trước khi chạy, đảm bảo đã cài các thư viện Python cần thiết (chỉ cần cài một lần):

```bash
pip install --break-system-packages requests beautifulsoup4 xlwt
```

Lưu ý: dùng `xlwt` (không dùng `openpyxl`) vì output phải là file `.xls` chuẩn Excel 97-2003 (định dạng nhị phân OLE2/CDFV2), giống hệt file mẫu do người dùng cung cấp — `openpyxl` chỉ ghi được `.xlsx`.

## Các bước thực hiện

1. Chạy script `scripts/fetch_tv_schedule.py`. Script sẽ:
   - Tải trang `https://baomoi.com/tien-ich-lich-truyen-hinh.epi`.
   - Tìm toàn bộ danh sách kênh (mọi thẻ `<a>` có href khớp mẫu `tien-ich-lich-truyen-hinh-<slug>.epi`), cộng thêm chính trang gốc (kênh mặc định, thường là VTV1).
   - Với từng kênh, tải trang lịch phát sóng riêng của kênh đó và tách bảng gồm 2 cột: **Giờ** và **Chương trình**.
   - Gán ngày thực tế cho từng dòng (tự phát hiện khi giờ vòng qua nửa đêm để tăng ngày lên 1), và tính **Thời lượng** = khoảng cách tới chương trình kế tiếp (dòng cuối cùng tính đến hết ngày, 24:00:00).
   - Ghi lịch của từng kênh thành 1 file `.xls` riêng, đúng cấu trúc file mẫu: 3 dòng đầu để trống, dòng thứ 4 là tiêu đề, từ dòng thứ 5 là dữ liệu, gồm 5 cột **ID / Ngày / Thời gian bắt đầu / Thời lượng / Tên chương trình**.
   - Đặt tên file theo đúng mẫu: `<Tên kênh>EPG<ddMMyyyy>.xls` (ví dụ: `VTV1 (HD)EPG20082026.xls`), giữ nguyên dấu tiếng Việt và khoảng trắng trong tên kênh, chỉ lọc bỏ các ký tự không hợp lệ trên Windows (`\ / : * ? " < > |`).
   - Lưu vào thư mục con theo ngày dạng `YYYY-MM-DD` bên trong thư mục output: `output/<YYYY-MM-DD>/<Tên kênh>EPG<ddMMyyyy>.xls`.

   Chạy mặc định (lấy tất cả kênh):
   ```bash
   python3 scripts/fetch_tv_schedule.py --output-dir ./output
   ```

   Có thể giới hạn số kênh khi test nhanh:
   ```bash
   python3 scripts/fetch_tv_schedule.py --output-dir ./output --limit 5
   ```

2. Sau khi chạy xong, script in ra:
   - Tổng số kênh đã lấy được lịch thành công.
   - Danh sách kênh bị lỗi (nếu có), kèm lý do lỗi, để có thể thử lại riêng.
   - Đường dẫn thư mục chứa các file Excel vừa tạo.

3. Báo lại cho người dùng: số file đã tạo, đường dẫn thư mục, và danh sách kênh lỗi (nếu có) — không tự ý xoá hay ghi đè dữ liệu ngoài thư mục output đã chỉ định.

## Thiết lập chạy tự động hàng ngày (cron hệ thống, không tốn token)

Vì đây là tác vụ cố định (không cần AI suy luận mỗi lần chạy), nên dùng **cron của hệ điều hành (Linux/WSL)** thay vì cron kiểu agent của OpenClaw — cách này chạy hoàn toàn miễn phí, không tốn token.

Mở crontab:
```bash
crontab -e
```

Thêm 2 dòng sau (đường dẫn ví dụ, sửa lại cho khớp máy bạn):
```
0 6 * * * /usr/bin/python3 /home/openclaw/.openclaw/skills/lich-truyen-hinh-baomoi/scripts/fetch_tv_schedule.py --output-dir /home/openclaw/.openclaw/skills/lich-truyen-hinh-baomoi/scripts/output >> /home/openclaw/.openclaw/skills/lich-truyen-hinh-baomoi/scripts/cron.log 2>&1
10 6 * * * /usr/bin/python3 /home/openclaw/.openclaw/skills/lich-truyen-hinh-baomoi/scripts/cleanup_old_output.py --output-dir /home/openclaw/.openclaw/skills/lich-truyen-hinh-baomoi/scripts/output --days 7 >> /home/openclaw/.openclaw/skills/lich-truyen-hinh-baomoi/scripts/cleanup.log 2>&1
```

Dòng đầu: 6:00 sáng mỗi ngày lấy lịch mới, xuất vào `output/<YYYY-MM-DD>/`.
Dòng thứ hai: 6:10 sáng (sau khi lấy lịch xong 10 phút), tự xoá các thư mục `output/<YYYY-MM-DD>/` đã cũ hơn 7 ngày.

Kiểm tra đã lưu đúng chưa:
```bash
crontab -l
```

Chạy thử ngay (không cần đợi tới giờ) để kiểm tra:
```bash
python3 scripts/fetch_tv_schedule.py --output-dir ./output
python3 scripts/cleanup_old_output.py --output-dir ./output --days 7
```

## Định dạng đầu ra mong đợi

- Thư mục `output/<YYYY-MM-DD>/` chứa N file `.xls` (N = số kênh lấy được lịch thành công), định dạng nhị phân Excel 97-2003 chuẩn (không phải `.xlsx` đổi tên).
- Mỗi file có đúng 1 sheet, cấu trúc: 3 dòng đầu để trống, dòng 4 là tiêu đề (`ID`, `Ngày`, `Thời gian bắt đầu`, `Thời lượng`, `Tên chương trình`), từ dòng 5 trở đi là dữ liệu theo thứ tự thời gian.
- Tên file: `<Tên kênh>EPG<ddMMyyyy>.xls`, ví dụ `VTV1 (HD)EPG20082026.xls`, `Bắc NinhEPG20082026.xls`.

## Ràng buộc an toàn / lưu ý

- Chỉ đọc dữ liệu công khai từ baomoi.com, không đăng nhập, không gửi bất kỳ thông tin cá nhân nào lên trang.
- Có độ trễ nhỏ (khoảng 0.5–1 giây) giữa các request để tránh gửi quá nhiều request dồn dập vào baomoi.com.
- Nếu một kênh lỗi (mất mạng, đổi cấu trúc trang, v.v.), bỏ qua kênh đó, ghi log lỗi, và tiếp tục với các kênh còn lại — không dừng toàn bộ tiến trình.
- Nếu cấu trúc HTML của baomoi.com thay đổi khiến không tách được bảng giờ/chương trình, báo lỗi rõ ràng thay vì xuất ra file rỗng hoặc dữ liệu sai.
- Không tự ý mở rộng phạm vi sang các trang/tính năng khác của baomoi.com ngoài lịch truyền hình.
