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
INSTALL_AGENT_DIR = os.path.join(BASE_DIR, "install-agent")
OC_MIRROR_BASE_DIR = os.path.join(BASE_DIR, "oc-mirror")
VERSION_FILE_PATH = os.path.join(BASE_DIR, "versions.txt")
OPERATOR_OUTPUT_DIR = os.path.join(BASE_DIR, "operator_lists")
MIRROR_CONFIG_DIR = os.path.join(OC_MIRROR_BASE_DIR, "mirror-config")
MIRROR_IMAGES_DIR = os.path.join(OC_MIRROR_BASE_DIR, "mirror-images")

# --- 애플리케이션 시작 시 디렉토리 생성 ---
# 모든 필요한 디렉터리를 미리 생성합니다.
os.makedirs(INSTALL_AGENT_DIR, exist_ok=True)
os.makedirs(os.path.join(OC_MIRROR_BASE_DIR, "helm"), exist_ok=True)
os.makedirs(os.path.join(OC_MIRROR_BASE_DIR, "tekton"), exist_ok=True)
os.makedirs(os.path.join(OC_MIRROR_BASE_DIR, "butane"), exist_ok=True)
os.makedirs(os.path.join(OC_MIRROR_BASE_DIR, "mirror-registry"), exist_ok=True)
os.makedirs(OPERATOR_OUTPUT_DIR, exist_ok=True)
os.makedirs(MIRROR_CONFIG_DIR, exist_ok=True)
os.makedirs(MIRROR_IMAGES_DIR, exist_ok=True)

# --- Helper 함수 ---
def run_command(command):
    """지정된 셸 명령어를 실행하고 결과를 반환합니다."""
    try:
        # shell=True는 보안상 주의가 필요하지만, 이 앱의 목적상 사용합니다.
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return {"success": True, "output": result.stdout, "error": result.stderr}
    except subprocess.CalledProcessError as e:
        return {"success": False, "output": e.stdout, "error": e.stderr}

# --- 기본 페이지 및 API 라우팅 ---
@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

# --- Section 1: OCP Installer 준비 ---
@app.route('/api/get-ocp-versions')
def get_ocp_versions():
    """OCP 버전을 스크래핑하여 파일로 저장하고, 목록을 반환합니다."""
    try:
        url = "https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/"
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        versions = []
        for a in soup.find_all('a', href=True):
            # 정규식을 사용하여 '4.x.x' 형식의 버전만 추출
            match = re.match(r'^4\.\d+\.\d+/$', a['href'])
            if match:
                versions.append(match.group(0).strip('/'))
        
        # 최신 버전이 위로 오도록 정렬
        versions.sort(key=lambda v: list(map(int, v.split('.'))), reverse=True)

        with open(VERSION_FILE_PATH, 'w') as f:
            for version in versions:
                f.write(f"{version}\n")
        
        return jsonify({"success": True, "versions": versions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/execute-command', methods=['POST'])
def execute_command_route():
    """클라이언트로부터 받은 명령어를 실행합니다."""
    data = request.json
    command_key = data.get('command_key')
    version = data.get('version')

    commands = {
        # Section 1-2
        'download_installer_client': f"wget https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/{version}/openshift-install-linux.tar.gz -P {INSTALL_AGENT_DIR} && "
                                     f"wget https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/{version}/openshift-client-linux.tar.gz -P {INSTALL_AGENT_DIR}",
        'unpack_installer_client': f"tar -xzf {INSTALL_AGENT_DIR}/openshift-install-linux.tar.gz -C /usr/local/bin/ && "
                                   f"tar -xzf {INSTALL_AGENT_DIR}/openshift-client-linux.tar.gz -C /usr/local/bin/",
        'oc_version': "oc version",
        'openshift_install_version': "openshift-install version",
        # Section 2
        'download_oc_mirror': f"wget https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/{version}/oc-mirror.tar.gz -P {OC_MIRROR_BASE_DIR}",
        'unpack_oc_mirror': f"tar -xzf {OC_MIRROR_BASE_DIR}/oc-mirror.tar.gz -C /usr/local/bin/ && chmod 755 /usr/local/bin/oc-mirror",
        'download_helm': f"wget -P {OC_MIRROR_BASE_DIR}/helm/ https://mirror.openshift.com/pub/openshift-v4/clients/helm/latest/helm-linux-amd64.tar.gz",
        'unpack_helm': f"tar -xzf {OC_MIRROR_BASE_DIR}/helm/helm-linux-amd64.tar.gz -C /usr/local/bin/ linux-amd64/helm --strip-components=1",
        'download_tekton': f"wget -P {OC_MIRROR_BASE_DIR}/tekton https://mirror.openshift.com/pub/openshift-v4/clients/pipeline/latest/tkn-linux-amd64.tar.gz",
        'unpack_tekton': f"tar -xzf {OC_MIRROR_BASE_DIR}/tekton/tkn-linux-amd64.tar.gz -C /usr/local/bin/",
        'download_butane': f"wget -P {OC_MIRROR_BASE_DIR}/butane https://mirror.openshift.com/pub/openshift-v4/clients/butane/latest/butane",
        'install_butane': f"chmod 755 {OC_MIRROR_BASE_DIR}/butane/butane && mv {OC_MIRROR_BASE_DIR}/butane/butane /usr/local/bin/",
        'download_mirror_registry': f"wget -P {OC_MIRROR_BASE_DIR}/mirror-registry/ https://developers.redhat.com/content-gateway/rest/mirror/pub/openshift-v4/clients/mirror-registry/latest/mirror-registry.tar.gz",
        'unpack_mirror_registry': f"tar -xzf {OC_MIRROR_BASE_DIR}/mirror-registry/mirror-registry.tar.gz -C {OC_MIRROR_BASE_DIR}/mirror-registry/",
    }

    command_to_run = commands.get(command_key)
    if not command_to_run:
        return jsonify({"success": False, "error": "Unknown command key."})

    result = run_command(command_to_run)
    return jsonify(result)

# --- Section 3: Mirror Image 준비 ---
@app.route('/api/list-operators', methods=['POST'])
def list_operators():
    """지정된 카탈로그의 Operator 목록을 가져와 파싱 후 반환합니다."""
    data = request.json
    catalog = data.get('catalog')
    version = data.get('version')
    
    if not catalog or not version:
        return jsonify({"success": False, "error": "Catalog and version are required."})

    catalog_url = f"registry.redhat.io/redhat/{catalog}:v{version}"
    output_filename = os.path.join(OPERATOR_OUTPUT_DIR, f"{catalog.replace('-index','')}.out")
    
    command = f"oc-mirror list operators --catalog={catalog_url} > {output_filename}"
    result = run_command(command)
    
    if not result['success']:
        return jsonify(result)

    operators = []
    try:
        with open(output_filename, 'r') as f:
            lines = f.readlines()
            # 헤더 라인(NAME...)을 건너뛰고 파싱 시작
            for line in lines[1:]:
                # 여러 개의 공백을 기준으로 분리
                parts = re.split(r'\s{2,}', line.strip())
                if len(parts) >= 3:
                    operators.append({
                        "name": parts[0],
                        "displayName": parts[1],
                        "defaultChannel": parts[2]
                    })
        return jsonify({"success": True, "operators": operators})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to parse operator list: {str(e)}"})

@app.route('/api/generate-imageset', methods=['POST'])
def generate_imageset():
    """폼 데이터로 imagesetconfig.yaml 파일을 생성합니다."""
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
    """oc mirror 명령을 실행합니다."""
    config_file = os.path.join(MIRROR_CONFIG_DIR, 'imagesetconfig.yaml')
    command = f"oc mirror --config={config_file} file://{MIRROR_IMAGES_DIR}"
    
    # 이 명령어는 매우 오래 걸리므로, 백그라운드 실행을 고려해야 하지만
    # 여기서는 간단히 실행하고 "시작됨" 메시지를 반환합니다.
    # 실제 출력을 보려면 별도의 로깅/스트리밍 구현이 필요합니다.
    try:
        subprocess.Popen(command, shell=True)
        return jsonify({"success": True, "message": f"Mirroring process started in the background. Check server logs for progress. Images will be saved to {MIRROR_IMAGES_DIR}"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to start mirroring: {str(e)}"})

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5014)
