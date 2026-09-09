#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_haiphong_schedule.py

Lay lich phat song hai kenh truyen hinh Hai Phong tu trang chinh thuc
https://thhp.vn/ (khong dung baomoi cho hai kenh nay nua) va xuat moi kenh
thanh 1 file .xls dung cau truc EPG mau.

Nguon la mot API JSON sach:
    GET https://thhp.vn/schedule/list?type=video&dateplay=YYYY-MM-DD&channel=N
    -> {"schedule_data": [{"frame":"00:06","program":"...","duration":900,...}, ...]}

Hai kenh video cua thhp.vn:
    channel=1  THP   -> EPG "HAI PHONG 1" (service 822)
    channel=2  THP+  -> EPG "HAI PHONG 3" (service 823)
(channel 3,4 la phat thanh FM, khong lay.)

Thoi luong tinh theo "moc ke tiep tru moc nay" (giong cac script khac, va
giong cach EPG hieu lich phat song) chu khong dung truong duration cua API
— truong do la do dai chuong trinh that, co the chong lan/ho giua cac muc.

Usage:
    python3 fetch_haiphong_schedule.py --output-dir ./output
    python3 fetch_haiphong_schedule.py --output-dir ./output --date 2026-09-09

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

API_URL = "https://thhp.vn/schedule/list"

# (Ten kenh dung DUNG nhu EPG de khop file, tham so channel cua API)
CHANNELS = [
    ("HAI PHONG 1", "1"),   # THP
    ("HAI PHONG 3", "2"),   # THP+
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://thhp.vn/lich-phat-song",
}

_HHMM = None


def fetch_schedule(session, channel, target_date, timeout=15, retries=2):
    """Goi API, tra ve list (time_text 'HH:MM', program). Da sap tang dan."""
    import re
    global _HHMM
    if _HHMM is None:
        _HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")

    params = {"type": "video", "dateplay": target_date.isoformat(),
              "channel": channel}
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(API_URL, headers=HEADERS, params=params,
                               timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("schedule_data") or []
            pairs = []
            for it in items:
                frame = (it.get("frame") or "").strip()
                program = (it.get("program") or "").strip()
                if not program or not _HHMM.match(frame):
                    continue
                pairs.append((frame, program))
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
