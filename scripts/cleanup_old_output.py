#!/usr/bin/env python3
"""
cleanup_old_output.py

Xoa cac thu muc con dang YYYY-MM-DD trong thu muc output da qua so ngay quy dinh
(mac dinh 7 ngay). Dung de don dep tu dong sau khi chay fetch_tv_schedule.py hang ngay.

Usage:
    python3 cleanup_old_output.py --output-dir ./output --days 7
"""

import argparse
import datetime
import re
import shutil
from pathlib import Path

DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="./output", help="Thu muc goc chua cac thu muc ngay")
    parser.add_argument("--days", type=int, default=7, help="Giu lai bao nhieu ngay gan nhat")
    args = parser.parse_args()

    root = Path(args.output_dir)
    if not root.exists():
        print(f"Thu muc {root} khong ton tai, bo qua.")
        return

    today = datetime.date.today()
    removed = []
    kept = []

    for d in sorted(root.iterdir()):
        if not d.is_dir() or not DATE_DIR_RE.match(d.name):
            continue
        try:
            folder_date = datetime.date.fromisoformat(d.name)
        except ValueError:
            continue

        age_days = (today - folder_date).days
        if age_days > args.days:
            shutil.rmtree(d)
            removed.append(d.name)
        else:
            kept.append(d.name)

    if removed:
        print(f"Da xoa {len(removed)} thu muc cu hon {args.days} ngay: {', '.join(removed)}")
    else:
        print("Khong co thu muc nao can xoa.")
    if kept:
        print(f"Giu lai {len(kept)} thu muc: {', '.join(kept)}")


if __name__ == "__main__":
    main()
