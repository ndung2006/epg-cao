#!/usr/bin/env python3
"""
fetch_vtv10_schedule.py

Lay lich phat song kenh VTV10 (chinh la VTV Can Tho, kenh thu 12 tren trang
lich phat song cua vtv.vn) va xuat ra file .xls (dinh dang Excel 97-2003
chuan), dung cau truc file EPG mau: 3 dong trong, 1 dong tieu de, cac cot
ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.

Trang https://vtv.vn/lich-phat-song-ngay-<D>-thang-<M>-nam-<Y>.htm liet ke
lien tiep 12 danh sach <ul class="programs"> theo dung thu tu kenh trong bo
chon kenh: VTV1, VTV2, VTV3, VTV4, VTV5, VTV5 Tay Nam Bo, VTV5 Tay Nguyen,
VTV6, VTV7, VTV8, VTV9, VTV Can Tho (= VTV10). Danh sach thu 12 (index 11)
la kenh can lay. Moi <li class="program"> da co san thuoc tinh duration
(so phut), khong can tu tinh khoang cach nhu voi baomoi.com.

Ten file: "VTV10EPG<ddMMyyyy>.xls"

Usage:
    python3 fetch_vtv10_schedule.py --output-dir ./output
    python3 fetch_vtv10_schedule.py --output-dir ./output --date 2026-08-28

Requires: requests, beautifulsoup4, xlwt (va fetch_tv_schedule.py trong cung
thu muc scripts/)
    pip install --break-system-packages requests beautifulsoup4 xlwt
"""

import argparse
import datetime
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from fetch_tv_schedule import write_xls, safe_filename_part

CHANNEL_NAME = "VTV10"
CHANNEL_INDEX = 11  # kenh thu 12 (0-based) trong danh sach 12 ul.programs

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def build_url(date: datetime.date) -> str:
    return (
        f"https://vtv.vn/lich-phat-song-ngay-{date.day}-thang-{date.month}"
        f"-nam-{date.year}.htm"
    )


def fetch_schedule(session: requests.Session, date: datetime.date, timeout: int = 15, retries: int = 2):
    """Tra ve list of (start_time 'HH:MM', duration_minutes, program)."""
    url = build_url(date)
    last_err = None
    html = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            html = resp.text
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                continue
            raise last_err

    soup = BeautifulSoup(html, "html.parser")
    program_lists = soup.find_all("ul", class_="programs")
    if len(program_lists) <= CHANNEL_INDEX:
        raise ValueError(
            f"Trang chi co {len(program_lists)} danh sach kenh, "
            f"khong du toi vi tri {CHANNEL_INDEX + 1} (VTV10)"
        )

    items = program_lists[CHANNEL_INDEX].find_all("li", class_="program")
    pairs = []
    for li in items:
        time_span = li.find("span", class_="time")
        title_span = li.find("span", class_="title")
        if not time_span or not title_span:
            continue
        time_text = time_span.get_text(strip=True)
        title = title_span.get_text(strip=True)
        genre_a = li.find("a", class_="genre")
        if genre_a and genre_a.get_text(strip=True):
            title = f"{title}: {genre_a.get_text(strip=True)}"
        duration_min = int(li.get("duration", 0))
        pairs.append((time_text, duration_min, title))

    pairs.sort(key=lambda p: p[0])
    return pairs


def build_epg_rows(schedule_triples, base_date: datetime.date):
    """Dung duration co san tu nguon (phut); dong cuoi cung cat tai 23:59:59
    cua cung ngay thay vi tran sang 00:00:00 hom sau."""
    rows = []
    for i, (time_text, duration_min, program) in enumerate(schedule_triples):
        hh, mm = map(int, time_text.split(":"))
        dt = datetime.datetime(base_date.year, base_date.month, base_date.day, hh, mm, 0)
        if i + 1 < len(schedule_triples):
            duration = datetime.timedelta(minutes=duration_min)
        else:
            end_of_day = datetime.datetime(dt.year, dt.month, dt.day, 23, 59, 59)
            duration = end_of_day - dt
        rows.append({
            "id": i + 1,
            "start_dt": dt,
            "duration": duration,
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
