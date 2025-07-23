import os
import json
import subprocess
import shutil
from flask import Flask, render_template, request, jsonify, render_template_string
from io import StringIO
import csv

# --- 기본 설정 ---
app = Flask(__name__)
# 공유 데이터 경로 (이전 앱에서 사용하던 경로)
SHARED_DATA_PATH = "/var/www/html/ocp-installer-helper/data/cluster_info.json"

# --- Helper 함수 ---
def run_command(command):
    """지정된 셸 명령어를 실행하고 결과를 반환합니다."""
    try:
        result = subprocess.run(
            command, shell=True, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return {"success": True, "output": result.stdout, "error": result.stderr}
    except subprocess.CalledProcessError as e:
        return {"success": False, "output": e.stdout, "error": e.stderr}

def load_cluster_data():
    """공유 JSON 파일에서 클러스터 데이터를 로드합니다."""
    try:
        with open(SHARED_DATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def backup_file(filepath):
    """파일을 백업합니다."""
    if os.path.exists(filepath):
        backup_path = f"{filepath}.bak_{os.getpid()}"
        shutil.copy2(filepath, backup_path)
        return f"기존 파일 백업: {backup_path}"
    return "백업할 기존 파일 없음"

def write_file_as_root(filepath, content):
    """파일을 root 권한으로 씁니다."""
    # tee 명령어를 사용하여 root 권한으로 파일 생성/덮어쓰기
    command = f"echo '{content}' | sudo tee {filepath}"
    return run_command(command)

# --- 기본 페이지 및 API 라우팅 ---
@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

# --- Section 1: CSV 업로드 ---
@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    """CSV 파일을 업로드 받아 공유 JSON 파일로 저장합니다."""
    if 'csv_file' not in request.files:
        return jsonify({"success": False, "error": "파일이 없습니다."})
    file = request.files['csv_file']
    if file.filename == '':
        return jsonify({"success": False, "error": "파일이 선택되지 않았습니다."})
    
    try:
        stream = StringIO(file.stream.read().decode("UTF-8"), newline=None)
        csv_reader = csv.reader(stream)
        keys = next(csv_reader)
        values = next(csv_reader)
        cluster_data = dict(zip(keys, values))
        
        # 공유 디렉터리가 없을 경우 생성
        os.makedirs(os.path.dirname(SHARED_DATA_PATH), exist_ok=True)
        
        with open(SHARED_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(cluster_data, f, indent=4, ensure_ascii=False)
        return jsonify({"success": True, "message": f"✅ 클러스터 정보가 {SHARED_DATA_PATH}에 저장되었습니다."})
    except Exception as e:
        return jsonify({"success": False, "error": f"파일 처리 중 오류 발생: {e}"})

# --- Section 2: Bastion 확정 ---
@app.route('/api/configure', methods=['POST'])
def configure_bastion():
    config_type = request.json.get('type')
    data = load_cluster_data()
    if not data:
        return jsonify({"success": False, "error": "클러스터 정보(cluster_info.json)가 없습니다. 먼저 CSV를 업로드하세요."})

    # --- Hostname 변경 ---
    if config_type == 'hostname':
        hostname = f"{data['hostname_bastion']}.{data['metadata_name']}.{data['base_domain']}"
        return jsonify(run_command(f"sudo hostnamectl set-hostname {hostname}"))

    # --- IP 변경 ---
    elif config_type == 'ip':
        ip = data['nodeip_bastion']
        prefix = data['prefix_master0'] # 예시로 master0의 prefix 사용
        gateway = data['gw_master0'] # gw_bastion 키가 없을 경우 대비
        dns = data['nodeip_bastion']
        search_domain = f"{data['metadata_name']}.{data['base_domain']}"
        # nmcli를 사용하여 네트워크 설정 변경 (더 안정적)
        # 실제 인터페이스 이름(예: eth0)을 알아야 함. 여기서는 'enp1s0'으로 가정.
        # 이 부분은 환경에 맞게 수정이 필요할 수 있습니다.
        interface_name = "enf1s0" 
        command = (
            f"sudo nmcli connection modify {interface_name} "
            f"ipv4.method manual ipv4.addresses {ip}/{prefix} "
            f"ipv4.gateway {gateway} ipv4.dns {dns} ipv4.dns-search {search_domain} && "
            f"sudo nmcli connection up {interface_name}"
        )
        return jsonify(run_command(command))

    # --- DNS 설정 ---
    elif config_type == 'dns':
        # named.conf 수정
        backup_file("/etc/named.conf")
        run_command("sudo sed -i 's/dnssec-validation yes;/dnssec-validation no;/' /etc/named.conf")
        run_command("sudo sed -i '/listen-on-v6/a \\        forwarders { 8.8.8.8; };\\n        forward first;\\n' /etc/named.conf")
        
        # named.rfc1912.zones 수정
        backup_file("/etc/named.rfc1912.zones")
        rev_ip = '.'.join(data['machine_network_cidr'].split('/')[0].split('.')[:3][::-1])
        zone_config = render_template_string(
            open('templates/named.rfc1912.zones.j2').read(),
            base_domain=data['base_domain'],
            rev_ip=rev_ip
        )
        run_command(f"echo '{zone_config}' | sudo tee -a /etc/named.rfc1912.zones")

        # zone 파일 생성
        zone_content = render_template_string(open('templates/domain.zone.j2').read(), data=data)
        write_file_as_root(f"/var/named/{data['base_domain']}.zone", zone_content)

        # rev 파일 생성
        rev_content = render_template_string(open('templates/domain.rev.j2').read(), data=data)
        write_file_as_root(f"/var/named/{data['base_domain']}.rev", rev_content)

        # named 서비스 시작
        return jsonify(run_command("sudo systemctl enable --now named"))

    # --- Chrony 설정 ---
    elif config_type == 'chrony':
        backup_file("/etc/chrony.conf")
        chrony_content = render_template_string(
            open('templates/chrony.conf.j2').read(),
            machine_network_cidr=data['machine_network_cidr']
        )
        write_file_as_root("/etc/chrony.conf", chrony_content)
        return jsonify(run_command("sudo systemctl enable --now chronyd"))

    # --- HAProxy 설정 ---
    elif config_type == 'haproxy':
        backup_file("/etc/haproxy/haproxy.cfg")
        haproxy_content = render_template_string(open('templates/haproxy.cfg.j2').read(), data=data)
        write_file_as_root("/etc/haproxy/haproxy.cfg", haproxy_content)
        run_command("sudo setsebool -P haproxy_connect_any=1")
        return jsonify(run_command("sudo systemctl enable --now haproxy"))

    return jsonify({"success": False, "error": "알 수 없는 설정 타입입니다."})

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5024)
