#!/usr/bin/env python3
"""
fetch_vtv_schedule.py

Lay lich phat song cac kenh VTV1, VTV2, VTV3, VTV5, VTV6, VTV9, VTV10 tu
https://vtv.vn/lich-phat-song.htm (khong dung baomoi.com cho cac kenh nay
nua) va xuat moi kenh thanh 1 file .xls (dinh dang Excel 97-2003 chuan)
rieng biet, dung cau truc file EPG mau: 3 dong trong, 1 dong tieu de, cac
cot ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.

Trang https://vtv.vn/lich-phat-song-ngay-<D>-thang-<M>-nam-<Y>.htm liet ke
lien tiep 12 danh sach <ul class="programs"> theo dung thu tu kenh trong bo
chon kenh: VTV1, VTV2, VTV3, VTV4, VTV5, VTV5 Tay Nam Bo, VTV5 Tay Nguyen,
VTV6, VTV7, VTV8, VTV9, VTV Can Tho (= VTV10). Chi tai trang 1 lan roi tach
ra 7 kenh can lay theo dung vi tri trong danh sach do. Moi <li class="program">
da co san thuoc tinh duration (so phut), khong can tu tinh khoang cach nhu
voi baomoi.com.

Ten file: "<Ten kenh>EPG<ddMMyyyy>.xls" (vi du: "VTV1EPG28082026.xls")

Usage:
    python3 fetch_vtv_schedule.py --output-dir ./output
    python3 fetch_vtv_schedule.py --output-dir ./output --date 2026-08-28

Requires: requests, beautifulsoup4, xlwt (va fetch_tv_schedule.py trong cung
thu muc scripts/)
    pip install --break-system-packages requests beautifulsoup4 xlwt
"""

import argparse
import datetime
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from fetch_tv_schedule import (
    write_xls,
    safe_filename_part,
    discover_channels,
    fetch as baomoi_fetch,
    parse_schedule as baomoi_parse_schedule,
    build_epg_rows as baomoi_build_epg_rows,
)

# (ten kenh xuat ra file, vi tri (0-based) trong 12 danh sach <ul class="programs">
# tren trang, dung theo thu tu bo chon kenh: VTV1,2,3,4,5,5TNB,5TN,6,7,8,9,CanTho)
CHANNELS = [
    ("VTV1", 0),
    ("VTV2", 1),
    ("VTV3", 2),
    ("VTV5", 4),
    ("VTV6", 7),
    ("VTV9", 10),
    ("VTV10", 11),  # VTV10 chinh la VTV Can Tho
]

# Kenh nao vtv.vn khong co du lieu thi tam thoi lay lai tu baomoi.com
# (ten kenh xuat file -> ten kenh tren baomoi.com)
FALLBACK_BAOMOI = {
    "VTV9": "VTV9",
}

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


def fetch_page(session: requests.Session, date: datetime.date, timeout: int = 15, retries: int = 2) -> str:
    url = build_url(date)
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            return resp.text
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                continue
            raise last_err


def fetch_all_channel_lists(session: requests.Session, date: datetime.date, needed_indices, max_attempts: int = 15, delay: float = 1.0):
    """vtv.vn phuc vu cache khong dong nhat: co lan tra ve trang day du 12
    kenh, co lan thieu du lieu vai kenh (ul.programs rong). Tai lai nhieu
    lan, moi lan giu lai danh sach <li class="program"> cho kenh nao dang
    con thieu, den khi du het cac kenh can hoac het luot thu."""
    best_lists = {}
    for attempt in range(max_attempts):
        html = fetch_page(session, date)
        soup = BeautifulSoup(html, "html.parser")
        program_lists = soup.find_all("ul", class_="programs")
        for idx in needed_indices:
            if idx in best_lists:
                continue
            if idx < len(program_lists):
                items = program_lists[idx].find_all("li", class_="program")
                if items:
                    best_lists[idx] = program_lists[idx]
        if all(idx in best_lists for idx in needed_indices):
            break
        if attempt < max_attempts - 1:
            time.sleep(delay)
    return best_lists


def parse_channel_schedule(program_list) -> list:
    """Tra ve list of (start_time 'HH:MM', duration_minutes, program), da sap
    xep tang dan, tu 1 the <ul class="programs"> cua 1 kenh."""
    items = program_list.find_all("li", class_="program")
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
    print(f"Dang tai trang lich phat song vtv.vn cho ngay {target_date.isoformat()} ...")
    print("(vtv.vn phuc vu cache khong dong nhat, se tu dong thu lai toi da 15 lan neu con kenh thieu du lieu)")
    needed_indices = [idx for _, idx in CHANNELS]
    try:
        channel_lists = fetch_all_channel_lists(session, target_date, needed_indices)
    except Exception as e:  # noqa: BLE001
        print(f"LOI: khong the tai trang vtv.vn: {e}", file=sys.stderr)
        sys.exit(1)

    baomoi_channels_by_name = None  # tai luoi, chi khi can fallback

    success = []
    failures = []
    for idx, (channel_name, list_index) in enumerate(CHANNELS, start=1):
        try:
            if list_index not in channel_lists:
                raise ValueError(
                    "khong co du lieu lich cho ngay nay sau nhieu lan thu lai "
                    "(co the vtv.vn chua cong bo lich kenh nay)"
                )
            schedule = parse_channel_schedule(channel_lists[list_index])
            if not schedule:
                raise ValueError("khong co du lieu lich cho ngay nay")
            epg_rows = build_epg_rows(schedule, target_date)
            filename = f"{safe_filename_part(channel_name)}EPG{date_stamp}.xls"
            file_path = out_dir / filename
            write_xls(file_path, epg_rows)
            success.append((channel_name, file_path, len(epg_rows)))
            print(f"[{idx}/{len(CHANNELS)}] OK  - {channel_name}: {len(epg_rows)} muc lich -> {file_path}")
        except Exception as e:  # noqa: BLE001
            baomoi_name = FALLBACK_BAOMOI.get(channel_name)
            if not baomoi_name:
                failures.append((channel_name, str(e)))
                print(f"[{idx}/{len(CHANNELS)}] LOI - {channel_name}: {e}", file=sys.stderr)
                continue
            try:
                if baomoi_channels_by_name is None:
                    baomoi_channels_by_name = {
                        name: url for url, name in discover_channels(session)
                    }
                url = baomoi_channels_by_name.get(baomoi_name)
                if not url:
                    raise ValueError(f"khong tim thay '{baomoi_name}' tren baomoi.com")
                html = baomoi_fetch(session, url)
                baomoi_schedule = baomoi_parse_schedule(html)
                if not baomoi_schedule:
                    raise ValueError("baomoi.com cung khong co du lieu")
                epg_rows = baomoi_build_epg_rows(baomoi_schedule, target_date)
                filename = f"{safe_filename_part(channel_name)}EPG{date_stamp}.xls"
                file_path = out_dir / filename
                write_xls(file_path, epg_rows)
                success.append((channel_name, file_path, len(epg_rows)))
                print(
                    f"[{idx}/{len(CHANNELS)}] OK  - {channel_name}: {len(epg_rows)} muc lich "
                    f"-> {file_path} (nguon du phong: baomoi.com, vtv.vn khong co du lieu)"
                )
            except Exception as e2:  # noqa: BLE001
                failures.append((channel_name, f"vtv.vn: {e} | baomoi.com: {e2}"))
                print(f"[{idx}/{len(CHANNELS)}] LOI - {channel_name}: {e2}", file=sys.stderr)

    print("\n===== TONG KET =====")
    print(f"Thanh cong: {len(success)}/{len(CHANNELS)} kenh")
    print(f"Thu muc output: {out_dir.resolve()}")
    if failures:
        print(f"\nCac kenh loi ({len(failures)}):")
        for name, err in failures:
            print(f"  - {name}: {err}")


if __name__ == "__main__":
    main()
