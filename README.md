# EPG Excel Baomoi

Script tự động cào (scrape) lịch phát sóng truyền hình từ trang
[baomoi.com/tien-ich-lich-truyen-hinh.epi](https://baomoi.com/tien-ich-lich-truyen-hinh.epi)
và xuất ra file `.xls` (Excel 97-2003 chuẩn) riêng biệt cho từng kênh, đúng định
dạng EPG mẫu: `ID / Ngày / Thời gian bắt đầu / Thời lượng / Tên chương trình`.

Đây cũng là một **skill cho OpenClaw** (xem `SKILL.md`) — có thể cài trực tiếp vào
`~/.openclaw/workspace/skills/` để OpenClaw nhận diện và gọi khi cần.

## Cấu trúc dự án

```
.
├── SKILL.md                       # Mo ta skill cho OpenClaw (huong dan su dung chi tiet)
├── scripts/
│   ├── fetch_tv_schedule.py       # Cao lich + xuat file .xls moi kenh
│   ├── cleanup_old_output.py      # Xoa thu muc output cu hon N ngay
│   └── sort_xls_by_time.py        # Sap xep lai 1 file .xls da xuat theo ngay/gio tang dan
└── output/                        # (khong commit) ket qua chay, 1 thu muc con moi ngay YYYY-MM-DD
```

## Cài đặt

```bash
pip install --break-system-packages requests beautifulsoup4 xlwt xlrd
```

## Sử dụng

Chạy thủ công:
```bash
python3 scripts/fetch_tv_schedule.py --output-dir ./output
python3 scripts/cleanup_old_output.py --output-dir ./output --days 7
```

Tham số:
- `--output-dir` — thư mục gốc lưu kết quả (mặc định `./output`), script tự tạo thư mục con theo ngày `YYYY-MM-DD`.
- `--limit N` (chỉ với `fetch_tv_schedule.py`) — giới hạn số kênh, dùng để test nhanh.
- `--delay` — độ trễ (giây) giữa các request tới baomoi.com (mặc định 0.7s).
- `--days` (chỉ với `cleanup_old_output.py`) — số ngày giữ lại trước khi xoá (mặc định 7).

Nếu một file `.xls` đã xuất ra có thứ tự dòng chưa đúng ngày/giờ tăng dần (ví dụ file
cũ, hoặc nghi ngờ dữ liệu bị lệch), sắp xếp lại ngay trên file đó mà không cần cào lại:
```bash
python3 scripts/sort_xls_by_time.py --file "output/2026-08-25/VTV1 (HD)EPG25082026.xls"
```
Mặc định ghi đè lên chính file đó; dùng `--output <file_khac>.xls` nếu muốn ghi ra file mới.

## Đầu ra

Mỗi lần chạy tạo `output/<YYYY-MM-DD>/<Tên kênh>EPG<ddMMyyyy>.xls`, ví dụ:
`output/2026-08-21/VTV1 (HD)EPG21082026.xls`.

Mỗi file gồm 1 sheet, 3 dòng đầu để trống, dòng 4 là tiêu đề, từ dòng 5 là dữ
liệu với 5 cột: `ID`, `Ngày`, `Thời gian bắt đầu`, `Thời lượng`, `Tên chương trình`.
Font Arial 12, không in đậm, độ rộng cột khớp với file EPG mẫu gốc. Cột `Ngày`,
`Thời gian bắt đầu`, `Thời lượng` được ghi là giá trị ngày/giờ thật của Excel
(không phải text) nên sắp xếp tăng dần trong Excel sẽ đúng theo thứ tự thời gian
thực tế (00:00:00 → 23:59:59), không bị sai do so sánh chuỗi ký tự.

## Chạy tự động hàng ngày (cron, không tốn token AI)

Xem chi tiết trong `SKILL.md`, phần "Thiết lập chạy tự động hàng ngày". Tóm tắt:
dùng `crontab` của hệ điều hành (không dùng cron kiểu agent của OpenClaw) để gọi
thẳng 2 script trên mỗi ngày — không tốn token vì không đi qua AI.

Hiện đã thiết lập trên máy chạy OpenClaw (WSL Ubuntu) tại:
`~/.openclaw/workspace/skills/lich-truyen-hinh-baomoi/scripts/`, chạy lúc 00:05
giờ Việt Nam (tức 17:05 giờ GMT/UTC ngày hôm trước) để lấy lịch, và 10 phút sau
đó để dọn dẹp thư mục cũ hơn 7 ngày. Giờ chạy cụ thể không bắt buộc phải gần nửa
đêm — trang baomoi luôn trả về đủ lịch của cả ngày hôm đó (00:00:00 → 23:59:59)
bất kể cào vào lúc nào, chỉ khác là thứ tự hiển thị trên trang là "sắp phát trước,
đã phát sau" (script đã tự sắp lại theo giờ tăng dần). Xem chi tiết dòng cron
theo múi giờ hệ thống trong `SKILL.md`.

## Ghi chú kỹ thuật

- Danh sách kênh được tự động phát hiện từ các link trên trang gốc (không hardcode),
  lọc trùng theo tên kênh.
- Trang baomoi hiển thị lịch của đúng 1 ngày (ngày cào), nhưng theo thứ tự
  "chương trình sắp/đang phát trước, chương trình đã phát sóng sáng cùng ngày đó
  sau" — không phải theo giờ tăng dần và không liên quan tới ngày hôm sau. Script
  gán cùng 1 ngày cho toàn bộ dữ liệu rồi sắp xếp lại theo giờ tăng dần trước khi
  ghi ra file, và tính "Thời lượng" so với chương trình kế tiếp trong danh sách
  đã sắp xếp.
- `output/` không nên commit vào git (xem `.gitignore`) vì đây là dữ liệu sinh ra
  mỗi ngày, không phải mã nguồn.
