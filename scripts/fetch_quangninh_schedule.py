#!/usr/bin/env python3
"""
fetch_quangninh_schedule.py

Lay lich phat song 2 kenh Quang Ninh (QTV1, QTV3) tu API cua baoquangninh.vn
va xuat ra file .xls (dinh dang Excel 97-2003 chuan) rieng biet cho tung kenh,
dung cau truc file EPG mau: 3 dong trong, 1 dong tieu de, cac cot
ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.

Khac voi baomoi.com (chi tra ve lich tu thoi diem cao, phai tu suy ra ngay),
API nay ho tro loc dung theo tham so 'date' (dang YYYYMMDD) nen lay duoc chinh
xac lich 1 ngay bat ky, khong can suy doan.

API: https://api.baoquangninh.vn/api/schedules/get/list?channel=<id>&date=<YYYYMMDD>
  - channel=1 -> QTV1 HD (Quang Ninh 1)
  - channel=2 -> QTV3 HD (Quang Ninh 3)

Ten file: "<Ten kenh>EPG<ddMMyyyy>.xls" (vi du: "QUANG NINH 1EPG28082026.xls")

Usage:
    python3 fetch_quangninh_schedule.py --output-dir ./output
    python3 fetch_quangninh_schedule.py --output-dir ./output --date 2026-08-28

Requires: requests, xlwt (va fetch_tv_schedule.py trong cung thu muc scripts/)
    pip install --break-system-packages requests xlwt
"""

import argparse
import datetime
import sys
from pathlib import Path

import requests

from fetch_tv_schedule import write_xls, safe_filename_part

API_URL = "https://api.baoquangninh.vn/api/schedules/get/list"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://baoquangninh.vn/truyen-hinh/",
}

# (ten kenh xuat ra file, channel id tren API)
CHANNELS = [
    ("QUANG NINH 1", 1),
    ("QUANG NINH 3", 2),
]


def fetch_schedule(session: requests.Session, channel_id: int, date: datetime.date, timeout: int = 15, retries: int = 2):
    """Tra ve list of (start_time 'HH:MM', program) da sap xep tang dan, cho dung 1 ngay."""
    params = {"channel": channel_id, "date": int(date.strftime("%Y%m%d"))}
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(API_URL, params=params, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                continue
            raise last_err
    schedules = data.get("data", {}).get("schedules", [])
    pairs = [(s["start_time"], s["name"]) for s in schedules if s.get("start_time")]
    pairs.sort(key=lambda p: p[0])
    return pairs


def build_epg_rows(schedule_pairs, base_date: datetime.date):
    """Giong logic trong fetch_tv_schedule.py: tinh Thoi luong = khoang cach den
    chuong trinh ke tiep, dong cuoi cat tai 23:59:59 cua cung ngay."""
    rows = []
    for i, (time_text, program) in enumerate(schedule_pairs):
        hh, mm = map(int, time_text.split(":"))
        dt = datetime.datetime(base_date.year, base_date.month, base_date.day, hh, mm, 0)
        if i + 1 < len(schedule_pairs):
            next_hh, next_mm = map(int, schedule_pairs[i + 1][0].split(":"))
            next_dt = datetime.datetime(base_date.year, base_date.month, base_date.day, next_hh, next_mm, 0)
            duration = next_dt - dt
        else:
            end_of_day = datetime.datetime(dt.year, dt.month, dt.day, 23, 59, 59)
            duration = end_of_day - dt
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
    parser.add_argument("--output-dir", default="./output", help="Thu muc de luu file .xls")
    parser.add_argument("--date", default=None, help="Ngay can lay lich, dang YYYY-MM-DD (mac dinh: hom nay)")
    args = parser.parse_args()

    target_date = (
        datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date else datetime.date.today()
    )
    date_stamp = target_date.strftime("%d%m%Y")
    out_dir = Path(args.output_dir) / target_date.isoformat()

    session = requests.Session()
    success = []
    failures = []

    for idx, (channel_name, channel_id) in enumerate(CHANNELS, start=1):
        try:
            schedule = fetch_schedule(session, channel_id, target_date)
            if not schedule:
                raise ValueError("khong co du lieu lich cho ngay nay")
            epg_rows = build_epg_rows(schedule, target_date)
            filename = f"{safe_filename_part(channel_name)}EPG{date_stamp}.xls"
            file_path = out_dir / filename
            write_xls(file_path, epg_rows)
            success.append((channel_name, file_path, len(epg_rows)))
            print(f"[{idx}/{len(CHANNELS)}] OK  - {channel_name}: {len(epg_rows)} muc lich -> {file_path}")
        except Exception as e:  # noqa: BLE001
            failures.append((channel_name, str(e)))
            print(f"[{idx}/{len(CHANNELS)}] LOI - {channel_name}: {e}", file=sys.stderr)

    print("\n===== TONG KET =====")
    print(f"Thanh cong: {len(success)}/{len(CHANNELS)} kenh")
    print(f"Thu muc output: {out_dir.resolve()}")
    if failures:
        print(f"\nCac kenh loi ({len(failures)}):")
        for name, err in failures:
            print(f"  - {name}: {err}")


if __name__ == "__main__":
    main()
