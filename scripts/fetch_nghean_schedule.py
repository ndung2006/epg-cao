#!/usr/bin/env python3
"""
fetch_nghean_schedule.py

Lay lich phat song kenh truyen hinh Nghe An (NTV) tu API cua
truyenhinhnghean.vn va xuat ra file .xls (dinh dang Excel 97-2003 chuan),
dung cau truc file EPG mau: 3 dong trong, 1 dong tieu de, cac cot
ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.

API (JSONP): https://truyenhinhnghean.vn/sc_service/api/tvshow/list
  ?scUnitMapId=4028eaa46735a26101673a4df345003c
  &timeBegin=<DD/MM/YYYY>
  &tvchannelName=ngheantv
  &jsonCallback=jsonCallback

Ho tro loc dung theo ngay (tham so timeBegin), khong can suy doan qua dem
nhu voi baomoi.com. Truong "duration" nguon tra ve luon co gia tri co dinh
(30), khong dang tin cay, nen tinh Thoi luong = khoang cach den chuong
trinh ke tiep (giong logic build_epg_rows cua fetch_quangninh_schedule.py).

Ten file: "NGHE ANEPG<ddMMyyyy>.xls"

Usage:
    python3 fetch_nghean_schedule.py --output-dir ./output
    python3 fetch_nghean_schedule.py --output-dir ./output --date 2026-08-28

Requires: requests, xlwt (va fetch_tv_schedule.py, fetch_quangninh_schedule.py
trong cung thu muc scripts/)
    pip install --break-system-packages requests xlwt
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

import requests

from fetch_tv_schedule import write_xls, safe_filename_part
from fetch_quangninh_schedule import build_epg_rows

CHANNEL_NAME = "NGHE AN"
API_URL = "https://truyenhinhnghean.vn/sc_service/api/tvshow/list"
SC_UNIT_MAP_ID = "4028eaa46735a26101673a4df345003c"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://truyenhinhnghean.vn/",
}


def fetch_schedule(session: requests.Session, date: datetime.date, timeout: int = 15, retries: int = 2):
    """Tra ve list of (start_time 'HH:MM', program) da sap xep tang dan, cho dung 1 ngay."""
    params = {
        "scUnitMapId": SC_UNIT_MAP_ID,
        "timeBegin": date.strftime("%d/%m/%Y"),
        "tvchannelName": "ngheantv",
        "jsonCallback": "jsonCallback",
    }
    last_err = None
    text = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(API_URL, params=params, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            text = resp.text.strip()
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                continue
            raise last_err

    if not (text.startswith("jsonCallback(") and text.endswith(")")):
        raise ValueError("phan hoi khong dung dinh dang JSONP mong doi")
    data = json.loads(text[len("jsonCallback("):-1])
    items = data.get("response", [])

    pairs = []
    for it in items:
        time_begin = it.get("timeBegin", "")
        title = it.get("title", "").strip()
        if not time_begin or not title:
            continue
        # dang "DD/MM/YYYY HH:MM:SS" -> lay phan HH:MM
        time_part = time_begin.split(" ")[-1]
        hh_mm = ":".join(time_part.split(":")[:2])
        pairs.append((hh_mm, title))

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
