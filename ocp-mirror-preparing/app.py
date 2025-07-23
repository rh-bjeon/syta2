import os
import json
import subprocess
import re
from flask import Flask, render_template, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup

# --- 기본 설정 ---
app = Flask(__name__)
BASE_DIR = "/ocp_install" 
APP_DEPLOY_DIR = "/var/www/html/ocp-mirror-preparing" # 실제 배포 경로
AUTH_DIR = os.path.join(APP_DEPLOY_DIR, ".auth")
AUTH_FILE_PATH = os.path.join(AUTH_DIR, "auth.json") # apache용 인증 파일 경로
INSTALL_AGENT_DIR = os.path.join(BASE_DIR, "install-agent")
OC_MIRROR_BASE_DIR = os.path.join(BASE_DIR, "oc-mirror")
VERSION_FILE_PATH = os.path.join(BASE_DIR, "versions.txt")
OPERATOR_OUTPUT_DIR = os.path.join(BASE_DIR, "operator_lists")
MIRROR_CONFIG_DIR = os.path.join(OC_MIRROR_BASE_DIR, "mirror-config")
MIRROR_IMAGES_DIR = os.path.join(OC_MIRROR_BASE_DIR, "mirror-images")

# --- Helper 함수 ---
def run_command(command, extra_env=None):
    """지정된 셸 명령어를 실행하고 결과를 반환합니다."""
    final_command = command
    if extra_env:
        exports = " && ".join([f"export {key}='{value}'" for key, value in extra_env.items()])
        final_command = f"{exports} && {command}"

    try:
        result = subprocess.run(
            final_command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            executable='/bin/bash'
        )
        return {"success": True, "output": result.stdout, "error": result.stderr}
    except subprocess.CalledProcessError as e:
        return {"success": False, "output": e.stdout, "error": e.stderr}

# 애플리케이션 시작 시 디렉터리 권한을 보장하는 함수
def setup_directories_and_permissions():
    """필요한 모든 디렉터리를 생성하고 apache 사용자에게 소유권을 부여합니다."""
    print("INFO: Setting up required directories and permissions...")
    try:
        dirs_to_create = [
            BASE_DIR, INSTALL_AGENT_DIR, OC_MIRROR_BASE_DIR,
            os.path.join(OC_MIRROR_BASE_DIR, "helm"),
            os.path.join(OC_MIRROR_BASE_DIR, "tekton"),
            os.path.join(OC_MIRROR_BASE_DIR, "butane"),
            os.path.join(OC_MIRROR_BASE_DIR, "mirror-registry"),
            OPERATOR_OUTPUT_DIR, MIRROR_CONFIG_DIR, MIRROR_IMAGES_DIR,
        ]
        for d in dirs_to_create:
            run_command(f"sudo mkdir -p {d}")
        
        run_command(f"sudo chown -R apache:apache {BASE_DIR}")
        print("INFO: Directory setup completed successfully.")
    except Exception as e:
        print(f"ERROR during directory setup: {e}")

setup_directories_and_permissions()

# --- 기본 페이지 및 API 라우팅 ---
@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

# --- Section 1: OCP Installer 준비 ---
@app.route('/api/get-ocp-versions')
def get_ocp_versions():
    try:
        url = "https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/"
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        versions = []
        for a in soup.find_all('a', href=True):
            match = re.match(r'^4\.\d+\.\d+/$', a['href'])
            if match:
                versions.append(match.group(0).strip('/'))
        versions.sort(key=lambda v: list(map(int, v.split('.'))), reverse=True)
        with open(VERSION_FILE_PATH, 'w') as f:
            for version in versions:
                f.write(f"{version}\n")
        return jsonify({"success": True, "versions": versions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/execute-command', methods=['POST'])
def execute_command_route():
    data = request.json
    command_key = data.get('command_key')
    version = data.get('version')
    commands = {
        'download_installer_client': f"wget https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/{version}/openshift-install-linux.tar.gz -P {INSTALL_AGENT_DIR} && wget https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/{version}/openshift-client-linux.tar.gz -P {INSTALL_AGENT_DIR}",
        'unpack_installer_client': f"sudo tar --overwrite -xzf {INSTALL_AGENT_DIR}/openshift-install-linux.tar.gz -C /usr/local/bin/ && sudo tar --overwrite -xzf {INSTALL_AGENT_DIR}/openshift-client-linux.tar.gz -C /usr/local/bin/",
        'oc_version': "oc version",
        'openshift_install_version': "openshift-install version",
        'download_oc_mirror': f"wget https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/{version}/oc-mirror.tar.gz -P {OC_MIRROR_BASE_DIR}",
        'unpack_oc_mirror': f"sudo tar --overwrite -xzf {OC_MIRROR_BASE_DIR}/oc-mirror.tar.gz -C /usr/local/bin/ && sudo chmod 755 /usr/local/bin/oc-mirror",
        'download_helm': f"wget -P {OC_MIRROR_BASE_DIR}/helm/ https://mirror.openshift.com/pub/openshift-v4/clients/helm/latest/helm-linux-amd64.tar.gz",
        'unpack_helm': f"sudo tar --overwrite -xzf {OC_MIRROR_BASE_DIR}/helm/helm-linux-amd64.tar.gz -C /usr/local/bin/",
        'download_tekton': f"wget -P {OC_MIRROR_BASE_DIR}/tekton https://mirror.openshift.com/pub/openshift-v4/clients/pipeline/latest/tkn-linux-amd64.tar.gz",
        'unpack_tekton': f"sudo tar --overwrite -xzf {OC_MIRROR_BASE_DIR}/tekton/tkn-linux-amd64.tar.gz -C /usr/local/bin/",
        'download_butane': f"wget -P {OC_MIRROR_BASE_DIR}/butane https://mirror.openshift.com/pub/openshift-v4/clients/butane/latest/butane",
        'install_butane': f"sudo chmod 755 {OC_MIRROR_BASE_DIR}/butane/butane && sudo mv {OC_MIRROR_BASE_DIR}/butane/butane /usr/local/bin/",
        'download_mirror_registry': f"wget -P {OC_MIRROR_BASE_DIR}/mirror-registry/ https://mirror.openshift.com/pub/cgw/mirror-registry/latest/mirror-registry-amd64.tar.gz",
        'unpack_mirror_registry': f"tar --overwrite -xzf {OC_MIRROR_BASE_DIR}/mirror-registry/mirror-registry-amd64.tar.gz -C {OC_MIRROR_BASE_DIR}/mirror-registry/ && sudo mv {OC_MIRROR_BASE_DIR}/mirror-registry/mirror-registry /usr/local/bin/",
    }
    command_to_run = commands.get(command_key)
    if not command_to_run:
        return jsonify({"success": False, "error": "Unknown command key."})
    result = run_command(command_to_run)
    return jsonify(result)

# --- Section 3: Mirror Image 준비 ---
@app.route('/api/apply-pull-secret', methods=['POST'])
def apply_pull_secret():
    data = request.json
    pull_secret = data.get('pull_secret')
    if not pull_secret:
        return jsonify({"success": False, "error": "Pull Secret 내용이 없습니다."})
    try:
        json.loads(pull_secret)
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "유효하지 않은 JSON 형식입니다."})
    mkdir_cmd = f"sudo mkdir -p {AUTH_DIR}"
    chown_dir_cmd = f"sudo chown apache:apache {AUTH_DIR}"
    dir_result = run_command(f"{mkdir_cmd} && {chown_dir_cmd}")
    if not dir_result['success']:
        return jsonify({"success": False, "error": f"인증 디렉터리 생성 실패: {dir_result['error']}"})
    try:
        with open(AUTH_FILE_PATH, 'w') as f:
            f.write(pull_secret)
    except IOError as e:
         return jsonify({"success": False, "error": f"인증 파일 쓰기 실패: {str(e)}"})
    chown_file_cmd = f"sudo chown apache:apache {AUTH_FILE_PATH}"
    file_result = run_command(chown_file_cmd)
    if not file_result['success']:
        return jsonify({"success": False, "error": f"인증 파일 권한 설정 실패: {file_result['error']}"})
    return jsonify({"success": True, "message": f"✅ Pull Secret이 {AUTH_FILE_PATH}에 성공적으로 적용되었습니다."})

@app.route('/api/list-operators', methods=['POST'])
def list_operators():
    data = request.json
    catalog = data.get('catalog')
    version = data.get('version')
    if not catalog or not version:
        return jsonify({"success": False, "error": "Catalog and version are required."})
    catalog_url = f"registry.redhat.io/redhat/{catalog}:v{version}"
    output_filename = os.path.join(OPERATOR_OUTPUT_DIR, f"{catalog.replace('-index','')}.out")
    
    command = f"oc-mirror list operators --catalog={catalog_url} > {output_filename}"
    extra_env = {
        "REGISTRY_AUTH_FILE": AUTH_FILE_PATH,
        "XDG_RUNTIME_DIR": AUTH_DIR
    }
    result = run_command(command, extra_env=extra_env)
    
    if not result['success']:
        return jsonify(result)
        
    operator_names = []
    json_output_filename = os.path.join(OPERATOR_OUTPUT_DIR, f"{catalog.replace('-index','')}.json")
    try:
        with open(output_filename, 'r') as f:
            lines = f.readlines()
            if len(lines) <= 1:
                return jsonify({"success": False, "error": f"명령은 성공했으나 Operator 목록이 비어있습니다. Stderr: {result['error']}"})

            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if parts:
                    operator_names.append(parts[0])
        
        with open(json_output_filename, 'w') as json_f:
            json.dump(operator_names, json_f, indent=4)

        return jsonify({"success": True, "operators": operator_names})
    except Exception as e:
        return jsonify({"success": False, "error": f"Operator 목록 파일 파싱 실패: {str(e)}"})

@app.route('/api/generate-imageset', methods=['POST'])
def generate_imageset():
    config_data = request.json
    try:
        with open('templates/imageset-config.yaml.j2') as f:
            template_str = f.read()
        rendered_yaml = render_template_string(template_str, **config_data)
        target_path = os.path.join(MIRROR_CONFIG_DIR, 'imagesetconfig.yaml')
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(rendered_yaml)
        return jsonify({"success": True, "message": f"✅ imagesetconfig.yaml 파일이 {os.path.abspath(MIRROR_CONFIG_DIR)}에 생성되었습니다."})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to generate file: {str(e)}"})

@app.route('/api/run-mirror', methods=['POST'])
def run_mirror():
    config_file = os.path.join(MIRROR_CONFIG_DIR, 'imagesetconfig.yaml')
    # [수정] --v2 명령어에 --authfile 옵션을 사용하도록 수정
    command = f"oc mirror --authfile {AUTH_FILE_PATH} -c {config_file} file://{MIRROR_IMAGES_DIR} --v2"
    
    # XDG_RUNTIME_DIR은 여전히 필요할 수 있음
    extra_env = {
        "XDG_RUNTIME_DIR": AUTH_DIR
    }
    
    final_command = command
    exports = " && ".join([f"export {key}='{value}'" for key, value in extra_env.items()])
    final_command = f"{exports} && {final_command}"

    try:
        subprocess.Popen(final_command, shell=True, executable='/bin/bash')
        return jsonify({"success": True, "message": f"Mirroring process started in the background. Check server logs for progress. Images will be saved to {MIRROR_IMAGES_DIR}"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to start mirroring: {str(e)}"})

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5022)
