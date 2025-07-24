#!/bin/bash

# ==============================================================================
# OCP Create ISO Flask Application Deployment Script
# ==============================================================================
# 이 스크립트는 다음 작업을 수행합니다:
# 1. 필수 시스템 패키지를 설치합니다.
# 2. 애플리케이션 디렉터리를 생성하고 소스 파일을 복사합니다.
# 3. Python 의존성을 설치합니다.
# 4. systemd 서비스 파일을 생성하고 sudo 권한을 부여합니다.
# 5. 방화벽 및 SELinux를 구성합니다.
# 6. 서비스를 활성화하고 시작합니다.
#
# **실행 방법:**
# 1. 이 스크립트를 Git으로 복제한 프로젝트의 루트 디렉터리에 위치시킵니다.
# 2. 실행 권한을 부여합니다: chmod +x ./1.scripts.sh
# 3. root 권한으로 스크립트를 실행합니다: sudo ./1.scripts.sh
# ==============================================================================

# --- 변수 정의 ---
APP_BASE_DIR="/var/www/html"
APP_NAME="ocp-create-iso"
APP_PORT=5024
SERVICE_NAME="ocp-create-iso"
APP_USER="apache"
APP_GROUP="apache"

# --- 스크립트 실행 ---
set -e

if [ "$(id -u)" -ne 0 ]; then
   echo "이 스크립트는 반드시 root 권한으로 실행해야 합니다."
   exit 1
fi

SOURCE_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
APP_TARGET_DIR="${APP_BASE_DIR}/${APP_NAME}"

echo ">>> 소스 경로: $SOURCE_DIR"
echo ">>> 배포 경로: $APP_TARGET_DIR"
echo

# 1. 필수 시스템 패키지 설치
echo ">>> [단계 1/8] 필수 시스템 패키지 설치"
dnf install -y python3 python3-pip git gcc python3-devel rsync policycoreutils-python-utils bind-utils chrony haproxy
pip3 install gunicorn
echo "패키지 설치 완료."
echo

# 2. 배포 디렉터리 준비
echo ">>> [단계 2/8] 배포 디렉터리 준비"
mkdir -p "$APP_BASE_DIR"
rm -rf "$APP_TARGET_DIR"
rsync -av "$SOURCE_DIR/" "$APP_TARGET_DIR/"
echo "파일 복사 완료."
echo

# 3. Python 의존성 설치
echo ">>> [단계 3/8] requirements.txt를 이용한 Python 라이브러리 설치"
if [ -f "$APP_TARGET_DIR/requirements.txt" ]; then
    pip3 install -r "$APP_TARGET_DIR/requirements.txt"
else
    pip3 install flask pandas openpyxl PyYAML
fi
chown -R $APP_USER:$APP_GROUP "$APP_TARGET_DIR"
echo "Python 라이브러리 및 소유권 설정 완료."
echo

# 4. systemd 서비스 파일 생성
echo ">>> [단계 4/8] systemd 서비스 파일 생성"
cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=OCP Create ISO Gunicorn Service
After=network.target

[Service]
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$APP_TARGET_DIR
ExecStart=$(command -v gunicorn) --workers 4 --bind 0.0.0.0:${APP_PORT} --timeout 1200 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF
echo "systemd 서비스 파일 생성 완료."
echo

# 5. sudoers 파일 생성 (가장 중요)
echo ">>> [단계 5/8] sudo 권한 설정"
# 이 앱이 시스템을 변경하기 위해 필요한 모든 명령어를 NOPASSWD로 허용
cat <<EOF > /etc/sudoers.d/ocp-iso-creator
# Allow apache user to run specific commands for OCP ISO creation
apache ALL=(ALL) NOPASSWD: /usr/bin/hostnamectl
apache ALL=(ALL) NOPASSWD: /usr/bin/nmcli
apache ALL=(ALL) NOPASSWD: /usr/bin/systemctl
apache ALL=(ALL) NOPASSWD: /usr/bin/cp
apache ALL=(ALL) NOPASSWD: /usr/bin/mv
apache ALL=(ALL) NOPASSWD: /usr/bin/rm
apache ALL=(ALL) NOPASSWD: /usr/bin/tee
apache ALL=(ALL) NOPASSWD: /usr/bin/chown
apache ALL=(ALL) NOPASSWD: /usr/sbin/setsebool
apache ALL=(ALL) NOPASSWD: /usr/sbin/semanage
apache ALL=(ALL) NOPASSWD: /usr/local/bin/mirror-registry
apache ALL=(ALL) NOPASSWD: /usr/bin/update-ca-trust
apache ALL=(ALL) NOPASSWD: /usr/local/bin/oc
apache ALL=(ALL) NOPASSWD: /usr/local/bin/openshift-install
EOF
chmod 440 /etc/sudoers.d/ocp-iso-creator
echo "sudoers 파일 생성 완료."
echo


# /opt 디렉터리에 대한 쓰기 권한 허용
sudo setsebool -P httpd_unified 1

# Quay 디렉터리에 대한 컨텍스트 설정
sudo semanage fcontext -a -t container_file_t "/opt/openshift/init-quay(/.*)?"
sudo restorecon -Rv /opt/openshift/init-quay





# 6. 방화벽 및 SELinux 포트 설정
echo ">>> [단계 6/8] 방화벽 및 SELinux 구성"
# 웹 앱 포트
firewall-cmd --permanent --add-port=${APP_PORT}/tcp
# HAProxy 포트
firewall-cmd --permanent --add-port=6443/tcp
firewall-cmd --permanent --add-port=22623/tcp
firewall-cmd --permanent --add-port=9000/tcp
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp
# DNS 포트
firewall-cmd --permanent --add-service=dns
firewall-cmd --reload

semanage port -a -t http_port_t -p tcp ${APP_PORT} || true
semanage port -a -t http_port_t -p tcp 6443 || true
semanage port -a -t http_port_t -p tcp 22623 || true
echo "방화벽 및 SELinux 포트 설정 완료."
echo

# 7. SELinux 컨텍스트 설정
echo ">>> [단계 7/8] SELinux 컨텍스트 설정"
# 웹 서버가 앱 파일에 접근할 수 있도록 설정
chcon -R -t httpd_sys_content_t "$APP_TARGET_DIR"
# 웹 서버가 네트워크에 연결하고, named/chrony/haproxy 설정 파일을 수정할 수 있도록 허용
setsebool -P httpd_can_network_connect 1
setsebool -P httpd_manage_ipa 1
setsebool -P haproxy_connect_any=1
echo "SELinux 컨텍스트 설정 완료."
echo

sudo semanage permissive -a httpd_t


# 8. 서비스 활성화 및 시작
echo ">>> [단계 8/8] 서비스 활성화 및 시작"
systemctl daemon-reload
systemctl restart ${SERVICE_NAME}.service
systemctl enable ${SERVICE_NAME}.service
echo "서비스가 활성화되고 시작되었습니다."
echo


sudo semanage fcontext -a -t httpd_sys_rw_content_t "/var/www/html/ocp-installer-helper/data(/.*)?"
sudo restorecon -Rv /var/www/html/ocp-installer-helper/data
sudo semanage fcontext -a -t named_conf_t "/etc/named.conf"
sudo semanage fcontext -a -t named_conf_t "/etc/named.rfc1912.zones"
sudo semanage fcontext -a -t named_zone_t "/var/named(/.*)?"
sudo restorecon -Rv /etc/named.conf /etc/named.rfc1912.zones /var/named
sudo semanage fcontext -a -t chronyd_conf_t "/etc/chrony.conf"
sudo restorecon -Rv /etc/chrony.conf
sudo semanage fcontext -a -t haproxy_etc_t "/etc/haproxy/haproxy.cfg"
sudo restorecon -Rv /etc/haproxy/haproxy.cfg
# /opt 디렉터리에 대한 쓰기 권한 허용
sudo setsebool -P httpd_unified 1

# Quay 디렉터리에 대한 컨텍스트 설정
sudo semanage fcontext -a -t container_file_t "/opt/openshift/init-quay(/.*)?"
sudo restorecon -Rv /opt/openshift/init-quay

sudo systemctl restart ocp-create-iso.service


echo "=================================================="
echo "OCP ISO 생성 도우미 배포가 완료되었습니다."
echo "서비스 상태: sudo systemctl status ${SERVICE_NAME}.service"
echo "접속 주소: http://<서버_IP_주소>:${APP_PORT}"
echo "=================================================="
