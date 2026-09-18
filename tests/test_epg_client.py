#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm thử lớp đẩy file lên EPG, dùng một EPG giả — không cần EPG thật.

Soi những chỗ dễ sai:
  * token đi kèm mọi lời gọi; sai/thiếu token thì EPG giả trả 403/503
  * file .xls đẩy đúng, đọc lại kết quả result/message
  * EPG sập (không nối được) thì báo lỗi rõ, KHÔNG làm treo
  * cấu hình đọc từ file lẫn biến môi trường
  * logic canh giờ của thợ nền: mốc tới hạn thì chạy, chạy rồi thì thôi

Chạy:  python tests/test_epg_client.py
"""

import io
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

import epg_client                                    # noqa: E402
from epg_client import EpgClient, EpgError, load_config   # noqa: E402
import push_output                                   # noqa: E402
import crawl_and_push                                # noqa: E402
import fetch_tv_schedule                             # noqa: E402

PASS, FAIL = [], []
TOKEN = "khoa thu nghiem"


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("%s %s%s" % ("  ok  " if cond else " HONG ", name,
                       ("   " + detail) if detail and not cond else ""))


# ------------------------------------------------------------ EPG giả

class EpgGia(BaseHTTPRequestHandler):
    """Máy chủ EPG giả: đủ ba cửa để kiểm client, không phải EPG thật."""
    token_dung = TOKEN
    da_bat = True          # False = chưa đặt token -> 503
    nhan = []              # ghi lại các lần push

    def log_message(self, *a):
        pass

    def _tok_ok(self):
        if not EpgGia.da_bat:
            self._json(503, {"error": "chưa bật"})
            return False
        if self.headers.get("X-Crawl-Token") != EpgGia.token_dung:
            self._json(403, {"error": "khoá sai"})
            return False
        return True

    def _json(self, code, obj):
        b = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/crawl/orders":
            if not self._tok_ok():
                return
            self._json(200, {"enabled": True, "times": ["05:00", "17:00"],
                             "channels": [{"service_id": 809, "name": "VTV1",
                                           "mode": "tu_dong"}]})
        else:
            self._json(404, {"error": "?"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        if self.path == "/api/crawl/push":
            if not self._tok_ok():
                return
            # không phân tích multipart cho đủ, chỉ ghi nhận đã nhận
            EpgGia.nhan.append(len(body))
            ten = b'filename="' in body
            self._json(200, {"ok": True, "result": "nap_duyet",
                             "message": "Đã nạp", "co_ten": ten})
        elif self.path == "/api/crawl/heartbeat":
            if not self._tok_ok():
                return
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "?"})


def start_gia():
    srv = HTTPServer(("127.0.0.1", 0), EpgGia)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


# --------------------------------------------------------------- bài kiểm

def test_config():
    print("\n--- Đọc cấu hình ---")
    tmp = tempfile.mkdtemp()
    fp = os.path.join(tmp, "c.json")
    io.open(fp, "w", encoding="utf-8").write(json.dumps(
        {"epg_url": "https://vidu/", "token": "abc", "timeout": 30}))
    cfg = load_config(fp)
    check("đọc url từ file", cfg["epg_url"] == "https://vidu", cfg["epg_url"])
    check("cắt dấu / cuối url", not cfg["epg_url"].endswith("/"))
    check("đọc token từ file", cfg["token"] == "abc")

    os.environ["EPG_URL"] = "https://khac"
    os.environ["EPG_CRAWL_TOKEN"] = "xyz"
    cfg = load_config(fp)
    check("biến môi trường đè lên file", cfg["epg_url"] == "https://khac"
          and cfg["token"] == "xyz")
    del os.environ["EPG_URL"], os.environ["EPG_CRAWL_TOKEN"]

    try:
        load_config(os.path.join(tmp, "khong-co.json"))
        check("thiếu url thì báo lỗi", False, "không báo")
    except EpgError:
        check("thiếu url/token thì báo lỗi rõ", True)


def test_client(url):
    print("\n--- Client nói chuyện với EPG ---")
    c = EpgClient(url, TOKEN)
    o = c.orders()
    check("đọc được lệnh", o["enabled"] is True and o["times"] == ["05:00", "17:00"])
    check("thấy kênh tự động", o["channels"][0]["mode"] == "tu_dong")

    d = c.heartbeat(run_at="2026-09-09 05:00", ok=40, failed=2, message="xong")
    check("gửi được nhịp tim", d.get("ok") is True)

    # đẩy một file .xls thật (nhỏ)
    tmp = tempfile.mkdtemp()
    fp = os.path.join(tmp, "VTV1EPG09092026.xls")
    io.open(fp, "wb").write(b"\xd0\xcf\x11\xe0" + b"x" * 200)
    d = c.push_file(fp, "2026-09-09")
    check("đẩy được file", d.get("result") == "nap_duyet", str(d))
    check("EPG nhận được đúng là multipart có tên file", d.get("co_ten") is True)


def test_token(url):
    print("\n--- Sai/thiếu token ---")
    c = EpgClient(url, "khoa sai")
    try:
        c.orders()
        check("sai token thì báo lỗi", False, "không báo")
    except EpgError as e:
        check("sai token thì báo lỗi rõ", "Token sai" in str(e), str(e)[:60])

    EpgGia.da_bat = False
    try:
        EpgClient(url, TOKEN).orders()
        check("chưa bật token thì báo lỗi", False)
    except EpgError as e:
        check("chưa bật thì nói 'chưa bật tính năng cào'",
              "chưa bật" in str(e), str(e)[:70])
    EpgGia.da_bat = True


def test_epg_sap():
    print("\n--- EPG sập thì báo, không treo ---")
    c = EpgClient("http://127.0.0.1:1", TOKEN, timeout=2)
    try:
        c.orders()
        check("nối cổng chết thì báo lỗi", False)
    except EpgError as e:
        check("nối không được thì báo lỗi rõ ràng",
              "Không nối được" in str(e), str(e)[:60])


def test_push_folder(url):
    print("\n--- Đẩy cả thư mục ---")
    EpgGia.nhan = []
    tmp = tempfile.mkdtemp()
    for n in ("VTV1EPG09092026.xls", "VTV2EPG09092026.xls", "bo-qua.txt"):
        io.open(os.path.join(tmp, n), "wb").write(b"\xd0\xcf" + b"x" * 100)
    c = EpgClient(url, TOKEN)
    ket, ok, hong = push_output.push_folder(c, tmp, "2026-09-09")
    check("chỉ đẩy file .xls, bỏ .txt", len(ket) == 2, str([k[0] for k in ket]))
    check("cả hai gửi được", ok == 2 and hong == 0, "%d/%d" % (ok, hong))

    d = push_output.ngay_tu_thu_muc("output/2026-09-09")
    check("đoán ngày từ tên thư mục", d == "2026-09-09", str(d))
    check("thư mục không có ngày thì trả None",
          push_output.ngay_tu_thu_muc("linh-tinh") is None)


def test_lich_tho_nen():
    print("\n--- Logic canh giờ của thợ nền ---")
    st = {}
    ngay = "2026-09-09"
    check("mốc chưa chạy thì báo chưa chạy",
          not crawl_and_push._slot_da_chay(st, ngay, "05:00"))
    crawl_and_push._danh_dau_chay(ngay, "05:00"); st = crawl_and_push.load_state()
    check("đánh dấu rồi thì báo đã chạy",
          crawl_and_push._slot_da_chay(st, ngay, "05:00"))
    check("mốc khác vẫn chưa chạy",
          not crawl_and_push._slot_da_chay(st, ngay, "17:00"))
    # dọn ngày cũ
    crawl_and_push._danh_dau_chay("2026-09-10", "05:00"); st = crawl_and_push.load_state()
    check("ngày cũ bị dọn khi sang ngày mới",
          "2026-09-09" not in st.get("ran", {}))


def test_run_now():
    print("\n--- Đồng bộ ngay (run_now) ---")

    class ClientGia:
        def __init__(self, orders):
            self._o = orders
        def orders(self):
            return self._o
        def heartbeat(self, **k):
            return {"ok": True}

    class _Stop(Exception):
        pass

    def mot_vong(client):
        """Chạy đúng một vòng daemon rồi dừng (time.sleep ném _Stop)."""
        def sleep_stop(_n):
            raise _Stop
        goc = crawl_and_push.time.sleep
        crawl_and_push.time.sleep = sleep_stop
        try:
            crawl_and_push.daemon({}, client, poll=0)
        except _Stop:
            pass
        finally:
            crawl_and_push.time.sleep = goc

    tmp = tempfile.mkdtemp()
    goc_state = crawl_and_push.STATE_FILE
    crawl_and_push.STATE_FILE = os.path.join(tmp, "state.json")
    goc_cvd = crawl_and_push.cao_va_day
    dem = {"n": 0}
    crawl_and_push.cao_va_day = lambda cfg, client, **k: (
        dem.__setitem__("n", dem["n"] + 1),
        {"ok": 1, "failed": 0, "message": "x"})[1]
    try:
        cl = ClientGia({"enabled": False, "times": [], "channels": [],
                        "run_now": "2026-09-18 10:00:00"})
        mot_vong(cl)
        check("có yêu cầu -> cào một lần", dem["n"] == 1, str(dem["n"]))
        check("đã dấu mốc đã xử lý",
              crawl_and_push.load_state().get("run_now_done")
              == "2026-09-18 10:00:00")

        mot_vong(cl)     # cùng mốc, không cào lại
        check("cùng mốc thì KHÔNG cào lại", dem["n"] == 1, str(dem["n"]))

        cl._o["run_now"] = "2026-09-18 11:00:00"   # mốc mới
        mot_vong(cl)
        check("mốc mới thì cào lại", dem["n"] == 2, str(dem["n"]))

        cl._o["run_now"] = None      # không có yêu cầu -> không cào
        mot_vong(cl)
        check("không có yêu cầu thì không cào", dem["n"] == 2, str(dem["n"]))
    finally:
        crawl_and_push.cao_va_day = goc_cvd
        crawl_and_push.STATE_FILE = goc_state


def test_normalize():
    """write_xls dọn dữ liệu cào: bỏ mục lệch ngày, gộp mục trùng giờ,
    tính lại thời lượng — không để EPG từ chối cả file."""
    print("\n--- Dọn dữ liệu cào (normalize_epg_rows) ---")
    import datetime as dt
    D = dt.datetime
    rows = [
        {"start_dt": D(1, 1, 1, 0, 0), "duration": dt.timedelta(days=9),
         "program": "rác 0001"},
        {"start_dt": D(2026, 9, 9, 6, 0), "duration": dt.timedelta(0),
         "program": "Sáng"},
        {"start_dt": D(2026, 9, 9, 11, 45), "duration": dt.timedelta(0),
         "program": "Trùng 1"},
        {"start_dt": D(2026, 9, 9, 11, 45), "duration": dt.timedelta(minutes=30),
         "program": "Trùng 2"},
        {"start_dt": D(2026, 9, 9, 12, 15), "duration": dt.timedelta(minutes=45),
         "program": "Trưa"},
    ]
    out = fetch_tv_schedule.normalize_epg_rows(rows)
    check("bỏ mục lệch ngày (0001)", all(r["start_dt"].year == 2026 for r in out))
    check("gộp mục trùng giờ còn một", len(out) == 3, str(len(out)))
    check("không còn thời lượng 0",
          all(r["duration"].total_seconds() > 0 for r in out))
    check("không còn trùng giờ bắt đầu",
          len({r["start_dt"] for r in out}) == len(out))
    check("mục trùng giữ bản sau cùng",
          any(r["program"] == "Trùng 2" for r in out))
    # rỗng thì trả nguyên
    check("danh sách rỗng thì không lỗi",
          fetch_tv_schedule.normalize_epg_rows([]) == [])


def main():
    srv, url = start_gia()
    try:
        test_config()
        test_client(url)
        test_token(url)
        test_epg_sap()
        test_push_folder(url)
        test_lich_tho_nen()
        test_run_now()
        test_normalize()
    finally:
        srv.shutdown()

    print("\n" + "=" * 60)
    print("  %d dat - %d hong" % (len(PASS), len(FAIL)))
    if FAIL:
        for n in FAIL:
            print("    - " + n)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
