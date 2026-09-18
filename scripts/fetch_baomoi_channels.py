#!/usr/bin/env python3
"""
fetch_baomoi_channels.py

Lay lich phat song 28 kenh (trong danh sach 44 kenh yeu cau) van con dung
nguon baomoi.com, theo dung mapping ten kenh da duoc nguoi dung xac nhan
thu cong truoc do. Cac kenh da chuyen sang nguon rieng (VTV1/2/3/5/6/9/10,
Quang Ninh 1/3, Nghe An, Thanh Hoa, Vinh Long 1/2, SCTV9/14, Vietnam Today)
KHONG nam trong danh sach nay - xem cac script fetch_*_schedule.py tuong ung.
(Vietnam Today truoc day lay tu vietnamtoday.vtv.vn, nay chuyen sang TV360
cung voi Dong Nai, ON Football... trong fetch_tv360_schedule.py.)

Mapping (ten kenh xuat file -> ten kenh hien thi tren baomoi.com):
  - Hai Phong 1/3 va An Giang 1/3: baomoi chi co 1 kenh chung cho moi tinh,
    dung chung 1 nguon cho ca 2 so (nguoi dung da xac nhan).
  - Bac Ninh: sau sap nhap tinh, dung chung nguon voi Bac Giang tren baomoi.
  - Lam Dong 2: dung nguon Binh Thuan tren baomoi (nguoi dung da xac nhan).
  - On Sports / On Sport News / On Football: ten hien thi tren baomoi khac
    ten thong dung (Thể Thao TV / Thể thao Tin tức / Bóng đá TV).

Ten file: "<Ten kenh>EPG<ddMMyyyy>.xls" (dung ten kenh theo danh sach yeu cau,
khong phai ten hien thi tren baomoi).

Usage:
    python3 fetch_baomoi_channels.py --output-dir ./output
    python3 fetch_baomoi_channels.py --output-dir ./output --date 2026-09-08

Requires: requests, beautifulsoup4, xlwt (va fetch_tv_schedule.py trong cung
thu muc scripts/)
    pip install --break-system-packages requests beautifulsoup4 xlwt
"""

import argparse
import datetime
import sys
from pathlib import Path

import requests

from fetch_tv_schedule import discover_channels, fetch, parse_schedule, build_epg_rows, write_xls, safe_filename_part

# (ten kenh xuat file, ten kenh hien thi tren baomoi.com)
CHANNELS = [
    ("ANTV HD", "ANTV"),
    ("QPVN HD", "QPVN (HD)"),
    ("HTV2", "HTV2 (HD)"),
    ("VTVcab8-BIBI", "VTVcab8 - BIBI"),
    ("QUANG TRI", "QuangTriTV (QRTV)"),
    ("PHU THO", "PhuThoTV (PTV) (HD)"),
    ("LAO CAI", "LaoCaiTV (THLC)"),
    ("SON LA", "SonLaTV (STV)"),
    ("TUYEN QUANG", "TuyenQuangTV (TTV)"),
    ("CAO BANG", "CaoBangTV (CRTV)"),
    ("DAKLAK", "DakLakTV (DRT)"),
    ("LAM DONG", "LamDongTV (LDTV)"),
    ("NINH BINH", "NinhBinhTV (NTB)"),
    ("THAI NGUYEN", "ThaiNguyenTV1 (TV1) (HD)"),
    ("LAI CHAU", "LaiChauTV (LTV)"),
    ("HAI PHONG 1", "HaiPhongTV (THP) (HD)"),
    ("HAI PHONG 3", "HaiPhongTV (THP) (HD)"),
    ("AN GIANG 1", "AnGiangTV (ATV)"),
    ("AN GIANG 3", "AnGiangTV (ATV)"),
    ("LAM DONG 2", "BinhThuanTV (BTV)"),
    ("BAC NINH", "BacGiangTV (BGTV)"),
]


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
    print("Dang lay danh sach kenh tu baomoi.com ...")
    try:
        by_name = {name: url for url, name in discover_channels(session)}
    except Exception as e:  # noqa: BLE001
        print(f"LOI: khong the tai danh sach kenh baomoi: {e}", file=sys.stderr)
        sys.exit(1)

    success = []
    failures = []
    cache = {}
    for idx, (channel_name, baomoi_name) in enumerate(CHANNELS, start=1):
        try:
            url = by_name.get(baomoi_name)
            if not url:
                raise ValueError(f"khong tim thay '{baomoi_name}' tren baomoi.com")
            if url not in cache:
                html = fetch(session, url)
                schedule = parse_schedule(html)
                if not schedule:
                    raise ValueError("khong tach duoc bang gio/chuong trinh")
                cache[url] = build_epg_rows(schedule, target_date)
            epg_rows = cache[url]
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
