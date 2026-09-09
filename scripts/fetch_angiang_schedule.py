#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_angiang_schedule.py

Lay lich phat song hai kenh truyen hinh An Giang tu trang chinh thuc
https://angiangtv.vn/ (khong dung baomoi cho hai kenh nay nua) va xuat moi
kenh thanh 1 file .xls dung cau truc EPG mau.

Sau khi tinh Kien Giang sap nhap vao An Giang, dai phat hai kenh hinh:
    kenh=TV   (nhan tren web: "KG")  -> EPG "AN GIANG 1" (service 840) = ATV1
    kenh=TV2  (nhan tren web: "KG1") -> EPG "AN GIANG 3" (service 841) = ATV3
(kenh=Radio la FM phat thanh, khong lay.)

Trang la WordPress, lich render san trong HTML theo tham so GET:
    GET https://angiangtv.vn/lich-phat-song?ngay=YYYY-MM-DD&kenh=TV
    -> <div class="lps-body"><h4>KG - ngay ...</h4><div class="table">
         <div class="tbl-row"><div class="time">05:15</div>
                              <div class="program">...</div></div> ...

Thoi luong tinh theo "moc ke tiep tru moc nay" (giong cac script khac va
giong cach EPG hieu lich phat song) — dung build_epg_rows chung.

Usage:
    python3 fetch_angiang_schedule.py --output-dir ./output
    python3 fetch_angiang_schedule.py --output-dir ./output --date 2026-09-09

Requires: requests, beautifulsoup4 (va fetch_tv_schedule.py +
fetch_quangninh_schedule.py trong cung thu muc scripts/).
"""

import argparse
import datetime
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from fetch_tv_schedule import write_xls, safe_filename_part
from fetch_quangninh_schedule import build_epg_rows

PAGE_URL = "https://angiangtv.vn/lich-phat-song"

# (Ten kenh dung DUNG nhu EPG de khop file, tham so kenh cua web)
CHANNELS = [
    ("AN GIANG 1", "TV"),    # web "KG"  = ATV1
    ("AN GIANG 3", "TV2"),   # web "KG1" = ATV3
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": PAGE_URL,
}

_HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def fetch_schedule(session, kenh, target_date, timeout=20, retries=2):
    """Goi trang, tra ve list (time_text 'HH:MM', program). Da sap tang dan."""
    params = {"ngay": target_date.isoformat(), "kenh": kenh}
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(PAGE_URL, headers=HEADERS, params=params,
                               timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            body = soup.find("div", class_="lps-body")
            pairs = []
            for row in (body.find_all("div", class_="tbl-row") if body else []):
                t = row.find("div", class_="time")
                p = row.find("div", class_="program")
                if t is None or p is None:
                    continue
                frame = t.get_text(strip=True)
                program = p.get_text(" ", strip=True)
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

    for idx, (channel_name, kenh) in enumerate(CHANNELS, start=1):
        try:
            schedule = fetch_schedule(session, kenh, target_date)
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
