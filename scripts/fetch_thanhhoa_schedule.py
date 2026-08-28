#!/usr/bin/env python3
"""
fetch_thanhhoa_schedule.py

Lay lich phat song kenh truyen hinh Thanh Hoa tu API cua baothanhhoa.vn va
xuat ra file .xls (dinh dang Excel 97-2003 chuan), dung cau truc file EPG
mau: 3 dong trong, 1 dong tieu de, cac cot
ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.

API (JSON, khong phai JSONP): https://baothanhhoa.vn/ptth/lich-phat-song/truyen-hinh/<D>/<M>/<Y>
(header Accept: application/json)

Ho tro loc dung theo ngay (phan duong dan D/M/Y), khong can suy doan qua
dem nhu voi baomoi.com. API khong tra ve duration, nen tinh Thoi luong =
khoang cach den chuong trinh ke tiep (giong logic build_epg_rows cua
fetch_quangninh_schedule.py). Kenh nay thuong khong phat truoc 04:00 sang
(off-air), nen file co the bat dau tu 04:00 thay vi 00:00 - la dung theo
lich phat that cua kenh, khong phai thieu du lieu.

Ten file: "THANH HOAEPG<ddMMyyyy>.xls"

Usage:
    python3 fetch_thanhhoa_schedule.py --output-dir ./output
    python3 fetch_thanhhoa_schedule.py --output-dir ./output --date 2026-08-28

Requires: requests, xlwt (va fetch_tv_schedule.py, fetch_quangninh_schedule.py
trong cung thu muc scripts/)
    pip install --break-system-packages requests xlwt
"""

import argparse
import datetime
import html
import sys
from pathlib import Path

import requests

from fetch_tv_schedule import write_xls, safe_filename_part
from fetch_quangninh_schedule import build_epg_rows

CHANNEL_NAME = "THANH HOA"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://baothanhhoa.vn/ptth/",
}


def build_url(date: datetime.date) -> str:
    return (
        f"https://baothanhhoa.vn/ptth/lich-phat-song/truyen-hinh/"
        f"{date.day}/{date.month}/{date.year}"
    )


def fetch_schedule(session: requests.Session, date: datetime.date, timeout: int = 15, retries: int = 2):
    """Tra ve list of (start_time 'HH:MM', program) da sap xep tang dan, cho dung 1 ngay."""
    url = build_url(date)
    last_err = None
    data = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                continue
            raise last_err

    items = data.get("items", [])
    pairs = []
    for it in items:
        time_text = it.get("time", "")
        title = html.unescape(it.get("title", "").strip())
        if not time_text or not title:
            continue
        pairs.append((time_text, title))

    pairs.sort(key=lambda p: p[0])
    return pairs


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
    try:
        schedule = fetch_schedule(session, target_date)
        if not schedule:
            raise ValueError("khong co du lieu lich cho ngay nay")
        epg_rows = build_epg_rows(schedule, target_date)
        filename = f"{safe_filename_part(CHANNEL_NAME)}EPG{date_stamp}.xls"
        file_path = out_dir / filename
        write_xls(file_path, epg_rows)
        print(f"OK  - {CHANNEL_NAME}: {len(epg_rows)} muc lich -> {file_path}")
    except Exception as e:  # noqa: BLE001
        print(f"LOI - {CHANNEL_NAME}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
