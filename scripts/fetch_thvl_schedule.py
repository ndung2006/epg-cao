#!/usr/bin/env python3
"""
fetch_thvl_schedule.py

Lay lich phat song 2 kenh Vinh Long (THVL1, THVL2) tu API cua thvli.vn va
xuat ra file .xls (dinh dang Excel 97-2003 chuan) rieng biet cho tung kenh,
dung cau truc file EPG mau: 3 dong trong, 1 dong tieu de, cac cot
ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.

API: https://api.thvli.vn/backend/cm/epg/?channel_id=<id>&schedule_date=<YYYY-MM-DD>&platform=web
Yeu cau 2 header ky (tim thay trong main.*.chunk.js cua www.thvli.vn):
  X-SFD-Date = <YYYYMMDD><HHMMSS> (thoi diem goi request)
  X-SFD-Key  = MD5("Kh0ngDuLieu"+YYYYMMDD+"C0R0i"+HHMMSS+"Kh0aAnT0an"+d[:3]+d[-3:])
               voi d = MD5(YYYYMMDD+HHMMSS)
Channel_id lay tu API danh sach kenh (ribbon), match theo "slug" (thvl1-hd,
thvl2-hd) de khong phai hardcode - phong khi id doi.

Ho tro loc dung theo ngay (tham so schedule_date), khong can suy doan qua
dem nhu voi baomoi.com. Moi muc co start_at la unix timestamp (giay), khong
co truong ket thuc/duration nen tinh Thoi luong = khoang cach den chuong
trinh ke tiep (dong cuoi cat tai 23:59:59 cua cung ngay).

Ten file: "<Ten kenh>EPG<ddMMyyyy>.xls"

Usage:
    python3 fetch_thvl_schedule.py --output-dir ./output
    python3 fetch_thvl_schedule.py --output-dir ./output --date 2026-08-28

Requires: requests, xlwt (va fetch_tv_schedule.py trong cung thu muc scripts/)
    pip install --break-system-packages requests xlwt
"""

import argparse
import datetime
import hashlib
import sys
from pathlib import Path

import requests

from fetch_tv_schedule import write_xls, safe_filename_part

API_BASE = "https://api.thvli.vn/backend/cm/"
RIBBON_ID = "a6ccbdff-5688-4b25-9989-5ce872603b0a"  # "Kenh THVL" - danh sach kenh
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# (ten kenh xuat ra file, slug kenh tren thvli.vn)
CHANNELS = [
    ("VINH LONG 1 HD", "thvl1-hd"),
    ("VINH LONG 2 HD", "thvl2-hd"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.thvli.vn/",
}


def sign_headers(now: datetime.datetime = None) -> dict:
    """Tao 2 header X-SFD-Date / X-SFD-Key ma api.thvli.vn yeu cau, dua theo
    thuat toan doc duoc trong main.*.chunk.js cua www.thvli.vn."""
    now = now or datetime.datetime.now()
    date_part = now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M%S")
    d = hashlib.md5((date_part + time_part).encode()).hexdigest()
    salted = (
        "Kh0ngDuLieu" + date_part + "C0R0i" + time_part + "Kh0aAnT0an"
        + d[:3] + d[-3:]
    )
    key = hashlib.md5(salted.encode()).hexdigest()
    return {"X-SFD-Date": date_part + time_part, "X-SFD-Key": key}


def api_get(session: requests.Session, path: str, params: dict, timeout: int = 15, retries: int = 2):
    last_err = None
    for attempt in range(retries + 1):
        try:
            headers = dict(HEADERS)
            headers.update(sign_headers())
            resp = session.get(API_BASE + path, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                continue
            raise last_err


def get_channel_id(session: requests.Session, slug: str) -> str:
    data = api_get(session, f"ribbon/{RIBBON_ID}/", {"platform": "web"})
    for item in data.get("items", []):
        if item.get("slug") == slug:
            return item["id"]
    raise ValueError(f"khong tim thay slug '{slug}' trong danh sach kenh THVL")


def fetch_schedule(session: requests.Session, channel_id: str, date: datetime.date):
    """Tra ve list of (start_time 'HH:MM', program) da sap xep tang dan, cho dung 1 ngay."""
    data = api_get(session, "epg/", {
        "channel_id": channel_id,
        "schedule_date": date.isoformat(),
        "platform": "web",
    })
    items = data.get("items", [])
    pairs = []
    for it in items:
        start_at = it.get("start_at")
        title = (it.get("title") or "").strip()
        if start_at is None or not title:
            continue
        dt_local = datetime.datetime.fromtimestamp(start_at, VN_TZ)
        pairs.append((dt_local.strftime("%H:%M"), title))
    pairs.sort(key=lambda p: p[0])
    return pairs


def build_epg_rows(schedule_pairs, base_date: datetime.date):
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
    for idx, (channel_name, slug) in enumerate(CHANNELS, start=1):
        try:
            channel_id = get_channel_id(session, slug)
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
