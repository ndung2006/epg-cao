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
│   └── cleanup_old_output.py      # Xoa thu muc output cu hon N ngay
└── output/                        # (khong commit) ket qua chay, 1 thu muc con moi ngay YYYY-MM-DD
```

## Cài đặt

```bash
pip install --break-system-packages requests beautifulsoup4 xlwt
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
đó để dọn dẹp thư mục cũ hơn 7 ngày. Chạy gần nửa đêm là bắt buộc: trang baomoi
chỉ trả về lịch bắt đầu từ chương trình đang phát sóng tại thời điểm cào (không
phải từ 00:00:00), nên chạy càng trễ trong ngày thì file càng thiếu mất đoạn đầu
ngày. Xem chi tiết dòng cron theo múi giờ hệ thống trong `SKILL.md`.

## Ghi chú kỹ thuật

- Danh sách kênh được tự động phát hiện từ các link trên trang gốc (không hardcode),
  lọc trùng theo tên kênh.
- Vì lịch trên baomoi có thể vắt qua nửa đêm, script tự nhận diện mốc giờ quay
  vòng để gán đúng ngày cho từng dòng và tính "Thời lượng" so với chương trình kế tiếp.
- `output/` không nên commit vào git (xem `.gitignore`) vì đây là dữ liệu sinh ra
  mỗi ngày, không phải mã nguồn.
