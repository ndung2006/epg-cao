# Thợ nền cào lịch + đẩy sang EPG — chạy trong Docker (Coolify).
#
# Bốn điều phải nhớ:
#
# 1. MÚI GIỜ. Thợ nền so giờ hiện tại với "giờ mong muốn" (ví dụ 07:01) để
#    biết đã tới lúc cào chưa. Container mặc định chạy UTC, nên 07:01 sẽ nổ
#    vào 07:01 UTC = 14:01 giờ Việt Nam. Phải cài tzdata + đặt TZ.
#
# 2. TOKEN + ĐỊA CHỈ EPG. KHÔNG nhúng vào ảnh. Đặt qua biến môi trường trên
#    Coolify: EPG_URL và EPG_CRAWL_TOKEN. Danh sách lệnh cào thì nằm trong
#    epg_push_config.docker.json (không phải bí mật, nên nằm trong ảnh).
#
# 3. TRẠNG THÁI. Biến EPG_PUSH_STATE trỏ vào /data để nhớ mốc đã cào qua
#    các lần khởi động lại — khỏi cào lại. Gắn volume vào /data.
#
# 4. KHÔNG CHẠY BẰNG ROOT.

FROM python:3.14-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Ho_Chi_Minh \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EPG_PUSH_CONFIG=/app/epg_push_config.docker.json \
    EPG_PUSH_STATE=/data/.epg_push_state.json

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ ./scripts/
COPY epg_push_config.docker.json ./

RUN useradd --create-home --shell /usr/sbin/nologin cao \
 && mkdir -p /data/output \
 && chown -R cao:cao /data
USER cao

# Chạy nền: cứ vài phút hỏi lịch EPG, tới giờ mong muốn thì cào + đẩy.
CMD ["python", "scripts/crawl_and_push.py", "--daemon", "--poll", "120"]
