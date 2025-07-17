#!/bin/bash
set -e

echo "========================================================"
echo "🚀 1. RHEL 9 호스트 서버 초기 설정을 시작합니다..."
echo "========================================================"


# 1. Python Flask 설치
echo "🐍 Flask 웹 프레임워크를 설치합니다..."
pip install pandas openpyxl

# 2. 서비스 활성화 (httpd)
echo "⚙️ httpd 서비스를 활성화하고 시작합니다..."


# --- httpd 포트를 8080으로 변경 ---
echo "⚙️ httpd 포트를 80에서 8080으로 변경합니다..."
sudo sed -i 's/Listen 80/Listen 8080/g' /etc/httpd/conf/httpd.conf

# --- SELinux에 8080 포트 허용 정책 추가 ---
echo "🛡️ SELinux가 httpd의 8080 포트 사용을 허용하도록 정책을 추가합니다..."
# http_port_t 타입에 8080/tcp 포트를 추가합니다. 이미 존재하면 무시합니다.
if ! sudo semanage port -l | grep -q "^http_port_t.*tcp.*8080"; then
    sudo semanage port -a -t http_port_t -p tcp 8080
fi

sudo systemctl enable --now httpd


# 3. 관련 디렉토리 생성
echo "📁 웹 서버 및 애플리케이션 관련 디렉토리를 생성합니다..."
sudo mkdir -p /var/www/html/data_import/templates


echo "========================================================"
echo "🚚 2. 웹 애플리케이션 파일을 배포합니다..."
echo "========================================================"

APP_SOURCE="./app.py"
TEMPLATE_SOURCE="./index.html"

APP_DEST="/var/www/html/data_import/app.py"
TEMPLATE_DEST="/var/www/html/data_import/templates/index.html"

# 1. 소스 파일 존재 여부 확인
if [ ! -f "$APP_SOURCE" ]; then
    echo "❌ 오류: 현재 디렉토리에 'app.py' 파일이 없습니다."
    exit 1
fi

if [ ! -f "$TEMPLATE_SOURCE" ]; then
    echo "❌ 오류: './templates' 디렉토리에 'index.html' 파일이 없습니다."
    exit 1
fi

# 2. 파일 복사
echo " 'app.py' -> '${APP_DEST}'"
sudo cp "$APP_SOURCE" "$APP_DEST"

echo " 'templates/index.html' -> '${TEMPLATE_DEST}'"
sudo cp "$TEMPLATE_SOURCE" "$TEMPLATE_DEST"



echo "========================================================"
echo "⚙️ 3. Systemd 서비스를 등록하고 실행합니다..."
echo "========================================================"

SERVICE_FILE="/etc/systemd/system/data_import.service"

# 1. Systemd 서비스 파일 생성
echo "📝 서비스 파일을 생성합니다: ${SERVICE_FILE}"
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Flask data import Web UI
After=network.target

[Service]
User=root
# app.py가 있는 실제 경로로 지정해야 합니다.
WorkingDirectory=/var/www/html/data_import
# python3와 app.py의 절대 경로를 사용합니다.
ExecStart=/usr/bin/python3 /var/www/html/data_import/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo "✅ 서비스 파일 생성 완료."

# 2. 서비스 활성화 및 시작
echo "🔄 Systemd 데몬을 리로드합니다."
sudo systemctl daemon-reload

echo "🚀 서비스를 활성화하고 시작합니다..."
sudo systemctl enable data_import.service
sudo systemctl start data_import.service

echo ""
echo "🎉 모든 설정이 완료되었습니다! 서비스 상태를 확인합니다:"
echo "--------------------------------------------------------"
sudo systemctl status data_import.service --no-pager
echo "--------------------------------------------------------"
echo "웹 브라우저에서 http://<RHEL9_호스트_IP>:5012 으로 접속하세요."
