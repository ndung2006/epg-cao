#!/usr/bin/env python3
"""
fetch_tv_schedule.py

Cao (scrape) lich phat song truyen hinh tu baomoi.com/tien-ich-lich-truyen-hinh.epi
va xuat moi kenh thanh 1 file .xls (dinh dang Excel 97-2003 chuan) rieng biet,
theo dung cau truc file EPG mau: 3 dong trong, 1 dong tieu de, cac cot
ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.

Ten file: "<Ten kenh>EPG<ddMMyyyy>.xls" (vi du: "VTV1 (HD)EPG20082026.xls")

Usage:
    python3 fetch_tv_schedule.py --output-dir ./output [--limit N] [--delay 0.7]

Requires: requests, beautifulsoup4, xlwt
    pip install --break-system-packages requests beautifulsoup4 xlwt
"""

import argparse
import datetime
import re
import sys
import time
from pathlib import Path

import requests
import xlwt
from bs4 import BeautifulSoup

BASE_URL = "https://baomoi.com/tien-ich-lich-truyen-hinh.epi"
CHANNEL_LINK_RE = re.compile(r"/tien-ich-lich-truyen-hinh-([a-z0-9\-]+)\.epi$", re.IGNORECASE)
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Ky tu khong duoc phep trong ten file tren Windows
INVALID_FILENAME_CHARS = '\\/:*?"<>|'


def safe_filename_part(text: str) -> str:
    cleaned = "".join(c for c in text if c not in INVALID_FILENAME_CHARS)
    return cleaned.strip()


def fetch(session: requests.Session, url: str, timeout: int = 15, retries: int = 2):
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_err


def discover_channels(session: requests.Session):
    """Tra ve list of (channel_url, channel_name), da loc trung theo TEN kenh.

    Khong tu dong them trang goc (BASE_URL) nhu mot kenh rieng nua, vi trang goc
    chi la ban hien thi mac dinh cua 1 kenh da co trong danh sach link (thuong la
    VTV1) -> neu them se bi trung du lieu voi ten file khac (vd "Lich truyen hinh").
    Chi dung trang goc lam kenh du phong khi khong tim thay link kenh nao ca.
    """
    html = fetch(session, BASE_URL)
    soup = BeautifulSoup(html, "html.parser")

    seen_names = set()
    channels = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not CHANNEL_LINK_RE.search(href):
            continue
        if href.startswith("http"):
            full_url = href
        else:
            full_url = "https://baomoi.com" + (href if href.startswith("/") else "/" + href)
        name = a.get_text(strip=True) or CHANNEL_LINK_RE.search(href).group(1)

        key = name.strip().lower()
        if not key or key in seen_names:
            # Bo qua kenh trung ten (vd baomoi co 2 link cung tro ve "VTVcab10")
            continue
        seen_names.add(key)
        channels.append((full_url, name))

    if not channels:
        # Truong hop hiem: khong tim thay link kenh nao -> dung chinh trang goc
        title_tag = soup.find("h1") or soup.title
        default_name = title_tag.get_text(strip=True) if title_tag else "Trang chinh"
        channels.append((BASE_URL, default_name))

    return channels


def parse_schedule(html: str):
    """Tra ve list of (gio 'HH:MM', chuong_trinh) theo thu tu xuat hien tren trang."""
    soup = BeautifulSoup(html, "html.parser")
    rows_out = []

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        time_text = cells[0].get_text(strip=True)
        if not TIME_RE.match(time_text):
            continue
        program_text = " ".join(c.get_text(" ", strip=True) for c in cells[1:]).strip()
        if program_text:
            rows_out.append((time_text, program_text))

    return rows_out


def build_epg_rows(schedule_pairs, base_date: datetime.date):
    """
    Gan ngay thuc te cho tung dong (xu ly qua dem khi gio bi lap lai/nho hon dong truoc),
    tinh 'Thoi luong' = khoang cach den chuong trinh ke tiep (dong cuoi tinh den het ngay).
    Tra ve list dict: id, start_dt (datetime), duration (timedelta), program (str).
    """
    parsed_times = []
    current_date = base_date
    prev_dt = None

    for time_text, _program in schedule_pairs:
        hh, mm = map(int, time_text.split(":"))
        dt = datetime.datetime(current_date.year, current_date.month, current_date.day, hh, mm, 0)
        if prev_dt is not None and dt <= prev_dt:
            current_date = current_date + datetime.timedelta(days=1)
            dt = datetime.datetime(current_date.year, current_date.month, current_date.day, hh, mm, 0)
        parsed_times.append(dt)
        prev_dt = dt

    rows = []
    for i, (dt, (_time_text, program)) in enumerate(zip(parsed_times, schedule_pairs)):
        if i + 1 < len(parsed_times):
            duration = parsed_times[i + 1] - dt
        else:
            next_midnight = datetime.datetime(dt.year, dt.month, dt.day) + datetime.timedelta(days=1)
            duration = next_midnight - dt
        rows.append({
            "id": i + 1,
            "start_dt": dt,
            "duration": duration,
            "program": program,
        })
    return rows


def format_timedelta(td: datetime.timedelta) -> str:
    total_seconds = int(td.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def write_xls(path: Path, epg_rows):
    """Ghi file .xls chuan (Excel 97-2003) dung cau truc: 3 dong trong, 1 dong tieu de,
    cac cot ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.
    Font, do rong cot deu duoc dat khop voi file EPG mau (Arial 12, General format,
    khong bold, khong border)."""
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Sheet1")

    # Font/style giong file mau: Arial, cao 240 twips (=12pt), khong bold, dinh dang General
    plain_style = xlwt.easyxf("font: name Arial, height 240, bold off")

    # Do rong cot (don vi 1/256 ky tu) lay dung theo file mau
    col_widths = [2773, 5333, 5333, 5333, 38613]
    for c, w in enumerate(col_widths):
        ws.col(c).width = w

    header = ["ID", "Ngày", "Thời gian bắt đầu", "Thời lượng", "Tên chương trình"]
    header_row_idx = 3  # 3 dong dau (0,1,2) de trong giong file mau
    for c, h in enumerate(header):
        ws.write(header_row_idx, c, h, plain_style)

    for i, row in enumerate(epg_rows):
        r = header_row_idx + 1 + i
        ws.write(r, 0, row["id"], plain_style)
        ws.write(r, 1, row["start_dt"].strftime("%m/%d/%Y %H:%M:%S"), plain_style)
        ws.write(r, 2, row["start_dt"].strftime("%H:%M:%S"), plain_style)
        ws.write(r, 3, format_timedelta(row["duration"]), plain_style)
        ws.write(r, 4, row["program"], plain_style)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="./output", help="Thu muc de luu file .xls")
    parser.add_argument("--limit", type=int, default=None, help="Gioi han so kenh (de test nhanh)")
    parser.add_argument("--delay", type=float, default=0.7, help="Do tre giua cac request (giay)")
    args = parser.parse_args()

    today = datetime.date.today()
    out_dir = Path(args.output_dir) / today.isoformat()  # vi du: output/2026-08-20/
    date_stamp = today.strftime("%d%m%Y")

    session = requests.Session()

    print(f"Dang lay danh sach kenh tu {BASE_URL} ...")
    try:
        channels = discover_channels(session)
    except Exception as e:  # noqa: BLE001
        print(f"LOI: khong the tai danh sach kenh: {e}", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        channels = channels[: args.limit]

    print(f"Tim thay {len(channels)} kenh. Bat dau lay lich phat song...")

    success = []
    failures = []

    for idx, (url, name) in enumerate(channels, start=1):
        try:
            html = fetch(session, url)
            schedule = parse_schedule(html)
            if not schedule:
                raise ValueError("khong tach duoc bang gio/chuong trinh (co the trang doi cau truc)")

            epg_rows = build_epg_rows(schedule, today)
            filename = f"{safe_filename_part(name)}EPG{date_stamp}.xls"
            file_path = out_dir / filename
            write_xls(file_path, epg_rows)

            success.append((name, file_path, len(epg_rows)))
            print(f"[{idx}/{len(channels)}] OK  - {name}: {len(epg_rows)} muc lich -> {file_path}")
        except Exception as e:  # noqa: BLE001
            failures.append((name, url, str(e)))
            print(f"[{idx}/{len(channels)}] LOI - {name}: {e}", file=sys.stderr)

        time.sleep(args.delay)

    print("\n===== TONG KET =====")
    print(f"Thanh cong: {len(success)}/{len(channels)} kenh")
    print(f"Thu muc output: {out_dir.resolve()}")
    if failures:
        print(f"\nCac kenh loi ({len(failures)}):")
        for name, url, err in failures:
            print(f"  - {name} ({url}): {err}")


if __name__ == "__main__":
    main()
