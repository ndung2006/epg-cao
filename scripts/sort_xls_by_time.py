#!/usr/bin/env python3
"""
sort_xls_by_time.py

Doc lai 1 file .xls EPG da xuat ra (dung cau truc: 3 dong trong, 1 dong tieu de,
5 cot ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh), sap xep lai
cac dong du lieu, danh lai ID theo thu tu moi, roi ghi de (hoac ghi ra file khac)
- khong can cao lai du lieu tu baomoi.com.

Vi baomoi.com luon tra ve lich bat dau tu thoi diem cao (khong phai tu 00:00),
du lieu mot file thuong vat qua 2 ngay lich (vd 10:40 hom nay -> 10:35 hom sau).
Mac dinh script sap xep theo GIO TRONG NGAY (bo qua ngay), de cot "Thoi gian bat
dau" chay lien tuc 00:00:00 -> 23:59:59 trong 1 file, dua doan "00:00 tro di"
(thuoc ngay hom sau) len dau. Dung --absolute neu muon giu thu tu ngay-gio thuc
(khong doi cho, chi sap xep lai neu du lieu bi dao lon).

Ho tro doc ca file cu (cot Ngay/Thoi luong la text) lan file moi (da la kieu
ngay/gio thuc cua Excel).

Usage:
    python3 sort_xls_by_time.py --file "output/2026-08-25/VTV1 (HD)EPG25082026.xls"
    python3 sort_xls_by_time.py --file input.xls --output input_sorted.xls
    python3 sort_xls_by_time.py --file input.xls --absolute

Requires: xlrd, xlwt (va fetch_tv_schedule.py trong cung thu muc scripts/)
    pip install --break-system-packages xlrd xlwt
"""

import argparse
import datetime
import os
import sys
from pathlib import Path

import xlrd

from fetch_tv_schedule import write_xls

HEADER_ROW_IDX = 3  # 3 dong dau (0,1,2) de trong, dong 3 (index) la tieu de
DATA_START_ROW = HEADER_ROW_IDX + 1

# Dinh dang chuoi cu (truoc khi fetch_tv_schedule.py ghi kieu ngay/gio thuc)
OLD_DATETIME_FMT = "%m/%d/%Y %H:%M:%S"


def parse_datetime_cell(cell, datemode) -> datetime.datetime:
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, datemode)
    if cell.ctype in (xlrd.XL_CELL_TEXT, xlrd.XL_CELL_NUMBER):
        return datetime.datetime.strptime(str(cell.value).strip(), OLD_DATETIME_FMT)
    raise ValueError(f"Khong doc duoc gia tri ngay/gio o cot Ngay: {cell.value!r}")


def parse_duration_cell(cell) -> datetime.timedelta:
    if cell.ctype == xlrd.XL_CELL_DATE:
        return datetime.timedelta(days=float(cell.value))
    if cell.ctype in (xlrd.XL_CELL_TEXT, xlrd.XL_CELL_NUMBER):
        h, m, s = (int(p) for p in str(cell.value).strip().split(":"))
        return datetime.timedelta(hours=h, minutes=m, seconds=s)
    raise ValueError(f"Khong doc duoc gia tri thoi luong: {cell.value!r}")


def read_epg_rows(path: Path):
    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)

    rows = []
    for r in range(DATA_START_ROW, ws.nrows):
        cells = ws.row(r)
        if all(c.ctype == xlrd.XL_CELL_EMPTY for c in cells):
            continue
        start_dt = parse_datetime_cell(cells[1], wb.datemode)
        duration = parse_duration_cell(cells[3])
        program = str(cells[4].value).strip()
        rows.append({"start_dt": start_dt, "duration": duration, "program": program})
    return rows


def main():
    # Ep UTF-8 cho stdout/stderr, tranh crash UnicodeEncodeError tren console
    # Windows (cp1252) khi in duong dan file co ten kenh dau tieng Viet.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="File .xls EPG can sap xep lai")
    parser.add_argument(
        "--output",
        default=None,
        help="Ghi ra file khac thay vi ghi de len --file (mac dinh: ghi de len chinh no)",
    )
    parser.add_argument(
        "--absolute",
        action="store_true",
        help="Sap xep theo ngay-gio thuc (tuyet doi) thay vi gio-trong-ngay (mac dinh)",
    )
    args = parser.parse_args()

    src_path = Path(args.file)
    if not src_path.exists():
        print(f"LOI: khong tim thay file {src_path}", file=sys.stderr)
        sys.exit(1)

    rows = read_epg_rows(src_path)
    if not rows:
        print(f"LOI: khong doc duoc dong du lieu nao tu {src_path}", file=sys.stderr)
        sys.exit(1)

    if args.absolute:
        rows.sort(key=lambda row: row["start_dt"])
        mode_desc = "ngay-gio tuyet doi"
    else:
        rows.sort(key=lambda row: row["start_dt"].time())
        mode_desc = "gio trong ngay (00:00:00 -> 23:59:59)"

    for i, row in enumerate(rows, start=1):
        row["id"] = i

    dest_path = Path(args.output) if args.output else src_path
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")
    write_xls(tmp_path, rows)
    os.replace(tmp_path, dest_path)

    print(f"Da sap xep lai {len(rows)} dong theo {mode_desc} -> {dest_path}")
    print(f"Dong dau: {rows[0]['start_dt']} | Dong cuoi: {rows[-1]['start_dt']}")


if __name__ == "__main__":
    main()
