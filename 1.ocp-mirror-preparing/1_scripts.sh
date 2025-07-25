#!/bin/bash

# ==============================================================================
# OCP Installer Helper Flask Application Deployment Script for RHEL 9.x (v3)
# ==============================================================================
# 이 스크립트는 자신의 위치를 기준으로 소스 경로를 자동으로 감지하여
# Flask 애플리케이션을 배포하고 systemd 서비스로 등록합니다.
#
# **실행 방법:**
# 1. 이 스크립트 파일을 배포하려는 프로젝트의 루트 디렉터리에 위치시킵니다.
#    (예: /ocp-mirror-preparing/1_scipts.sh)
# 2. 실행 권한을 부여합니다: chmod +x /ocp-mirror-preparing/1_scipts.sh
# 3. root 권한으로 스크립트를 실행합니다.
#    sudo /ocp-mirror-preparing/1_scipts.sh
# ==============================================================================

# --- 변수 정의 ---
# 웹 애플리케이션을 배포할 부모 디렉터리
APP_BASE_DIR="/var/www/html"

# 애플리케이션이 사용할 포트
APP_PORT=5022

# systemd 서비스 이름
SERVICE_NAME="ocp-mirror-preparing"

# 웹 서비스를 실행할 사용자 (RHEL 기본 웹 서버 사용자인 'apache' 권장)
APP_USER="apache"
APP_GROUP="apache"


# --- 스크립트 실행 ---

# 스크립트 실행 중 오류가 발생하면 즉시 중단
set -e

# 0. 루트 권한 확인
if [ "$(id -u)" -ne 0 ]; then
   echo "이 스크립트는 반드시 root 권한으로 실행해야 합니다."
   exit 1
fi

# 1. 스크립트가 위치한 디렉터리를 소스 디렉터리로 자동 감지
# 심볼릭 링크 등을 모두 해석하여 실제 경로를 찾습니다.
SOURCE_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# 최종적으로 애플리케이션이 위치할 전체 경로
APP_TARGET_DIR="${APP_BASE_DIR}/$(basename "$SOURCE_DIR")"

echo ">>> 자동 감지된 소스 경로: $SOURCE_DIR"
echo ">>> 최종 배포될 경로: $APP_TARGET_DIR"
echo

sudo mkdir /ocp_install/


# --- httpd 포트를 8080으로 변경 ---
echo "⚙️ httpd 포트를 80에서 8080으로 변경합니다..."
sudo sed -i 's/Listen 80/Listen 8080/g' /etc/httpd/conf/httpd.conf

# --- SELinux에 8080 포트 허용 정책 추가 ---
echo "🛡️ SELinux가 httpd의 8080 포트 사용을 허용하도록 정책을 추가합니다..."
# http_port_t 타입에 8080/tcp 포트를 추가합니다. 이미 존재하면 무시합니다.
if ! sudo semanage port -l | grep -q "^http_port_t.*tcp.*8080"; then
    sudo semanage port -a -t http_port_t -p tcp 8080
fi

sudo systemctl enable --now libvirtd



# 2. 필수 시스템 패키지 설치
echo ">>> [단계 1/7] 필수 시스템 패키지 설치"
#dnf install -y python3 python3-pip git gcc python3-devel rsync
echo "Gunicorn (WSGI 서버)을 설치합니다..."
sudo pip3 install beautifulsoup4 requests gunicorn 
echo "패키지 설치 완료."
echo


sudo bash -c 'cat <<EOF > /etc/sudoers.d/ocp-preparer
# Allow apache user to run specific commands without a password
apache ALL=(ALL) NOPASSWD: /usr/bin/tar
apache ALL=(ALL) NOPASSWD: /usr/bin/chmod
apache ALL=(ALL) NOPASSWD: /usr/bin/mv
apache ALL=(ALL) NOPASSWD: /usr/bin/mkdir
apache ALL=(ALL) NOPASSWD: /usr/bin/chown
apache ALL=(ALL) NOPASSWD: /usr/bin/oc
apache ALL=(ALL) NOPASSWD: /usr/bin/oc-mirror
EOF'


sudo semanage fcontext -a -t httpd_sys_rw_content_t "/ocp_install(/.*)?"
sudo restorecon -Rv /ocp_install

sudo chown apache:apache /usr/share/httpd


# 2. 기존 디렉터리 정리 및 부모 디렉터리 생성
echo ">>> [단계 2/7] 배포 디렉터리 준비"
# 배포할 부모 디렉터리 생성
mkdir -p "$APP_BASE_DIR"
# 만약 타겟 디렉터리가 이미 존재한다면 삭제 (rsync --delete와 함께 사용)
rm -rf "$APP_TARGET_DIR"
echo "타겟 디렉터리 준비 완료: $APP_BASE_DIR"
echo




# 3. 소스 디렉터리를 타겟 위치로 복사 (디렉터리 구조 유지)
echo ">>> [단계 3/7] 애플리케이션 파일 복사"
# rsync의 마지막 '/'는 디렉터리 내용만 복사할지, 디렉터리 자체를 복사할지 결정합니다.
# 여기서는 디렉터리 자체를 복사하기 위해 '/'를 붙이지 않습니다.
rsync -av "$SOURCE_DIR" "$APP_BASE_DIR/"
echo "파일 복사 완료."
echo

# 4. 애플리케이션 파일들의 소유권을 웹 서버 사용자로 변경
chown -R $APP_USER:$APP_GROUP "$APP_TARGET_DIR"
echo "파일 소유권 변경 완료: $APP_USER:$APP_GROUP"
echo

# 5. systemd 서비스 파일 생성
echo ">>> [단계 5/7] systemd 서비스 파일 생성: /etc/systemd/system/${SERVICE_NAME}.service"
cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=mirror preparing
After=network.target

[Service]
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$APP_TARGET_DIR
ExecStart=$(command -v gunicorn) --workers 4 --bind 0.0.0.0:${APP_PORT} --timeout 900 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF
echo "systemd 서비스 파일 생성 완료."
echo

# 7. 방화벽 및 SELinux 구성
echo ">>> [단계 6/7] 방화벽 및 SELinux 구성"
echo "방화벽에서 ${APP_PORT}/tcp 포트를 영구적으로 허용합니다."
#if ! firewall-cmd --query-port=${APP_PORT}/tcp --permanent > /dev/null 2>&1; then
#    firewall-cmd --permanent --add-port=${APP_PORT}/tcp
#    firewall-cmd --reload
#fi

sudo semanage permissive -a httpd_t

echo "SELinux 컨텍스트를 설정하고 네트워크 연결을 허용합니다."
# chcon: 웹 서버가 애플리케이션 파일에 접근할 수 있도록 컨텍스트 설정
chcon -R -t httpd_sys_content_t "$APP_TARGET_DIR"
# setsebool: httpd(apache)가 네트워크에 연결할 수 있도록 허용
setsebool -P httpd_can_network_connect 1
echo "방화벽 및 SELinux 구성 완료."
echo

# 8. 서비스 활성화 및 시작
echo ">>> [단계 7/7] 서비스 활성화 및 시작"
systemctl daemon-reload
systemctl restart ${SERVICE_NAME}.service
systemctl enable ${SERVICE_NAME}.service
echo "서비스가 활성화되고 시작되었습니다."
echo

# --- 최종 확인 ---
echo "=================================================="
echo "OCP 설치 도우미 애플리케이션 배포가 완료되었습니다."
echo
echo "다음 명령어로 서비스 상태를 확인할 수 있습니다:"
echo "sudo systemctl status ${SERVICE_NAME}.service"
echo
echo "웹 브라우저에서 아래 주소로 접속하세요:"
echo "http://<서버_IP_주소>:${APP_PORT}"
echo "=================================================="
