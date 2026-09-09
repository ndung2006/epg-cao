#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đẩy mọi file .xls trong một thư mục output/<ngày> lên EPG.

Dùng riêng được (đẩy lại một thư mục đã cào), hoặc do crawl_and_push gọi
sau khi cào xong.

    python3 scripts/push_output.py output/2026-09-09
    python3 scripts/push_output.py output/2026-09-09 --date 2026-09-09

Ngày phát: nếu không truyền --date thì lấy từ tên thư mục (phải là
YYYY-MM-DD). EPG tự khớp kênh theo tên file, nên ở đây không cần biết
file nào là kênh nào.
"""

import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epg_client import EpgClient, EpgError, load_config   # noqa: E402

_NGAY = re.compile(r"(\d{4}-\d{2}-\d{2})")


def ngay_tu_thu_muc(folder):
    """Đoán ngày phát từ tên thư mục output/<YYYY-MM-DD>."""
    m = _NGAY.search(os.path.basename(os.path.normpath(folder)))
    if not m:
        return None
    try:
        datetime.datetime.strptime(m.group(1), "%Y-%m-%d")
        return m.group(1)
    except ValueError:
        return None


def push_folder(client, folder, air_date):
    """Đẩy mọi .xls trong thư mục. Trả về (danh sách kết quả, ok, hỏng).

    Một file EPG từ chối nội dung (result 'loi') vẫn tính là đã gửi được —
    'hỏng' ở đây chỉ đếm những file KHÔNG gửi được (mất mạng, EPG sập).
    """
    # Đẩy theo thứ tự file CŨ -> MỚI (thời gian sửa). Nếu hai nguồn cùng
    # cào một kênh (baomoi + nguồn riêng), nguồn nào cào SAU thì file mới
    # hơn, được đẩy sau, và EPG lấy bản đẩy sau. Nhờ vậy chỉ cần xếp lệnh
    # cào: baomoi trước, nguồn riêng sau, là nguồn riêng luôn thắng — không
    # phải maintain danh sách tên kênh nào đè kênh nào.
    names = [f for f in os.listdir(folder)
             if f.lower().endswith((".xls", ".xlsx", ".xlsm"))
             and not f.startswith("~$")]
    files = sorted(names, key=lambda f: os.path.getmtime(os.path.join(folder, f)))
    ket_qua, ok, hong = [], 0, 0
    for name in files:
        path = os.path.join(folder, name)
        try:
            d = client.push_file(path, air_date)
            ket_qua.append((name, d.get("result"), d.get("message")))
            ok += 1
        except EpgError as e:
            ket_qua.append((name, "KHÔNG GỬI ĐƯỢC", str(e)))
            hong += 1
    return ket_qua, ok, hong


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="thư mục chứa file .xls, ví dụ output/2026-09-09")
    ap.add_argument("--date", help="ngày phát YYYY-MM-DD (mặc định lấy từ tên thư mục)")
    ap.add_argument("--config", help="đường dẫn file cấu hình")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.folder):
        print("Không có thư mục %r." % args.folder, file=sys.stderr)
        return 2
    air_date = args.date or ngay_tu_thu_muc(args.folder)
    if not air_date:
        print("Không đoán được ngày phát từ tên thư mục — truyền --date "
              "YYYY-MM-DD.", file=sys.stderr)
        return 2

    try:
        client = EpgClient.from_config(load_config(args.config))
    except EpgError as e:
        print("Cấu hình: %s" % e, file=sys.stderr)
        return 2

    ket_qua, ok, hong = push_folder(client, args.folder, air_date)
    print("Đẩy %d file cho ngày %s -> %s" % (len(ket_qua), air_date, client.url))
    for name, result, msg in ket_qua:
        print("  %-30s %-12s %s" % (name[:30], result or "", (msg or "")[:60]))
    print("Gửi được %d, không gửi được %d." % (ok, hong))
    return 1 if hong else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
