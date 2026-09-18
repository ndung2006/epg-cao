#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_tv360_schedule.py

Lay lich phat song cac kenh co nguon tot hon tren TV360 (tv360.vn) —
khong dung baomoi cho nhung kenh nay nua — va xuat moi kenh thanh 1 file
.xls dung cau truc EPG mau.

Nguon la API JSON cong khai cua TV360 (tim thay trong bundle JS cua trang
https://tv360.vn/tv/dong-nai-1?ch=53, ham getScheduleCategory):
    GET https://tv360.vn/public/v1/live/get-live-schedule?id=<ch>&datetime=<YYYY-MM-DD>
    -> {"errorCode":200,"data":{"schedules":[
           {"name":"...","description":"","startTime":"00:00","endTime":"00:20",
            "datetime":"2026-09-16", ...}, ...]}}

Cac kenh dang lay (id lay tu tham so ?ch= tren URL trang kenh):
    ch=53   tv360.vn/tv/dong-nai-1                -> EPG "DONG NAI 1"
    ch=255  tv360.vn/tv/dong-nai                  -> EPG "DONG NAI 2"
    ch=174  tv360.vn/tv/vtvcab-16-hd              -> EPG "ON FOOTBALL"
    ch=170  tv360.vn/tv/vtvcab-18-on-sports-news  -> EPG "ON SPORT NEWS"
    ch=173  tv360.vn/tv/vtvcab-3-on-sports        -> EPG "ON SPORTS"
    ch=9951 tv360.vn/tv/vietnam-today-hd          -> EPG "Vietnam Today"
(Trang ch=255 co detail.name la "Dong Nai" nhung title trang la "dong nai 2".)
(Vietnam Today truoc day lay tu vietnamtoday.vtv.vn nhung API do khong on dinh,
chuyen sang TV360 cho do tin cay — cung API, cung format nhu cac kenh khac.)

Thoi luong tinh theo "moc ke tiep tru moc nay" (dung build_epg_rows chung nhu
cac script khac). Lich TV360 lien mach (endTime = startTime cua muc ke tiep)
nen ket qua trung khop voi endTime cua nguon; rieng muc cuoi nguon de 23:59
con file xuat ra cat tai 23:59:59 dung quy uoc chung cua du an.

Usage:
    python3 fetch_tv360_schedule.py --output-dir ./output
    python3 fetch_tv360_schedule.py --output-dir ./output --date 2026-09-16

Requires: requests (va fetch_tv_schedule.py + fetch_quangninh_schedule.py
trong cung thu muc scripts/).
"""

import argparse
import datetime
import re
import sys
import time
from pathlib import Path

import requests

from fetch_tv_schedule import write_xls, safe_filename_part
from fetch_quangninh_schedule import build_epg_rows

API_URL = "https://tv360.vn/public/v1/live/get-live-schedule"

# (Ten kenh dung DUNG nhu EPG de khop file, id kenh tren tv360.vn)
CHANNELS = [
    ("DONG NAI 1", 53),
    ("DONG NAI 2", 255),
    ("ON FOOTBALL", 174),
    ("ON SPORT NEWS", 170),
    ("ON SPORTS", 173),
    ("Vietnam Today", 9951),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://tv360.vn/",
}

HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def fetch_schedule(session, channel_id, target_date, timeout=20, retries=2):
    """Goi API, tra ve list (time_text 'HH:MM', program). Da sap tang dan."""
    day = target_date.isoformat()
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(API_URL, headers=HEADERS,
                               params={"id": channel_id, "datetime": day},
                               timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            items = (data.get("data") or {}).get("schedules") or []
            pairs = []
            for it in items:
                start = (it.get("startTime") or "").strip()
                name = (it.get("name") or "").strip()
                # API chi tra ve dung ngay duoc hoi, nhung van chan cho chac
                if not name or not HHMM.match(start):
                    continue
                if (it.get("datetime") or day) != day:
                    continue
                desc = (it.get("description") or "").strip()
                pairs.append((start, "%s: %s" % (name, desc) if desc else name))
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

    for idx, (channel_name, channel_id) in enumerate(CHANNELS, start=1):
        try:
            schedule = fetch_schedule(session, channel_id, target_date)
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
