#!/usr/bin/env python3
"""
fetch_sctv_schedule.py

Lay lich phat song 2 kenh SCTV9 va SCTV14 tu API cua sctv.com.vn va xuat ra
file .xls (dinh dang Excel 97-2003 chuan) rieng biet cho tung kenh, dung
cau truc file EPG mau: 3 dong trong, 1 dong tieu de, cac cot
ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.

API (JSON, POST):
  - Danh sach kenh: https://www.sctv.com.vn/WebMain/Kenh/LayDSKenhCoLPS  (body {})
    -> tra ve {"DSKenh": [{"Ma": <int>, "TenNgan": "SCTV9", ...}, ...]}
    Dung de tim "Ma" (maKenh) theo TenNgan, khong hardcode phong khi doi.
  - Lich phat song: https://www.sctv.com.vn/WebMain/LichPhatSong/LayLichPhatSong
    body {"maKenh": <ma>, "ngay": "<YYYY-MM-DD>"}
    -> tra ve {"LichPhatSong": {"EventList": [{"StartTime": "HH:MM:SS",
       "EndTime": "HH:MM:SS", "Name": "..."}]}}

Khac voi cac nguon khac, API nay da cho san ca StartTime lan EndTime cho
tung chuong trinh (co the co khoang trong giua 2 chuong trinh lien tiep -
vd 01:15 den 01:30 khong co du lieu), nen Thoi luong = EndTime - StartTime
theo dung nguon, khong tinh theo khoang cach den dong ke tiep. Dong cuoi
ngay neu EndTime vat sang hom sau (vd 23:30 -> 00:15) thi cat tai 23:59:59
cua cung ngay.

Ten file: "<Ten kenh>EPG<ddMMyyyy>.xls"

Usage:
    python3 fetch_sctv_schedule.py --output-dir ./output
    python3 fetch_sctv_schedule.py --output-dir ./output --date 2026-08-28

Requires: requests, xlwt (va fetch_tv_schedule.py trong cung thu muc scripts/)
    pip install --break-system-packages requests xlwt
"""

import argparse
import datetime
import sys
from pathlib import Path

import requests

from fetch_tv_schedule import write_xls, safe_filename_part

API_BASE = "https://www.sctv.com.vn/WebMain"

# (ten kenh xuat ra file, TenNgan tren sctv.com.vn de tra Ma kenh)
CHANNELS = [
    ("SCTV9", "SCTV9"),
    ("SCTV14", "SCTV14"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Content-Type": "application/json; charset=utf-8",
    "Referer": "https://www.sctv.com.vn/lich-phat-song",
}


def api_post(session: requests.Session, path: str, payload: dict, timeout: int = 15, retries: int = 2):
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.post(API_BASE + path, headers=HEADERS, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                continue
            raise last_err


def get_channel_code(session: requests.Session, ten_ngan: str) -> int:
    data = api_post(session, "/Kenh/LayDSKenhCoLPS", {})
    for kenh in data.get("DSKenh", []):
        if kenh.get("TenNgan") == ten_ngan:
            return kenh["Ma"]
    raise ValueError(f"khong tim thay kenh '{ten_ngan}' tren sctv.com.vn")


def fetch_schedule(session: requests.Session, ma_kenh: int, date: datetime.date):
    """Tra ve list of (start_time 'HH:MM', end_time 'HH:MM', program), da sap xep tang dan."""
    data = api_post(session, "/LichPhatSong/LayLichPhatSong", {
        "maKenh": ma_kenh,
        "ngay": date.isoformat(),
    })
    events = data.get("LichPhatSong", {}).get("EventList") or []
    triples = []
    for ev in events:
        start = ev.get("StartTime", "")[:5]
        end = ev.get("EndTime", "")[:5]
        name = (ev.get("Name") or "").strip()
        if not start or not end or not name:
            continue
        triples.append((start, end, name))
    triples.sort(key=lambda t: t[0])
    return triples


def build_epg_rows(schedule_triples, base_date: datetime.date):
    """Thoi luong = EndTime - StartTime theo dung nguon; neu EndTime vat sang
    hom sau thi cat tai 23:59:59 cua cung ngay."""
    rows = []
    for i, (start_text, end_text, program) in enumerate(schedule_triples):
        sh, sm = map(int, start_text.split(":"))
        start_dt = datetime.datetime(base_date.year, base_date.month, base_date.day, sh, sm, 0)
        eh, em = map(int, end_text.split(":"))
        end_dt = datetime.datetime(base_date.year, base_date.month, base_date.day, eh, em, 0)
        if end_dt <= start_dt:
            end_dt = datetime.datetime(base_date.year, base_date.month, base_date.day, 23, 59, 59)
        rows.append({
            "id": i + 1,
            "start_dt": start_dt,
            "duration": end_dt - start_dt,
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
    for idx, (channel_name, ten_ngan) in enumerate(CHANNELS, start=1):
        try:
            ma_kenh = get_channel_code(session, ten_ngan)
            schedule = fetch_schedule(session, ma_kenh, target_date)
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
