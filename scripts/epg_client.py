#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nói chuyện với hệ thống nhập liệu EPG: đọc lệnh, đẩy file, báo nhịp tim.

Đây là phía CRAWLER của mô hình "một app + thợ nền". App EPG là não (giữ
lịch cào, kênh nào tự động), crawler là thợ: hỏi lệnh, cào, đẩy kết quả về.

Ba cửa của EPG, đều đi một chiều crawler -> EPG, khoá bằng token:

    GET  /api/crawl/orders      đọc: bật/tắt, giờ mong muốn, kênh nào tự động
    POST /api/crawl/push        đẩy một file .xls
    POST /api/crawl/heartbeat   báo còn sống + tóm tắt lần cào

Token và địa chỉ EPG nằm trong file cấu hình (xem epg_push_config.example
.json) hoặc biến môi trường EPG_URL / EPG_CRAWL_TOKEN. Không nhúng vào mã.

Cô lập: file này KHÔNG import gì của phần cào (không bs4, không xlwt). Nó
chỉ gửi file có sẵn đi. Phần cào hỏng cũng không kéo theo phần đẩy, và
ngược lại.
"""

import json
import os

import requests

# Tên biến môi trường / khoá cấu hình
ENV_URL = "EPG_URL"
ENV_TOKEN = "EPG_CRAWL_TOKEN"
ENV_CONFIG = "EPG_PUSH_CONFIG"
TOKEN_HEADER = "X-Crawl-Token"

# Chỗ tìm file cấu hình, theo thứ tự ưu tiên
_CONFIG_NAMES = ("epg_push_config.json", "epg_push_config.local.json")


class EpgError(Exception):
    """Không nói chuyện được với EPG. Lời nhắn viết cho người vận hành đọc."""


# --------------------------------------------------------------- cấu hình

def load_config(path=None):
    """Đọc cấu hình từ file JSON và/hoặc biến môi trường.

    Thứ tự: biến môi trường đè lên file. Nhờ vậy đặt tạm EPG_URL /
    EPG_CRAWL_TOKEN lúc chạy thử mà không phải sửa file.
    """
    cfg = {
        "epg_url": "",
        "token": "",
        "output_dir": "./output",
        "verify_tls": True,
        "timeout": 60,
        # Danh sách lệnh cào chạy trước khi đẩy. Mỗi lệnh là một danh sách
        # đối số. {output} được thay bằng thư mục output/<ngày>. Để trống
        # thì crawl_and_push chỉ đẩy những file đã có sẵn, không cào lại.
        "crawl_commands": [],
    }

    p = path or os.environ.get(ENV_CONFIG)
    if not p:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in _CONFIG_NAMES:
            thu = os.path.join(here, name)
            if os.path.isfile(thu):
                p = thu
                break
    if p and os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            cfg.update(json.load(f))

    if os.environ.get(ENV_URL):
        cfg["epg_url"] = os.environ[ENV_URL]
    if os.environ.get(ENV_TOKEN):
        cfg["token"] = os.environ[ENV_TOKEN]

    cfg["epg_url"] = (cfg["epg_url"] or "").rstrip("/")
    if not cfg["epg_url"]:
        raise EpgError("Chưa đặt địa chỉ EPG (epg_url trong file cấu hình "
                       "hoặc biến môi trường EPG_URL).")
    if not cfg["token"]:
        raise EpgError("Chưa đặt token (token trong file cấu hình hoặc biến "
                       "môi trường EPG_CRAWL_TOKEN).")
    return cfg


# ----------------------------------------------------------------- client

class EpgClient:
    def __init__(self, url, token, verify_tls=True, timeout=60):
        self.url = url.rstrip("/")
        self.token = token
        self.verify_tls = verify_tls
        self.timeout = timeout

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg["epg_url"], cfg["token"],
                   verify_tls=cfg.get("verify_tls", True),
                   timeout=cfg.get("timeout", 60))

    def _hdr(self):
        return {TOKEN_HEADER: self.token}

    def _diagnose(self, r):
        """Đổi mã lỗi HTTP thành lời nhắn người đọc hiểu."""
        if r.status_code == 503:
            return ("EPG chưa bật tính năng cào: máy chủ chưa đặt biến "
                    "EPG_CRAWL_TOKEN. Báo người quản trị EPG.")
        if r.status_code == 403:
            return ("Token sai — khoá ở crawler khác khoá EPG_CRAWL_TOKEN "
                    "trên máy chủ EPG.")
        try:
            return r.json().get("error") or r.text[:200]
        except Exception:                       # noqa: BLE001
            return r.text[:200]

    def orders(self):
        """Đọc lệnh: cào gì, giờ nào, kênh nào tự động."""
        try:
            r = requests.get(self.url + "/api/crawl/orders",
                             headers=self._hdr(), timeout=self.timeout,
                             verify=self.verify_tls)
        except requests.RequestException as e:
            raise EpgError("Không nối được tới EPG (%s): %s" % (self.url, e))
        if r.status_code != 200:
            raise EpgError("Đọc lệnh hỏng (HTTP %d): %s"
                           % (r.status_code, self._diagnose(r)))
        return r.json()

    def push_file(self, path, air_date):
        """Đẩy một file .xls lên EPG cho ngày phát air_date (YYYY-MM-DD).

        Trả về dict kết quả của EPG: result là 'nap_duyet' / 'nap_nhap' /
        'luu' / 'loi', kèm message tiếng Việt. KHÔNG ném lỗi khi EPG từ chối
        nội dung file (đó là kết quả hợp lệ, ghi lại rồi đi tiếp) — chỉ ném
        khi không nói chuyện được với EPG.
        """
        name = os.path.basename(path)
        try:
            with open(path, "rb") as f:
                r = requests.post(
                    self.url + "/api/crawl/push",
                    headers=self._hdr(),
                    data={"air_date": air_date},
                    files={"file": (name, f, "application/vnd.ms-excel")},
                    timeout=self.timeout, verify=self.verify_tls)
        except requests.RequestException as e:
            raise EpgError("Không đẩy được %s tới EPG: %s" % (name, e))
        if r.status_code != 200:
            raise EpgError("Đẩy %s hỏng (HTTP %d): %s"
                           % (name, r.status_code, self._diagnose(r)))
        return r.json()

    def heartbeat(self, run_at=None, ok=0, failed=0, message=None):
        """Báo còn sống + tóm tắt lần cào gần nhất."""
        try:
            r = requests.post(
                self.url + "/api/crawl/heartbeat",
                headers=self._hdr(),
                json={"run_at": run_at, "ok": ok, "failed": failed,
                      "message": message},
                timeout=self.timeout, verify=self.verify_tls)
        except requests.RequestException as e:
            raise EpgError("Không gửi được nhịp tim: %s" % e)
        if r.status_code != 200:
            raise EpgError("Nhịp tim hỏng (HTTP %d): %s"
                           % (r.status_code, self._diagnose(r)))
        return r.json()
