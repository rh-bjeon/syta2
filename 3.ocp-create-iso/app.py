import os
import json
import subprocess
import shutil
from flask import Flask, render_template, request, jsonify, render_template_string
from io import StringIO
import csv
import glob
import shlex

# --- 기본 설정 ---
app = Flask(__name__)
BASE_DIR = "/ocp_install" 
SHARED_DATA_PATH = "/ocp_install/data/cluster_info.json"
PREV_APP_CONFIG_DIR = "/ocp_install/create_config"

INSTALL_AGENT_DIR = os.path.join(BASE_DIR, "install-agent")
OC_MIRROR_BASE_DIR = os.path.join(BASE_DIR, "oc-mirror")
MIRROR_CONFIG_FILE = os.path.join(OC_MIRROR_BASE_DIR, "mirror-config/imagesetconfig.yaml")
MIRROR_IMAGES_DIR = os.path.join(OC_MIRROR_BASE_DIR, "mirror-images")
ISO_CREATE_DIR = os.path.join(BASE_DIR, "create-iso")
QUAY_ROOT = "/opt/openshift/init-quay"
APACHE_HOME_DIR = "/usr/share/httpd"

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
        run_command(f"sudo cp -p {filepath} {backup_path}")
        return f"기존 파일 백업: {backup_path}"
    return "백업할 기존 파일 없음"

def write_file_as_root(filepath, content):
    """파일의 '내용'을 root 권한으로 직접 써넣어 올바른 SELinux 컨텍스트를 부여합니다."""
    escaped_content = shlex.quote(content)
    command = f"echo {escaped_content} | sudo tee {filepath} > /dev/null"
    return run_command(command)

def setup_directories_and_permissions():
    """필요한 모든 디렉터리를 생성하고 apache 사용자에게 소유권을 부여합니다."""
    print("INFO: Setting up required directories and permissions...")
    try:
        dirs_to_create = [
            os.path.dirname(SHARED_DATA_PATH),
            ISO_CREATE_DIR,
        ]
        for d in dirs_to_create:
            run_command(f"sudo mkdir -p {d}")
        
        run_command(f"sudo chown -R apache:apache {BASE_DIR}")
        run_command(f"sudo chown -R apache:apache {APACHE_HOME_DIR}")
        print("INFO: Directory setup completed successfully.")
    except Exception as e:
        print(f"ERROR during directory setup: {e}")

setup_directories_and_permissions()

# --- 기본 페이지 및 API 라우팅 ---
@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

# --- Section 1: CSV 업로드 ---
@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    """CSV 파일을 업로드하고 sudo를 사용하여 공유 경로에 안전하게 저장합니다."""
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
        
        temp_file_path = f"/tmp/cluster_info_{os.getpid()}.json"
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump(cluster_data, f, indent=4, ensure_ascii=False)

        dest_dir = os.path.dirname(SHARED_DATA_PATH)
        run_command(f"sudo mkdir -p {dest_dir}")
        run_command(f"sudo mv {temp_file_path} {SHARED_DATA_PATH}")
        run_command(f"sudo chmod 644 {SHARED_DATA_PATH}")
        run_command(f"sudo chown apache:apache {SHARED_DATA_PATH}")
        run_command(f"sudo restorecon -Rv {dest_dir}")

        return jsonify({"success": True, "message": f"✅ 클러스터 정보가 {SHARED_DATA_PATH}에 저장되었습니다."})
    except Exception as e:
        return jsonify({"success": False, "error": f"파일 처리 중 오류 발생: {e}"})

# --- 버튼 액션 처리 ---
@app.route('/api/execute-action', methods=['POST'])
def execute_action():
    action_type = request.json.get('type')
    data = load_cluster_data()
    if not data and action_type not in ['ca_trust', 'unpack_tools']:
        return jsonify({"success": False, "error": "클러스터 정보(cluster_info.json)가 없습니다. 먼저 CSV를 업로드하세요."})

    # 필수 명령어 준비 액션
    if action_type == 'unpack_tools':
        cmd1 = f"sudo tar --overwrite -xzf {INSTALL_AGENT_DIR}/openshift-install-linux.tar.gz -C /usr/local/bin/"
        cmd2 = f"sudo tar --overwrite -xzf {INSTALL_AGENT_DIR}/openshift-client-linux.tar.gz -C /usr/local/bin/"
        cmd3 = f"sudo cp {OC_MIRROR_BASE_DIR}/mirror-registry/mirror-registry /usr/local/bin/"
        cmd4 = f"sudo tar --overwrite -xzf {OC_MIRROR_BASE_DIR}/oc-mirror.tar.gz -C /usr/local/bin/ && sudo chmod 755 /usr/local/bin/oc-mirror"
        cmd5 = f"sudo tar --overwrite -xzf {OC_MIRROR_BASE_DIR}/helm/helm-linux-amd64.tar.gz -C /usr/local/bin/"
        cmd6 = f"sudo tar --overwrite -xzf {OC_MIRROR_BASE_DIR}/tekton/tkn-linux-amd64.tar.gz -C /usr/local/bin/"
        full_command = f"{cmd1} && {cmd2} && {cmd3} && {cmd4} && {cmd5} && {cmd6}"
        return jsonify(run_command(full_command))

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
        command = (f"sudo nmcli connection modify {interface_name} ipv4.method manual ipv4.addresses {ip}/{prefix} ipv4.gateway {gateway} ipv4.dns {dns} ipv4.dns-search {search_domain} && sudo nmcli connection up {interface_name}")
        return jsonify(run_command(command))

    if action_type == 'dns':
        backup_file("/etc/named.conf")
        named_conf_content = render_template_string(open('templates/named.conf.j2').read())
        write_file_as_root("/etc/named.conf", named_conf_content)
        backup_file("/etc/named.rfc1912.zones")
        rev_ip = '.'.join(data['machine_network_cidr'].split('/')[0].split('.')[:3][::-1])
        rfc1912_content = render_template_string(open('templates/named.rfc1912.zones.j2').read(), base_domain=data['base_domain'], rev_ip=rev_ip)
        write_file_as_root("/etc/named.rfc1912.zones", rfc1912_content)
        zone_file_path = f"/var/named/{data['base_domain']}.zone"
        rev_file_path = f"/var/named/{data['base_domain']}.rev"
        zone_content = render_template_string(open('templates/domain.zone.j2').read(), data=data)
        write_file_as_root(zone_file_path, zone_content)
        rev_content = render_template_string(open('templates/domain.rev.j2').read(), data=data)
        write_file_as_root(rev_file_path, rev_content)
        run_command(f"sudo chown root:named {zone_file_path} {rev_file_path}")
        run_command(f"sudo restorecon /etc/named.conf /etc/named.rfc1912.zones")
        run_command(f"sudo restorecon -v /var/named/{data['base_domain']}.*")
        return jsonify(run_command("sudo systemctl enable --now named"))

    if action_type == 'chrony':
        backup_file("/etc/chrony.conf")
        chrony_content = render_template_string(open('templates/chrony.conf.j2').read(), machine_network_cidr=data['machine_network_cidr'])
        write_file_as_root("/etc/chrony.conf", chrony_content)
        run_command("sudo restorecon /etc/chrony.conf")
        return jsonify(run_command("sudo systemctl enable --now chronyd"))

    if action_type == 'haproxy':
        backup_file("/etc/haproxy/haproxy.cfg")
        haproxy_content = render_template_string(open('templates/haproxy.cfg.j2').read(), data=data)
        write_file_as_root("/etc/haproxy/haproxy.cfg", haproxy_content)
        run_command("sudo restorecon /etc/haproxy/haproxy.cfg")
        return jsonify(run_command("sudo systemctl enable --now haproxy"))

    # --- Section 3 Actions ---
    if action_type == 'mirror_install':
        cmd = (f"sudo /usr/local/bin/mirror-registry install --initUser {data['local_registry_user']} --initPassword {data['local_registry_password']} --quayHostname {data['local_registry']} --quayRoot {QUAY_ROOT} --pgStorage {QUAY_ROOT}/pg-storage --quayStorage {QUAY_ROOT}/quay-storage -v")
        return jsonify(run_command(cmd))

    if action_type == 'ca_trust':
        cmd = (f"sudo cp -f {QUAY_ROOT}/quay-rootCA/rootCA.pem /etc/pki/ca-trust/source/anchors/ && sudo cp -f {QUAY_ROOT}/quay-config/ssl.cert /etc/pki/ca-trust/source/anchors/ && sudo update-ca-trust")
        return jsonify(run_command(cmd))
    
    if action_type == 'get_ca_cert':
        ca_path = f"{QUAY_ROOT}/quay-rootCA/rootCA.pem"
        if not os.path.exists(ca_path):
            return jsonify({"success": False, "error": "rootCA.pem 파일을 찾을 수 없습니다."})
        result = run_command(f"sudo cat {ca_path}")
        return jsonify(result)

    if action_type == 'mirror_start':
        return jsonify(run_command("sudo systemctl enable --now quay-pod.service"))

    if action_type == 'registry_auth':
        # [수정] 명령어 문자열을 생성하여 반환
        user = data['local_registry_user']
        password = data['local_registry_password']
        registry = data['local_registry']

        auth_command = f"echo -n '{user}:{password}' | base64 -w0"
        auth_result = run_command(auth_command)
        if not auth_result['success']:
            return jsonify({"success": False, "error": f"auth 문자열 생성 실패: {auth_result['error']}"})
        auth_string = auth_result['output'].strip()

        config_json = {"auths": {registry: {"auth": auth_string}}}
        config_content = json.dumps(config_json, indent=4)
        
        command_to_run = (
            "mkdir -p ~/.docker && \\\n"
            f"echo '{config_content}' > ~/.docker/config.json"
        )
        
        return jsonify({
            "success": True,
            "is_command": True, # JS에서 이 값을 확인
            "message": "root 로 Bastion에서 해당 명령어를 복사/붙여넣기로 수행하세요.",
            "output": command_to_run
        })

    if action_type == 'mirror_push':
        # [수정] 명령어 문자열을 생성하여 반환
        command_to_run = (
            f"oc mirror -c {MIRROR_CONFIG_FILE} "
            f"--from=file://{MIRROR_IMAGES_DIR} "
            f"docker://{data['local_registry']} --v2"
        )
        return jsonify({
            "success": True,
            "is_command": True,
            "message": "root 로 Bastion에서 해당 명령어를 복사/붙여넣기로 수행하세요.",
            "output": command_to_run
        })

    # --- Section 5 & 6 Actions ---
    if action_type == 'create_iso':
        run_command(f"sudo mkdir -p {ISO_CREATE_DIR}")
        run_command(f"sudo cp {PREV_APP_CONFIG_DIR}/install-config.yaml {ISO_CREATE_DIR}/")
        run_command(f"sudo cp {PREV_APP_CONFIG_DIR}/agent-config.yaml {ISO_CREATE_DIR}/")
        run_command(f"sudo chown -R apache:apache {ISO_CREATE_DIR}")
        cmd = f"sudo openshift-install agent create image --dir={ISO_CREATE_DIR}"
        return jsonify(run_command(cmd))

    if action_type == 'oc_login':
        kubeconfig_path = f"{ISO_CREATE_DIR}/auth/kubeconfig"
        return jsonify({"success": True, "message": "터미널에서 아래 명령어를 복사하여 실행하세요:", "output": f"export KUBECONFIG={kubeconfig_path}"})

    if action_type == 'oc_get_node':
        kubeconfig_path = f"{ISO_CREATE_DIR}/auth/kubeconfig"
        return jsonify(run_command(f"export KUBECONFIG={kubeconfig_path} && oc get node"))

    if action_type == 'apply_policies':
        cmd1 = "export KUBECONFIG={0}/auth/kubeconfig && oc patch configs.imageregistry.operator.openshift.io cluster --type merge --patch '{{\"spec\":{{\"managementState\": \"Managed\"}}}}'".format(ISO_CREATE_DIR)
        cmd2 = "export KUBECONFIG={0}/auth/kubeconfig && oc patch OperatorHub cluster --type json -p '[{{\"op\": \"add\", \"path\": \"/spec/disableAllDefaultSources\", \"value\": true}}]'".format(ISO_CREATE_DIR)
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
