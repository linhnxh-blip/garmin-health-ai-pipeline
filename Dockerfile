# ==============================================================================
# GARMIN HEALTH AI PIPELINE - DOCKERFILE (FOR ASUS ROG ALLY X / WSL2 SERVER)
# ==============================================================================
FROM python:3.11-slim

# Tối ưu hóa biến môi trường cho Python chạy trong Container
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /app

# Cài đặt các gói hệ thống cơ bản & sqlite3
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn sạch vào Container
COPY . .

# Tạo sẵn các thư mục lưu trữ bền vững
RUN mkdir -p /app/data /app/logs /app/backups

# Mở cổng Web Dashboard (mặc định 8000)
EXPOSE 8000

# Lệnh mặc định (được ghi đè cho từng service trong docker-compose.yml)
CMD ["python", "main.py", "web", "--host", "0.0.0.0", "--port", "8000"]

