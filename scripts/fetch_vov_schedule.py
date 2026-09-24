#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lay lich hien tai cua VOV1 va VOV3, xuat moi kenh mot file EPG .xls.

    pip install xlwt
    python fetch_vov_schedule.py --output-dir ./output
    python fetch_vov_schedule.py --channels VOV3 --output-dir ./output

Chi lay lich hien tai: website khong cung cap ngay lich trong khoi HTML.
--date la ngay gan cho lich hien tai, KHONG truy van lich luu tru.
Ngay khac hom nay can --use-current-schedule de tranh gan nham lich.
File: output/YYYY-MM-DD/VOV1EPGDDMMYYYY.xls va VOV3EPGDDMMYYYY.xls.
"""
import argparse
import datetime as dt
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

CHANNELS = {"VOV1": "https://vov1.vov.vn/", "VOV3": "https://vov3.vov.vn/"}
VN_TZ = dt.timezone(dt.timedelta(hours=7))


class ScheduleParser(HTMLParser):
    """Doc cac class lich phat song; bo qua ban sao desktop/mobile."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.capture = None
        self.tag = None
        self.parts = []
        self.pending = None
        self.items = []

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        kind = next((x for x in ("time-play-schedule", "title-play-schedule")
                     if x in classes), None)
        if kind:
            if self.capture:
                raise ValueError("Cau truc lich HTML thay doi")
            self.capture, self.tag, self.parts = kind, tag, []

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if not self.capture or tag != self.tag:
            return
        text = " ".join("".join(self.parts).split())
        if self.capture == "time-play-schedule":
            if self.pending is not None:
                raise ValueError("Thieu ten chuong trinh")
            self.pending = text
        else:
            if self.pending is None or not text:
                raise ValueError("Thieu gio hoac ten chuong trinh")
            self.items.append((self.pending, text))
            self.pending = None
        self.capture = self.tag = None


class VOV3Parser(HTMLParser):
    """Chi doc cac khoi lich, tranh nham tieu de bai viet ben ngoai."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scope = 0
        self.capture = None
        self.depth = 0
        self.parts = []
        self.pending = None
        self.items = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "ul":
            if self.scope:
                self.scope += 1
            elif attrs.get("id") in ("lich-phat-song", "lich-phat-song-side"):
                self.scope = 1
        if not self.scope or tag != "span":
            return
        if self.capture:
            self.depth += 1
            return
        classes = attrs.get("class", "").split()
        kind = next((c for c in ("views-field-title", "view-field-airtime") if c in classes), None)
        if kind:
            self.capture, self.depth, self.parts = kind, 1, []

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "span" and self.capture:
            self.depth -= 1
            if not self.depth:
                text = " ".join("".join(self.parts).split())
                if self.capture == "views-field-title":
                    if self.pending is not None or not text:
                        raise ValueError("Lich VOV3 thieu gio hoac ten")
                    self.pending = text
                else:
                    if self.pending is None:
                        raise ValueError("Lich VOV3 thieu ten chuong trinh")
                    self.items.append((text, self.pending))
                    self.pending = None
                self.capture = None
        if tag == "ul" and self.scope:
            self.scope -= 1
            if not self.scope and self.pending is not None:
                raise ValueError("Lich VOV3 chua day du")


def parse_schedule(html, channel="VOV1"):
    parser = ScheduleParser() if channel == "VOV1" else VOV3Parser()
    parser.feed(html)
    parser.close()
    if parser.pending is not None or parser.capture:
        raise ValueError("Lich HTML chua day du")
    by_start = {}
    for interval, title in parser.items:
        match = re.fullmatch(r"(\d{1,2})[hH:](\d{2})\s*[-–—]\s*(\d{1,2})[hH:](\d{2})", interval)
        if not match:
            raise ValueError("Gio khong hop le: " + interval)
        h, m, eh, em = map(int, match.groups())
        if not (0 <= h < 24 and 0 <= m < 60 and 0 <= eh <= 24
                and 0 <= em < 60 and (eh != 24 or em == 0)):
            raise ValueError("Gio ngoai pham vi: " + interval)
        start = h * 60 + m
        if start in by_start and by_start[start] != title:
            raise ValueError("Nhieu chuong trinh khac nhau cung gio: " + interval)
        by_start[start] = title
    if not by_start:
        raise ValueError("Khong tim thay lich; website co the da doi cau truc")
    return sorted(by_start.items())


def fetch_schedule(channel, timeout=30, retries=2):
    for attempt in range(retries + 1):
        try:
            request = Request(CHANNELS[channel], headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
            with urlopen(request, timeout=timeout) as response:
                html = response.read().decode("utf-8-sig")
            return parse_schedule(html, channel)
        except (OSError, ValueError) as exc:
            if attempt == retries:
                raise RuntimeError("Khong lay duoc lich %s: %s" % (channel, exc)) from exc
            time.sleep(1.5 * (attempt + 1))


def build_epg_rows(schedule, date):
    midnight = dt.datetime.combine(date, dt.time())
    rows = []
    for i, (minute, title) in enumerate(schedule):
        start = midnight + dt.timedelta(minutes=minute)
        end = (midnight + dt.timedelta(minutes=schedule[i + 1][0])
               if i + 1 < len(schedule) else midnight + dt.timedelta(hours=24, seconds=-1))
        if end <= start:
            raise ValueError("Lich khong tang dan")
        rows.append((i + 1, start, end - start, title))
    return rows


def write_xls(path, rows):
    # BIFF8 / Excel 97-2003, cung cau truc voi fetch_hanoi_schedule.py.
    import xlwt
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("Sheet1")
    font = "font: name Arial, height 240, bold off"
    plain = xlwt.easyxf(font)
    date_style = xlwt.easyxf(font, num_format_str="M/D/YYYY hh:mm:ss")
    time_style = xlwt.easyxf(font, num_format_str="hh:mm:ss")
    duration_style = xlwt.easyxf(font, num_format_str="[h]:mm:ss")
    for col, width in enumerate([2773, 5333, 5333, 5333, 38613]):
        sheet.col(col).width = width
    for col, value in enumerate(["ID", "Ngày", "Thời gian bắt đầu", "Thời lượng", "Tên chương trình"]):
        sheet.write(3, col, value, plain)
    for row, (number, start, duration, title) in enumerate(rows, 4):
        for col, (value, style) in enumerate([(number, plain), (start, date_style),
                (start.time(), time_style), (duration.total_seconds() / 86400, duration_style),
                (title, plain)]):
            sheet.write(row, col, value, style)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.xls")
    try:
        book.save(str(temporary))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="./output")
    parser.add_argument("--channels", nargs="+", choices=list(CHANNELS),
                        default=list(CHANNELS), help="Mac dinh: VOV1 VOV3")
    parser.add_argument("--date", type=dt.date.fromisoformat, help="Ngay gan cho lich, YYYY-MM-DD")
    parser.add_argument("--use-current-schedule", action="store_true",
                        help="Cho phep gan lich hien tai cho ngay khac; khong phai lich luu tru")
    args = parser.parse_args()
    today = dt.datetime.now(VN_TZ).date()
    date = args.date or today
    if date != today and not args.use_current_schedule:
        parser.error("Chi lay duoc lich hien tai. Neu muon gan ngay khac, them --use-current-schedule.")
    failures = 0
    channels = list(dict.fromkeys(args.channels))
    print("Lay lich dang hien thi; ngay lich khong duoc nguon xac nhan.")
    for channel in channels:
        try:
            rows = build_epg_rows(fetch_schedule(channel), date)
            path = Path(args.output_dir) / date.isoformat() / ("%sEPG%s.xls" % (channel, date.strftime("%d%m%Y")))
            write_xls(path, rows)
            print("OK - %s: %d chuong trinh -> %s" % (channel, len(rows), path.resolve()))
        except ImportError:
            failures += 1
            print("Thieu thu vien: chay python -m pip install xlwt", file=sys.stderr)
        except (OSError, ValueError, RuntimeError) as exc:
            failures += 1
            print("LOI - %s: %s" % (channel, exc), file=sys.stderr)
    print("Thanh cong: %d/%d kenh" % (len(channels) - failures, len(channels)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
