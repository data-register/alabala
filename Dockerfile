FROM python:3.11-slim

WORKDIR /app

# Инсталиране на необходимите пакети
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Копиране и инсталиране на Python зависимости
COPY requirements.txt .
# Специално фиксираме numpy на съвместима с OpenCV версия
RUN pip install --no-cache-dir numpy==1.24.3 && \
    pip install --no-cache-dir -r requirements.txt

# Създаване на структура на директории
RUN mkdir -p /app/frames && chmod 777 /app/frames && \
    mkdir -p /app/templates && chmod 777 /app/templates && \
    mkdir -p /app/modules && chmod 777 /app/modules && \
    mkdir -p /app/modules/rtsp_capture && chmod 777 /app/modules/rtsp_capture && \
    mkdir -p /app/utils && chmod 777 /app/utils && \
    mkdir -p /app/logs && chmod 777 /app/logs && \
    mkdir -p /app/static && chmod 777 /app/static && \
    mkdir -p /app/ptz_frames && chmod 777 /app/ptz_frames && \
    for i in $(seq 0 4); do \
        mkdir -p /app/ptz_frames/position_$i && chmod 777 /app/ptz_frames/position_$i; \
    done

# Копиране на модулите
COPY modules/ /app/modules/
COPY utils/ /app/utils/
COPY templates/ /app/templates/
COPY app.py .

# Създаваме празен placeholder файл в директорията ptz_frames
RUN touch /app/ptz_frames/TEST && \
    touch /app/ptz_frames/position_0/TEST && \
    touch /app/ptz_frames/position_1/TEST && \
    touch /app/ptz_frames/position_2/TEST && \
    touch /app/ptz_frames/position_3/TEST && \
    touch /app/ptz_frames/position_4/TEST

# Порт, на който ще работи приложението
EXPOSE 7860

# Стартиране на приложението
CMD ["python", "app.py"]