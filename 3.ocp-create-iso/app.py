import os
import json
import subprocess
import shutil
from flask import Flask, render_template, request, jsonify, render_template_string
from io import StringIO
import csv
import glob

# --- 기본 설정 ---
app = Flask(__name__)
# 공유 데이터 경로 (이전 앱에서 사용하던 경로)
SHARED_DATA_PATH = "/var/www/html/ocp-installer-helper/data/cluster_info.json"
# 이전 앱에서 생성된 설정/이미지 경로
PREV_APP_BASE_DIR = "/disk1/ocp_install"
MIRROR_CONFIG_FILE = os.path.join(PREV_APP_BASE_DIR, "oc-mirror/mirror-config/imagesetconfig.yaml")
MIRROR_IMAGES_DIR = os.path.join(PREV_APP_BASE_DIR, "oc-mirror/mirror-images")
# 이 앱에서 사용할 경로
ISO_CREATE_DIR = os.path.join(PREV_APP_BASE_DIR, "create-iso")
PREV_APP_CONFIG_DIR = "/var/www/html/ocp-installer-helper/create_config"
QUAY_ROOT = "/opt/openshift/init-quay"

# --- Helper 함수 ---
def run_command(command, capture_output=True):
    """지정된 셸 명령어를 실행하고 결과를 반환합니다."""
    try:
        result = subprocess.run(
            command, shell=True, check=True,
            capture_output=capture_output, text=True, executable='/bin/bash'
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
    """파일을 백업하고 메시지를 반환합니다."""
    if os.path.exists(filepath):
        backup_path = f"{filepath}.bak_{os.getpid()}"
        run_command(f"sudo cp {filepath} {backup_path}")
        return f"기존 파일 백업: {backup_path}"
    return "백업할 기존 파일 없음"

def write_file_as_root(filepath, content):
    """파일을 root 권한으로 씁니다."""
    # 임시 파일에 내용을 쓰고, sudo mv로 이동하여 권한 문제를 회피
    temp_file = f"/tmp/temp_file_{os.getpid()}"
    with open(temp_file, 'w') as f:
        f.write(content)
    run_command(f"sudo mv {temp_file} {filepath}")
    return run_command(f"sudo chown root:root {filepath}") # 소유권 확인

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

# --- Section 2, 3, 5, 6: 버튼 액션 처리 ---
@app.route('/api/execute-action', methods=['POST'])
def execute_action():
    action_type = request.json.get('type')
    data = load_cluster_data()
    if not data and action_type not in ['ca_trust']: # CA 신뢰 설정은 데이터 없이도 가능
        return jsonify({"success": False, "error": "클러스터 정보(cluster_info.json)가 없습니다. 먼저 CSV를 업로드하세요."})

    # --- Section 2 Actions ---
    if action_type == 'hostname':
        hostname = f"{data['hostname_bastion']}.{data['metadata_name']}.{data['base_domain']}"
        return jsonify(run_command(f"sudo hostnamectl set-hostname {hostname}"))
    
    if action_type == 'ip':
        ip = data['nodeip_bastion']
        prefix = data['prefix_master0']
        gateway = data.get('gw_bastion', data.get('gw_master0', ''))
        dns = data['nodeip_bastion']
        search_domain = f"{data['metadata_name']}.{data['base_domain']}"
        interface_name = data.get('interface_bastion', 'eth0')
        command = (
            f"sudo nmcli connection modify {interface_name} "
            f"ipv4.method manual ipv4.addresses {ip}/{prefix} "
            f"ipv4.gateway {gateway} ipv4.dns {dns} ipv4.dns-search {search_domain} && "
            f"sudo nmcli connection up {interface_name}"
        )
        return jsonify(run_command(command))

    if action_type == 'dns':
        backup_file("/etc/named.conf")
        run_command("sudo sed -i 's/dnssec-validation yes;/dnssec-validation no;/' /etc/named.conf")
        run_command("sudo sed -i '/listen-on-v6/a \\        forwarders { 8.8.8.8; };\\n        forward first;\\n' /etc/named.conf")
        
        backup_file("/etc/named.rfc1912.zones")
        rev_ip = '.'.join(data['machine_network_cidr'].split('/')[0].split('.')[:3][::-1])
        zone_config = render_template_string(open('templates/named.rfc1912.zones.j2').read(), base_domain=data['base_domain'], rev_ip=rev_ip)
        run_command(f"echo '{zone_config}' | sudo tee -a /etc/named.rfc1912.zones")

        zone_content = render_template_string(open('templates/domain.zone.j2').read(), data=data)
        write_file_as_root(f"/var/named/{data['base_domain']}.zone", zone_content)

        rev_content = render_template_string(open('templates/domain.rev.j2').read(), data=data)
        write_file_as_root(f"/var/named/{data['base_domain']}.rev", rev_content)

        return jsonify(run_command("sudo systemctl enable --now named"))

    if action_type == 'chrony':
        backup_file("/etc/chrony.conf")
        chrony_content = render_template_string(open('templates/chrony.conf.j2').read(), machine_network_cidr=data['machine_network_cidr'])
        write_file_as_root("/etc/chrony.conf", chrony_content)
        return jsonify(run_command("sudo systemctl enable --now chronyd"))

    if action_type == 'haproxy':
        backup_file("/etc/haproxy/haproxy.cfg")
        haproxy_content = render_template_string(open('templates/haproxy.cfg.j2').read(), data=data)
        write_file_as_root("/etc/haproxy/haproxy.cfg", haproxy_content)
        return jsonify(run_command("sudo systemctl enable --now haproxy"))

    # --- Section 3 Actions ---
    if action_type == 'mirror_install':
        cmd = (f"sudo /usr/local/bin/mirror-registry install --initUser {data['local_registry_user']} "
               f"--initPassword {data['local_registry_password']} --quayHostname {data['local_registry']} "
               f"--quayRoot {QUAY_ROOT} --pgStorage {QUAY_ROOT}/pg-storage --quayStorage {QUAY_ROOT}/quay-storage -v")
        return jsonify(run_command(cmd))

    if action_type == 'ca_trust':
        cmd = (f"sudo cp -f {QUAY_ROOT}/quay-rootCA/rootCA.pem /etc/pki/ca-trust/source/anchors/ && "
               f"sudo cp -f {QUAY_ROOT}/quay-config/ssl.cert /etc/pki/ca-trust/source/anchors/ && "
               f"sudo update-ca-trust")
        return jsonify(run_command(cmd))
    
    if action_type == 'get_ca_cert':
        try:
            with open(f"{QUAY_ROOT}/quay-rootCA/rootCA.pem", 'r') as f:
                cert_content = f.read()
            return jsonify({"success": True, "output": cert_content})
        except FileNotFoundError:
            return jsonify({"success": False, "error": "rootCA.pem 파일을 찾을 수 없습니다. 'Mirror registry 구성'을 먼저 실행하세요."})

    if action_type == 'mirror_start':
        # mirror-registry는 podman quadlet으로 관리될 수 있음
        return jsonify(run_command("sudo systemctl enable --now quay-pod.service"))

    if action_type == 'mirror_push':
        cmd = (f"sudo oc mirror -c {MIRROR_CONFIG_FILE} "
               f"docker://{data['local_registry']} --v2 --dest-skip-tls")
        # 이 작업은 매우 오래 걸리므로 백그라운드 실행
        subprocess.Popen(cmd, shell=True, executable='/bin/bash')
        return jsonify({"success": True, "message": "이미지 푸시 작업이 백그라운드에서 시작되었습니다. 서버 로그를 확인하세요."})

    # --- Section 5 Actions ---
    if action_type == 'create_iso':
        run_command(f"sudo mkdir -p {ISO_CREATE_DIR}")
        run_command(f"sudo cp {PREV_APP_CONFIG_DIR}/install-config.yaml {ISO_CREATE_DIR}/")
        run_command(f"sudo cp {PREV_APP_CONFIG_DIR}/agent-config.yaml {ISO_CREATE_DIR}/")
        run_command(f"sudo chown -R apache:apache {ISO_CREATE_DIR}")
        
        cmd = f"sudo openshift-install agent create image --dir={ISO_CREATE_DIR}"
        return jsonify(run_command(cmd))

    # --- Section 6 Actions ---
    if action_type == 'oc_login':
        kubeconfig_path = f"{ISO_CREATE_DIR}/auth/kubeconfig"
        return jsonify({"success": True, "message": "터미널에서 아래 명령어를 복사하여 실행하세요:", "output": f"export KUBECONFIG={kubeconfig_path}"})

    if action_type == 'oc_get_node':
        kubeconfig_path = f"{ISO_CREATE_DIR}/auth/kubeconfig"
        return jsonify(run_command(f"export KUBECONFIG={kubeconfig_path} && oc get node"))

    if action_type == 'apply_policies':
        cmd1 = "export KUBECONFIG={0}/auth/kubeconfig && oc patch configs.imageregistry.operator.openshift.io cluster --type merge --patch '{{\"spec\":{{\"managementState\": \"Managed\"}}}}'".format(ISO_CREATE_DIR)
        cmd2 = "export KUBECONFIG={0}/auth/kubeconfig && oc patch OperatorHub cluster --type json -p '[{{\"op\": \"add\", \"path\": \"/spec/disableAllDefaultSources\", \"value\": true}}]'".format(ISO_CREATE_DIR)
        
        # results-XXXXX 디렉터리 찾기
        results_dirs = glob.glob(f"{MIRROR_IMAGES_DIR}/working-dir/results-*")
        if not results_dirs:
            return jsonify({"success": False, "error": "results-XXXXX 디렉터리를 찾을 수 없습니다."})
        latest_results_dir = max(results_dirs, key=os.path.getmtime)
        
        cmd3 = f"export KUBECONFIG={ISO_CREATE_DIR}/auth/kubeconfig && oc apply -f {latest_results_dir}/"
        
        full_command = f"{cmd1} && {cmd2} && {cmd3}"
        return jsonify(run_command(full_command))

    return jsonify({"success": False, "error": "알 수 없는 액션 타입입니다."})

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5024)
