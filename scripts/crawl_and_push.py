#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thợ nền: đọc lịch cào từ EPG, tự chạy đúng giờ, cào rồi đẩy về EPG.

Đây là "trái tim" độc lập của crawler. Nó có nhịp chạy riêng, không chờ
EPG bảo mới chạy — chỉ ĐỌC giờ mong muốn từ EPG rồi tự canh. EPG có sập
thì nó vẫn cào theo giờ đã nhớ, và khi EPG dậy lại thì đẩy tiếp.

Ba cách chạy:

    # chạy một lần ngay bây giờ (cào + đẩy), bất kể lịch — để thử hoặc cào tay
    python3 scripts/crawl_and_push.py --once

    # chỉ đẩy thư mục hôm nay đã cào sẵn, không cào lại
    python3 scripts/crawl_and_push.py --once --push-only

    # chạy nền: cứ vài phút thức dậy, tới giờ mong muốn thì tự cào + đẩy
    python3 scripts/crawl_and_push.py --daemon

Giờ mong muốn và bật/tắt lấy từ EPG (tab Quản lý dữ liệu). Đổi trên web
là lần chạy sau theo ngay, không phải sửa gì ở máy crawler.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epg_client import EpgClient, EpgError, load_config   # noqa: E402
from push_output import push_folder                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Nhớ mốc đã chạy giữa các lần khởi động. Trong container thì trỏ biến
# EPG_PUSH_STATE vào một volume (ví dụ /data/.epg_push_state.json) để
# khởi động lại không cào lại mốc đã cào.
STATE_FILE = os.environ.get("EPG_PUSH_STATE") or os.path.join(
    ROOT, ".epg_push_state.json")


def _log(msg):
    print("%s  %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg),
          flush=True)


# ------------------------------------------------------------- trạng thái

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ------------------------------------------------------------- cào + đẩy

def chay_cao(cfg, parent_dir):
    """Chạy các lệnh cào đã cấu hình. `parent_dir` là thư mục CHA (script
    cào tự tạo thư mục con theo ngày). Trả về (ok, lời than)."""
    lenh = cfg.get("crawl_commands") or []
    if not lenh:
        return True, "Không có lệnh cào nào được cấu hình — chỉ đẩy file sẵn có."
    than = []
    for raw in lenh:
        arg = [str(a).replace("{output}", parent_dir) for a in raw]
        _log("cào: " + " ".join(arg))
        try:
            r = subprocess.run(arg, cwd=ROOT, timeout=cfg.get("crawl_timeout", 900))
            if r.returncode != 0:
                than.append("lệnh %r trả mã %d" % (arg[0], r.returncode))
        except Exception as e:                  # noqa: BLE001
            than.append("lệnh %r hỏng: %s" % (arg[0], e))
    return (not than), "; ".join(than)


def cao_va_day(cfg, client, air_date=None, push_only=False):
    """Một lượt trọn: (cào) -> đẩy -> báo nhịp tim. Trả về dict tóm tắt."""
    air_date = air_date or datetime.date.today().strftime("%Y-%m-%d")
    parent = cfg.get("output_dir") or "./output"
    if not os.path.isabs(parent):
        parent = os.path.join(ROOT, parent)
    out_dir = os.path.join(parent, air_date)

    than_cao = ""
    if not push_only:
        _, than_cao = chay_cao(cfg, parent)

    if not os.path.isdir(out_dir):
        msg = "Không có thư mục %s để đẩy." % out_dir
        _log(msg)
        _hb(client, air_date, 0, 0, msg)
        return {"ok": 0, "failed": 0, "message": msg}

    ket_qua, ok, hong = push_folder(client, out_dir, air_date)
    for name, result, m in ket_qua:
        _log("  %-30s %-12s %s" % (name[:30], result or "", (m or "")[:50]))

    # Đếm cho nhịp tim: kênh gửi được nhưng EPG báo 'loi' vẫn là "hỏng" theo
    # nghĩa nội dung, đáng để người trực thấy con số.
    noi_dung_loi = sum(1 for _n, r, _m in ket_qua if r == "loi")
    tot = sum(1 for _n, r, _m in ket_qua if r in ("nap_duyet", "nap_nhap", "luu"))
    tong_hong = hong + noi_dung_loi
    msg = "Cào+đẩy %s: %d ok, %d lỗi." % (air_date, tot, tong_hong)
    if than_cao:
        msg += " Cào: " + than_cao
    _log(msg)
    _hb(client, air_date + " " + datetime.datetime.now().strftime("%H:%M:%S"),
        tot, tong_hong, msg)

    st = load_state()
    st["last_run"] = {"at": datetime.datetime.now().isoformat(timespec="seconds"),
                      "ok": tot, "failed": tong_hong, "message": msg}
    save_state(st)
    return {"ok": tot, "failed": tong_hong, "message": msg}


def _hb(client, run_at, ok, failed, message):
    try:
        client.heartbeat(run_at=run_at, ok=ok, failed=failed, message=message)
    except EpgError as e:
        _log("nhịp tim không gửi được (EPG có thể đang sập): %s" % e)


# ------------------------------------------------------------- thợ nền

def _slot_da_chay(st, ngay, gio):
    return gio in (st.get("ran", {}).get(ngay, []))


def _danh_dau_chay(ngay, gio):
    # Nạp lại trạng thái MỚI NHẤT rồi mới ghi, đừng đè lên bản cũ trong tay
    # — giữa lúc canh giờ và lúc đánh dấu, cao_va_day đã ghi last_run vào
    # file, đè bản cũ lên sẽ xoá mất.
    st = load_state()
    st.setdefault("ran", {}).setdefault(ngay, [])
    if gio not in st["ran"][ngay]:
        st["ran"][ngay].append(gio)
    for d in list(st["ran"]):        # dọn ngày cũ cho gọn
        if d < ngay:
            del st["ran"][d]
    save_state(st)


def daemon(cfg, client, poll=300):
    _log("Thợ nền khởi động. Hỏi lịch EPG mỗi %d giây." % poll)
    orders_cache = None
    while True:
        try:
            orders = client.orders()
            orders_cache = orders
            st = load_state()
            st["orders_cache"] = orders
            save_state(st)
        except EpgError as e:
            _log("không đọc được lịch từ EPG: %s" % e)
            orders = orders_cache or load_state().get("orders_cache")
            if orders is None:
                _log("chưa có lịch nào để theo, chờ vòng sau.")
                time.sleep(poll)
                continue
            _log("dùng lịch đã nhớ lần trước.")

        # Báo còn sống mỗi vòng, kèm số liệu lần cào gần nhất
        lr = load_state().get("last_run") or {}
        _hb(client, lr.get("at"), lr.get("ok", 0), lr.get("failed", 0),
            lr.get("message"))

        # "Đồng bộ ngay" từ web: mốc mới hơn lần đã xử lý -> cào full NGAY,
        # không đợi tới giờ. Dấu đã xử lý để không cào lại cùng một yêu cầu.
        rn = orders.get("run_now")
        if rn and rn != load_state().get("run_now_done"):
            _log("nhận yêu cầu Đồng bộ ngay (%s) — cào+đẩy toàn bộ." % rn)
            cao_va_day(cfg, client)
            st = load_state()            # nạp lại tươi, đừng đè last_run
            st["run_now_done"] = rn
            save_state(st)

        if orders.get("enabled") and orders.get("times"):
            now = datetime.datetime.now()
            ngay = now.strftime("%Y-%m-%d")
            hhmm = now.strftime("%H:%M")
            st = load_state()
            # Mốc nào tới hạn hôm nay mà chưa chạy thì chạy — lấy mốc muộn
            # nhất đã qua, để khởi động trễ vẫn không bỏ sót.
            den_han = sorted(t for t in orders["times"]
                             if t <= hhmm and not _slot_da_chay(st, ngay, t))
            if den_han:
                gio = den_han[-1]
                _log("tới giờ %s — bắt đầu cào+đẩy." % gio)
                cao_va_day(cfg, client)
                for t in den_han:
                    _danh_dau_chay(ngay, t)

        time.sleep(poll)


# ------------------------------------------------------------- vào lệnh

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="chạy một lần ngay")
    ap.add_argument("--daemon", action="store_true", help="chạy nền theo lịch EPG")
    ap.add_argument("--push-only", action="store_true",
                    help="không cào lại, chỉ đẩy file đã có")
    ap.add_argument("--date", help="ngày phát YYYY-MM-DD (mặc định hôm nay)")
    ap.add_argument("--poll", type=int, default=300,
                    help="thợ nền hỏi lịch EPG mỗi bao nhiêu giây (mặc định 300)")
    ap.add_argument("--config", help="đường dẫn file cấu hình")
    args = ap.parse_args(argv)

    if not (args.once or args.daemon):
        ap.error("chọn --once hoặc --daemon")

    try:
        cfg = load_config(args.config)
        client = EpgClient.from_config(cfg)
    except EpgError as e:
        print("Cấu hình: %s" % e, file=sys.stderr)
        return 2

    if args.once:
        out = cao_va_day(cfg, client, air_date=args.date,
                         push_only=args.push_only)
        return 1 if out["failed"] else 0

    try:
        daemon(cfg, client, poll=args.poll)
    except KeyboardInterrupt:
        _log("Dừng thợ nền.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
