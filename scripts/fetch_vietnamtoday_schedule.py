#!/usr/bin/env python3
"""
fetch_vietnamtoday_schedule.py

Lấy lịch phát sóng (EPG) kênh Vietnam Today từ API chính thức của
https://vietnamtoday.vtv.vn/live.htm và xuất ra file .xls
(định dạng Excel 97-2003 chuẩn) theo đúng cấu trúc file EPG mẫu:
3 dòng trống, 1 dòng tiêu đề, các cột
ID / Ngày / Thời gian bắt đầu / Thời lượng / Tên chương trình.

Nguồn dữ liệu (phát hiện từ main-v23.min.js trên trang live.htm):
  API: https://vietnamtoday.vtv.vn/ajax/programchannel.api?id=1&date=YYYY-MM-DD
  - id=1 lấy từ <input id="liveDataId" data-id="1">
  - date dạng YYYY-MM-DD (ví dụ 2026-09-07)
  - Trả về JSON {code, message, data: [{ScheduleTime, Title, Description, ...}]}
  - ScheduleTime dạng ISO "2026-09-07T20:15:00" (giờ GMT+7, không kèm timezone)
  - Mỗi ngày có ~60-66 mục, phủ 00:00 -> 23:45

  Trang live.htm render EPG động qua JS:
    livePage.getDataProgram(id, date, ".calendar__list")
    -> $.ajax({url: appSettings.baseUrl + `/ajax/programchannel.api?id=${n}&date=${t}`})
  Ảnh chụp màn hình xác nhận: MON - 09/07/2026 GMT+7 hiển thị
    20:15 Talk Vietnam / 21:00 Newsline / 21:30 Eyes on V
  khớp chính xác với data API cho 2026-09-07.

Thời lượng = khoảng cách tới chương trình kế tiếp (mục cuối tính đến 23:59:59).
Tên file: "Vietnam TodayEPG<ddMMyyyy>.xls" (ddMMyyyy = ngày phát sóng)

Usage:
    python3 fetch_vietnamtoday_schedule.py --output-dir ./output
    python3 fetch_vietnamtoday_schedule.py --output-dir ./output --date 2026-09-07
    python3 fetch_vietnamtoday_schedule.py --output-dir ./output --date 2026-09-08

Requires: requests, xlwt (và fetch_tv_schedule.py trong cùng thư mục)
    pip install --break-system-packages requests xlwt
"""

import argparse
import datetime
import sys
import time
from pathlib import Path

import requests

from fetch_tv_schedule import write_xls, safe_filename_part

API_BASE = "https://vietnamtoday.vtv.vn"
API_PATH = "/ajax/programchannel.api"
CHANNEL_ID = 1  # từ <input id="liveDataId" data-id="1"> trên live.htm
CHANNEL_NAME = "Vietnam Today"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://vietnamtoday.vtv.vn/live.htm",
}


def fetch_schedule(session: requests.Session, target_date: datetime.date, timeout: int = 15, retries: int = 2):
    """Gọi API programchannel.api, trả về list of (datetime, title, description)."""
    date_str = target_date.isoformat()  # YYYY-MM-DD
    url = f"{API_BASE}{API_PATH}"
    params = {"id": CHANNEL_ID, "date": date_str}
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, params=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 200:
                # API trả code 404 khi không có lịch cho ngày đó
                msg = data.get("message", "")
                raise ValueError(f"API code={data.get('code')} message={msg}")
            items = data.get("data", [])
            if not isinstance(items, list):
                raise ValueError(f"API data không phải list: {type(items)}")
            results = []
            for it in items:
                title = (it.get("Title") or "").strip()
                if not title:
                    continue
                sched = it.get("ScheduleTime") or ""
                # "2026-09-07T20:15:00"
                try:
                    dt = datetime.datetime.fromisoformat(sched)
                except ValueError:
                    continue
                desc = (it.get("Description") or "").strip()
                results.append((dt, title, desc))
            # API đã trả theo giờ tăng dần, nhưng sort lại cho chắc
            results.sort(key=lambda x: x[0])
            return results
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_err


def build_epg_rows(parsed_items, target_date: datetime.date):
    """
    parsed_items: list of (datetime, title, description) đã sort tăng dần.
    Tính Thời lượng = next_dt - current_dt (mục cuối -> 23:59:59).
    Trả về list dict: id, start_dt, duration, program
    """
    rows = []
    for i, (dt, title, desc) in enumerate(parsed_items):
        if i + 1 < len(parsed_items):
            duration = parsed_items[i + 1][0] - dt
        else:
            end_of_day = datetime.datetime(dt.year, dt.month, dt.day, 23, 59, 59)
            duration = end_of_day - dt
            if duration.total_seconds() < 0:
                duration = datetime.timedelta(seconds=0)
        # Tên chương trình: Title (Description nếu có thì thêm vào ngoặc)
        # Giữ Title gốc để khớp EPG mẫu; Description chỉ để tham khảo
        program = title
        rows.append({
            "id": i + 1,
            "start_dt": dt,
            "duration": duration,
            "program": program,
        })
    return rows


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="./output", help="Thư mục để lưu file .xls")
    parser.add_argument("--date", default=None, help="Ngày phát sóng cần lấy, dạng YYYY-MM-DD (mặc định: hôm nay)")
    args = parser.parse_args()

    target_date = (
        datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date else datetime.date.today()
    )
    date_stamp = target_date.strftime("%d%m%Y")
    out_dir = Path(args.output_dir) / target_date.isoformat()

    session = requests.Session()
    print(f"Đang tải EPG Vietnam Today cho ngày {target_date.isoformat()} ...")
    print(f"API: {API_BASE}{API_PATH}?id={CHANNEL_ID}&date={target_date.isoformat()}")
    try:
        parsed = fetch_schedule(session, target_date)
    except Exception as e:  # noqa: BLE001
        print(f"LỖI: không thể tải lịch: {e}", file=sys.stderr)
        print("Gợi ý: thử ngày khác (ví dụ --date 2026-09-07 hoặc --date 2026-09-08).", file=sys.stderr)
        sys.exit(1)

    if not parsed:
        print("LỖI: API trả về danh sách rỗng", file=sys.stderr)
        sys.exit(1)

    print(f"Tìm thấy {len(parsed)} chương trình. Đang tính thời lượng...")
    epg_rows = build_epg_rows(parsed, target_date)

    filename = f"{safe_filename_part(CHANNEL_NAME)}EPG{date_stamp}.xls"
    file_path = out_dir / filename
    write_xls(file_path, epg_rows)

    print(f"\n===== HOÀN TẤT =====")
    print(f"Kênh: {CHANNEL_NAME} (id={CHANNEL_ID})")
    print(f"Ngày phát sóng: {target_date.isoformat()}")
    print(f"Số mục: {len(epg_rows)}")
    print(f"File: {file_path.resolve()}")
    for r in epg_rows[:5]:
        print(f"  {r['id']:2d}. {r['start_dt'].strftime('%d/%m/%Y %H:%M')} | {str(r['duration'])} | {r['program'][:70]}")
    if len(epg_rows) > 5:
        print(f"  ... và {len(epg_rows)-5} mục nữa")
        # In thêm 3 mục khớp screenshot để xác nhận
        for r in epg_rows:
            if r["program"] in ("Talk Vietnam", "Newsline", "Eyes on V") and r["start_dt"].hour >= 20:
                print(f"  >> {r['start_dt'].strftime('%H:%M %d/%m')}  {r['program']}")


if __name__ == "__main__":
    main()