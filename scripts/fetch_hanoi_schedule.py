#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_hanoi_schedule.py

Lay lich phat song hai kenh truyen hinh Ha Noi tu trang chinh thuc
https://hanoionline.vn/ (khong dung baomoi cho hai kenh nay nua) va xuat moi
kenh thanh 1 file .xls dung cau truc EPG mau.

Nguon la mot API JSON sach (tim thay trong /js/Home/index.js):
    GET https://hanoionline.vn/api/Schedule/listschedule/?key=<MA_KENH>_<DD_MM_YYYY>
    -> {"Code":1,"Data":[{"Name":"...","Description":"...",
                          "StartTime":"2026-09-16T00:10:00",
                          "EndTime":"2026-09-16T00:20:00", ...}, ...]}

Hai kenh truyen hinh (ma lay tu thuoc tinh data-show cua .channel-btn):
    HN1 -> EPG "HA NOI 1"
    HN2 -> EPG "HA NOI 2"
(FM90, FM96 la phat thanh, khong lay.)

Ten chuong trinh ghep "Name: Description" khi co Description, cho khop cach
baomoi truoc day xuat ("Phim truyen hinh : Phu sa ngot ... tap 54") va giong
quy uoc cua fetch_vtv_schedule.py.

Thoi luong tinh theo "moc ke tiep tru moc nay" (dung build_epg_rows chung nhu
cac script khac). Lich cua hanoionline.vn lien mach (EndTime = StartTime cua
muc ke tiep) va muc cuoi da ket thuc luc 23:59:59, nen ket qua trung khop
voi EndTime cua nguon.

Usage:
    python3 fetch_hanoi_schedule.py --output-dir ./output
    python3 fetch_hanoi_schedule.py --output-dir ./output --date 2026-09-16

Requires: requests (va fetch_tv_schedule.py + fetch_quangninh_schedule.py
trong cung thu muc scripts/).
"""

import argparse
import datetime
import sys
import time
from pathlib import Path

import requests

from fetch_tv_schedule import write_xls, safe_filename_part
from fetch_quangninh_schedule import build_epg_rows

API_URL = "https://hanoionline.vn/api/Schedule/listschedule/"

# (Ten kenh dung DUNG nhu EPG de khop file, ma kenh cua hanoionline.vn)
CHANNELS = [
    ("HA NOI 1", "HN1"),
    ("HA NOI 2", "HN2"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://hanoionline.vn/",
}


def fetch_schedule(session, channel_code, target_date, timeout=15, retries=2):
    """Goi API, tra ve list (time_text 'HH:MM', program). Da sap tang dan."""
    key = "%s_%s" % (channel_code, target_date.strftime("%d_%m_%Y"))
    day = target_date.isoformat()
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(API_URL, headers=HEADERS, params={"key": key},
                               timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("Data") or []
            pairs = []
            for it in items:
                start = (it.get("StartTime") or "").strip()
                name = (it.get("Name") or "").strip()
                # API chi tra ve dung ngay duoc hoi, nhung van chan cho chac
                if not name or not start.startswith(day):
                    continue
                desc = (it.get("Description") or "").strip()
                program = "%s: %s" % (name, desc) if desc else name
                pairs.append((start[11:16], program))   # "HH:MM"
            pairs.sort(key=lambda x: x[0])
            return pairs
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_err


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", default="./output",
                    help="Thu muc de luu file .xls")
    ap.add_argument("--date", default=None,
                    help="Ngay can lay, YYYY-MM-DD (mac dinh: hom nay)")
    args = ap.parse_args()

    target_date = (
        datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date else datetime.date.today()
    )
    date_stamp = target_date.strftime("%d%m%Y")
    out_dir = Path(args.output_dir) / target_date.isoformat()

    session = requests.Session()
    success, failures = [], []

    for idx, (channel_name, channel_code) in enumerate(CHANNELS, start=1):
        try:
            schedule = fetch_schedule(session, channel_code, target_date)
            if not schedule:
                raise ValueError("khong co du lieu lich cho ngay nay")
            epg_rows = build_epg_rows(schedule, target_date)
            filename = f"{safe_filename_part(channel_name)}EPG{date_stamp}.xls"
            file_path = out_dir / filename
            write_xls(file_path, epg_rows)
            print("[%d/%d] OK  - %s: %d muc lich -> %s"
                  % (idx, len(CHANNELS), channel_name, len(epg_rows), file_path))
            success.append(channel_name)
        except Exception as e:  # noqa: BLE001
            print("[%d/%d] LOI - %s: %s"
                  % (idx, len(CHANNELS), channel_name, e), file=sys.stderr)
            failures.append((channel_name, str(e)))

    print("\n===== TONG KET =====")
    print("Thanh cong: %d/%d kenh" % (len(success), len(CHANNELS)))
    print("Thu muc output: %s" % out_dir)
    if failures:
        print("\nCac kenh loi (%d):" % len(failures))
        for name, err in failures:
            print("  - %s: %s" % (name, err))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
