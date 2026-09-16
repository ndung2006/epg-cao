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

# Vai kenh baomoi phai doi TEN FILE khi xuat, vi dai da sap nhap / doi ten.
# Key = slug trong link baomoi (.../tien-ich-lich-truyen-hinh-<slug>.epi),
# value = ten kenh dung DUNG nhu ben EPG (EPG khop file theo file_prefix).
#   bacgiangtv-bgtv:  dai Bac Giang da sap nhap vao Bac Ninh  -> "BAC NINH".
#   binhthuantv-btv:  dai Binh Thuan da sap nhap vao Lam Dong -> "LAM DONG 2".
TEN_KENH_THAY = {
    "bacgiangtv-bgtv": "BAC NINH",
    "binhthuantv-btv": "LAM DONG 2",
}

# Kenh KHONG lay tu baomoi nua vi da co nguon rieng chinh xac hon (script
# fetch_<dai>_schedule.py). Bo qua ngay khi discover de khong sinh file trung
# roi tranh nhau voi nguon rieng.
#   angiangtv-atv: lay tu angiangtv.vn (AN GIANG 1 & 3) qua fetch_angiang.
#   hanoitv1-hd / hanoitv2-hd: lay tu hanoionline.vn qua fetch_hanoi.
#   dongnaitv1-dn1-hd / dongnaitv2-dn2 va 3 kenh VTVcab the thao (ON SPORTS,
#   ON SPORT NEWS, ON FOOTBALL): lay tu tv360.vn qua fetch_tv360.
BO_QUA_SLUG = {
    "angiangtv-atv",
    "hanoitv1-hd",
    "hanoitv2-hd",
    "dongnaitv1-dn1-hd",
    "dongnaitv2-dn2",
    "vtvcab3-the-thao-tv-hd",
    "vtvcab18-the-thao-tin-tuc-hd",
    "vtvcab16-bong-da-tv",
}


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
        m = CHANNEL_LINK_RE.search(href)
        if not m:
            continue
        if href.startswith("http"):
            full_url = href
        else:
            full_url = "https://baomoi.com" + (href if href.startswith("/") else "/" + href)
        slug = m.group(1).lower()
        if slug in BO_QUA_SLUG:
            continue                       # da co nguon rieng, khong lay baomoi
        # Doi ten kenh sang ten dung ben EPG (neu co trong bang), roi moi
        # dung lam ten file — dai sap nhap: BacGiangTV -> BAC NINH, v.v.
        name = TEN_KENH_THAY.get(slug) or a.get_text(strip=True) or slug

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
    Trang baomoi hien thi lich cua DUY NHAT 1 ngay (hom nay), nhung theo thu tu
    "sap phat truoc, da phat sau" (vd 14:00 -> 23:30 roi 00:00 -> 13:30), khong
    phai theo gio tang dan, va khong he lien quan toi ngay hom sau. Vi vay gan
    CUNG 1 ngay (base_date) cho moi dong, roi sap xep lai theo gio tang dan de
    co danh sach 00:00:00 -> 23:59:59 lien tuc dung 1 ngay.

    Tinh 'Thoi luong' = khoang cach den chuong trinh ke tiep (dong cuoi cat tai
    23:59:59 cua CUNG ngay do - moi ngay la 1 khoi rieng biet, khong de thoi
    luong cham sang 00:00:00 ngay hom sau). Tra ve list dict: id,
    start_dt (datetime), duration (timedelta), program (str).
    """
    entries = []
    for time_text, program in schedule_pairs:
        hh, mm = map(int, time_text.split(":"))
        dt = datetime.datetime(base_date.year, base_date.month, base_date.day, hh, mm, 0)
        entries.append((dt, program))

    entries.sort(key=lambda entry: entry[0])

    rows = []
    for i, (dt, program) in enumerate(entries):
        if i + 1 < len(entries):
            duration = entries[i + 1][0] - dt
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


def normalize_epg_rows(epg_rows):
    """Don danh sach dong truoc khi ghi, de EPG khong tu choi ca file.

    Ba loi hay gap trong du lieu cao, xu ly o DUNG MOT CHO nay vi moi script
    (baomoi, quangninh, nghean, thanhhoa, sctv, thvl, vietnamtoday) deu ghi
    file qua write_xls:

      * Muc lech ngay: nguon doi khi tra mot muc "phat lai" voi gio rac (vd
        nam 0001), ra thoi luong khong lo. -> bo dong khong thuoc ngay chiem
        da so.
      * Trung gio bat dau: hai muc cung phut -> mot muc thoi luong 0 (EPG
        chan E02) va trung gio (E03). -> giu muc sau cung o moi moc gio.
      * Sau khi don thi TINH LAI thoi luong = moc ke tiep tru moc nay; dong
        cuoi cat tai 23:59:59 cung ngay.
    """
    from collections import Counter

    rows = [r for r in epg_rows if r.get("start_dt") is not None]
    if not rows:
        return epg_rows

    ngay = Counter(r["start_dt"].date() for r in rows).most_common(1)[0][0]
    rows = [r for r in rows if r["start_dt"].date() == ngay]

    theo_gio = {}
    for r in sorted(rows, key=lambda x: x["start_dt"]):
        theo_gio[r["start_dt"]] = r        # trung gio -> muc sau cung thang
    uniq = [theo_gio[k] for k in sorted(theo_gio)]

    out = []
    for i, r in enumerate(uniq):
        d = r["start_dt"]
        if i + 1 < len(uniq):
            dur = uniq[i + 1]["start_dt"] - d
        else:
            eod = datetime.datetime(d.year, d.month, d.day, 23, 59, 59)
            dur = eod - d
            if dur.total_seconds() < 0:
                dur = datetime.timedelta(0)
        out.append({"id": i + 1, "start_dt": d, "duration": dur,
                    "program": r.get("program", "")})
    return out


def write_xls(path: Path, epg_rows):
    """Ghi file .xls chuan (Excel 97-2003) dung cau truc: 3 dong trong, 1 dong tieu de,
    cac cot ID / Ngay / Thoi gian bat dau / Thoi luong / Ten chuong trinh.
    Font, do rong cot deu duoc dat khop voi file EPG mau (Arial 12, General format,
    khong bold, khong border).

    Cot Ngay / Thoi gian bat dau / Thoi luong duoc ghi la gia tri ngay-gio thuc su
    cua Excel (khong phai chuoi text) de sap xep tang dan dung thu tu thoi gian
    (00:00:00 -> 23:59:59), thay vi bi sap xep sai theo kieu so sanh chuoi ky tu."""
    epg_rows = normalize_epg_rows(epg_rows)

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Sheet1")

    # Font/style giong file mau: Arial, cao 240 twips (=12pt), khong bold
    plain_style = xlwt.easyxf("font: name Arial, height 240, bold off")
    datetime_style = xlwt.easyxf(
        "font: name Arial, height 240, bold off", num_format_str="M/D/YYYY hh:mm:ss"
    )
    time_style = xlwt.easyxf(
        "font: name Arial, height 240, bold off", num_format_str="hh:mm:ss"
    )
    # [h] cho phep hien thi qua 24 gio (vd chuong trinh cuoi ngay keo dai nhieu gio)
    duration_style = xlwt.easyxf(
        "font: name Arial, height 240, bold off", num_format_str="[h]:mm:ss"
    )

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
        ws.write(r, 1, row["start_dt"], datetime_style)
        ws.write(r, 2, row["start_dt"].time(), time_style)
        ws.write(r, 3, row["duration"].total_seconds() / 86400, duration_style)
        ws.write(r, 4, row["program"], plain_style)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))


def main():
    # Console Windows mac dinh dung bang ma cp1252, khong ma hoa duoc nhieu ky tu
    # tieng Viet -> ep stdout/stderr sang UTF-8 de tranh crash UnicodeEncodeError
    # khi in ten kenh/thong bao loi co dau.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

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
