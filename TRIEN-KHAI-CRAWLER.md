# Chạy thợ nền cào + đẩy tự động trên Coolify (Docker)

Mục tiêu: đúng **07:01 mỗi ngày** (giờ Việt Nam), thợ nền tự cào lịch rồi
đẩy sang app EPG. Kênh đặt "Tự động" trên EPG được nạp + gửi duyệt luôn.

Giờ cào và kênh Tự/Tay chỉnh trên web (tab **Quản lý dữ liệu** của EPG) —
thợ nền chỉ đọc và làm theo, không phải sửa gì ở máy chạy nó.

---

## Trước khi bắt đầu

Cần:
- Kho này đã đẩy lên GitHub (riêng tư), giống kho EPG.
- App EPG đang chạy và đã đặt `EPG_CRAWL_TOKEN` (tab Quản lý dữ liệu ghi
  "Khoá cào: đã đặt trên máy chủ").
- Chuỗi token đó — sẽ dán vào Coolify ở bước dưới.

---

## Bước 1 — Đẩy kho crawler lên GitHub

Tạo một kho **riêng tư** (Private) trên GitHub, rồi:

```bash
cd "EPG Excel baomoi"
git remote add origin https://github.com/<tài-khoản>/epg-cao.git
git branch -M main
git push -u origin main
```

Kiểm một điều trước khi đẩy: file chứa token **không** được lên git.

```bash
git ls-files | grep -i "epg_push_config.json"   # phải KHÔNG ra gì
```

`epg_push_config.json` (chứa token) đã bị chặn trong `.gitignore`. File lên
git là `epg_push_config.docker.json` — chỉ có danh sách lệnh cào, **không có
token**. Token đặt riêng trên Coolify ở bước 3.

---

## Bước 2 — Tạo ứng dụng trên Coolify

Thợ nền là **tiến trình chạy nền, không có cổng web**, nên dùng kiểu Docker
Compose cho gọn:

1. **+ New Resource › Docker Compose** (không phải Application), chọn kho
   `epg-cao` vừa tạo, nhánh `main`.
2. Coolify đọc `docker-compose.yaml` sẵn trong kho — không cần cấu hình
   Build Pack hay Port.
3. **Auto Deploy**: tuỳ ý. Bật cũng được vì đây là worker, không có bản
   dựng hỏng nào lên sóng trực tiếp.

---

## Bước 3 — Đặt biến môi trường (QUAN TRỌNG)

**Environment Variables**, thêm ba biến:

| Tên | Giá trị | Ghi chú |
|---|---|---|
| `EPG_URL` | `https://epg.vtcrd.top` | Địa chỉ app EPG |
| `EPG_CRAWL_TOKEN` | *(chuỗi token của EPG)* | Phải GIỐNG HỆT khoá đặt ở app EPG |
| `TZ` | `Asia/Ho_Chi_Minh` | Bỏ đi thì 07:01 nổ nhầm sang 14:01 giờ Việt Nam |

Token sai một ký tự là EPG trả 403, thợ nền không đẩy được. `TZ` sai thì
cào đúng nhưng lệch giờ.

---

## Bước 4 — Deploy

Bấm **Deploy**. Xem **Logs**. Thợ nền lên là in:

```
HH:MM:SS  Thợ nền khởi động. Hỏi lịch EPG mỗi 120 giây.
```

Cứ 120 giây nó hỏi lịch EPG một lần. Tới **07:01** thì:

```
07:01:xx  tới giờ 07:01 — bắt đầu cào+đẩy.
07:01:xx  cào: python scripts/fetch_vtv_schedule.py --output-dir /data/output
...
07:0x:xx  Cào+đẩy 2026-xx-xx: N ok, M lỗi.
```

---

## Bước 5 — Kiểm

Sau lần cào đầu (hoặc bấm thử ngay, xem dưới):

- Trên EPG › tab **Quản lý dữ liệu**: đèn nhịp tim **xanh** —
  "Bộ cào đang hoạt động", kèm số kênh ok/hỏng và giờ cào cuối.
- Các kênh Tự động: cột Kết quả ghi "Đã nạp + gửi duyệt".
- Tab **Kiểm duyệt** (ngày hôm nay): các kênh Tự động chờ duyệt.

### Muốn thử ngay, không đợi 07:01

Trong Coolify, mở **Terminal** của container `cao`, chạy:

```bash
python scripts/crawl_and_push.py --once
```

Nó cào + đẩy ngay một lần, không phụ thuộc lịch.

---

## Đổi giờ cào về sau

Vào EPG › **Quản lý dữ liệu** › sửa ô "Các mốc giờ", bấm Lưu. Thợ nền lần
hỏi lịch sau (trong vòng 2 phút) sẽ theo giờ mới. **Không phải** đụng gì
tới Coolify hay container.

Nhiều mốc trong ngày thì cách nhau dấu phẩy, ví dụ `05:00, 17:00`.

---

## Crawler hỏng thì EPG có sao không

Không. Hai bên tách hẳn:
- Container `cao` chết → EPG vẫn chạy, người nhập/duyệt/xuất bản như thường.
  Trên tab Quản lý dữ liệu, đèn chuyển **vàng** "Bộ cào chưa báo cáo từ …
  giờ" — nhìn thấy được mà không làm sập gì. Kênh Tự động chỉ không có lịch
  mới, giữ nguyên lịch cũ.
- EPG sập tạm → thợ nền báo lỗi trong log, nhớ lịch cũ, thử lại vòng sau.

## Sao lưu

Volume `cao-data` chỉ chứa file output tạm và mốc đã cào — **không** cần
sao lưu. Cào lại là có. Thứ duy nhất phải giữ là token (đã ở EPG + biến
môi trường Coolify).
