import os
import json
import subprocess
import csv
from io import StringIO
from flask import Flask, render_template, request, jsonify, make_response, render_template_string

# --- 기본 설정 ---
app = Flask(__name__)
DATA_DIR = 'data'
KEY_DIR = 'generated_keys'
# 생성된 설정 파일이 저장될 디렉터리
CREATE_CONFIG_DIR = 'create_config'
ALLOWED_EXTENSIONS = {'csv'}

# --- 애플리케이션 시작 시 디렉토리 생성 ---
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(KEY_DIR, exist_ok=True)
# app.py와 같은 레벨에 create_config 폴더 생성
os.makedirs(CREATE_CONFIG_DIR, exist_ok=True)


def allowed_file(filename):
    """허용된 파일 확장자인지 확인합니다."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 기본 페이지 라우팅 ---
@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')


# --- 섹션 0: 미러 레지스트리 ---
@app.route('/configure-mirror', methods=['POST'])
def configure_mirror():
    """미러 레지스트리 구성 정보를 받아 JSON 파일로 저장합니다."""
    data = request.form
    mirror_info = {
        "registry_url": f"{data['reg_domain']}:{data['reg_port']}",
        "registry_user": data['reg_user'],
        "registry_password": data['reg_password'],
        # install-config.yaml 샘플에 맞춘 구조
        "imageContentSources": [
            {
                "source": "quay.io/openshift-release-dev/ocp-v4.0-art-dev",
                "mirrors": [f"{data['reg_domain']}:{data['reg_port']}/openshift/release"]
            },
            {
                "source": "quay.io/openshift-release-dev/ocp-release",
                "mirrors": [f"{data['reg_domain']}:{data['reg_port']}/openshift/release-images"]
            }
        ]
    }
    with open(os.path.join(DATA_DIR, 'mirror_reg.json'), 'w') as f:
        json.dump(mirror_info, f, indent=4)
    return f"✅ 미러 레지스트리 정보가 {os.path.join(DATA_DIR, 'mirror_reg.json')}에 저장되었습니다."


# --- 섹션 1: 클러스터 정보 업로드 (CSV) ---
@app.route('/upload-nodes', methods=['POST'])
def upload_nodes():
    """CSV 파일을 업로드 받아 클러스터 정보를 JSON으로 저장합니다."""
    if 'node_info_file' not in request.files:
        return "파일이 없습니다.", 400
    file = request.files['node_info_file']
    if file.filename == '' or not allowed_file(file.filename):
        return "파일이 선택되지 않았거나 허용되지 않는 형식입니다. (.csv)", 400
    try:
        stream = StringIO(file.stream.read().decode("UTF-8"), newline=None)
        csv_reader = csv.reader(stream)
        keys = next(csv_reader)
        values = next(csv_reader)
        if len(keys) != len(values):
            return "CSV 파일의 첫 번째 행(키)과 두 번째 행(값)의 열 개수가 일치하지 않습니다.", 400
        cluster_data = dict(zip(keys, values))
        with open(os.path.join(DATA_DIR, 'cluster_info.json'), 'w', encoding='utf-8') as f:
            json.dump(cluster_data, f, indent=4, ensure_ascii=False)
        return "✅ 클러스터 정보가 성공적으로 저장되었습니다."
    except StopIteration:
        return "CSV 파일에 최소 2줄(키, 값)의 데이터가 필요합니다.", 400
    except Exception as e:
        return f"파일 처리 중 오류 발생: {e}", 500


# --- API 엔드포인트 ---
@app.route('/api/load-cluster-info')
def load_cluster_info_api():
    try:
        with open(os.path.join(DATA_DIR, 'cluster_info.json'), encoding='utf-8') as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({"error": "클러스터 정보 파일(cluster_info.json)이 없습니다."}), 404

@app.route('/api/load-mirror-secret')
def load_mirror_secret_api():
    try:
        with open(os.path.join(DATA_DIR, 'mirror_reg.json')) as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({"error": "미러 레지스트리 정보 파일(mirror_reg.json)이 없습니다."}), 404

@app.route('/generate-ssh-key', methods=['POST'])
def generate_ssh_key():
    key_name = request.json.get('key_name')
    if not key_name: return "키 이름이 필요합니다.", 400
    private_key_path = os.path.join(KEY_DIR, key_name)
    public_key_path = f"{private_key_path}.pub"
    if os.path.exists(private_key_path): return "이미 해당 이름의 키가 존재합니다.", 409
    subprocess.run(f"ssh-keygen -t rsa -b 4096 -f {private_key_path} -N ''", shell=True, check=True)
    return f"✅ SSH 키가 '{public_key_path}'에 생성되었습니다."

@app.route('/api/get-ssh-key/<key_name>')
def get_ssh_key(key_name):
    public_key_path = os.path.join(KEY_DIR, f"{key_name}.pub")
    try:
        with open(public_key_path, 'r') as f:
            return jsonify({"key": f.read().strip()})
    except FileNotFoundError:
        return jsonify({"error": "해당 이름의 Public Key를 찾을 수 없습니다."}), 404


# --- YAML 생성 라우팅 ---
@app.route('/generate-install-config', methods=['POST'])
def generate_install_config():
    """폼 데이터로 install-config.yaml 파일을 생성하여 로컬에 저장합니다."""
    config_data = request.form.to_dict()
    config_data['proxy_enabled'] = 'proxy_enabled' in config_data
    
    # imageContentSources는 미러 레지스트리 정보에서 가져옴
    if config_data.get('secret_type') == 'mirror_secret':
        try:
            with open(os.path.join(DATA_DIR, 'mirror_reg.json')) as f:
                mirror_data = json.load(f)
            config_data['imageContentSources'] = mirror_data.get('imageContentSources', [])
        except FileNotFoundError:
            config_data['imageContentSources'] = []
    else:
        config_data['imageContentSources'] = []

    with open('templates/install-config.yaml.j2') as f:
        template_str = f.read()
    rendered_yaml = render_template_string(template_str, **config_data)
    
    target_path = os.path.join(CREATE_CONFIG_DIR, 'install-config.yaml')
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(rendered_yaml)
    
    return f"✅ install-config.yaml 파일이 {os.path.abspath(CREATE_CONFIG_DIR)}에 생성되었습니다."

@app.route('/generate-agent-config', methods=['POST'])
def generate_agent_config():
    """폼 데이터로 agent-config.yaml 파일을 생성하여 로컬에 저장합니다."""
    form_data = request.form
    nodes_json = form_data.get('nodes_data', '[]')
    nodes = json.loads(nodes_json)
    agent_config_data = {
        'metadata_name': form_data.get('metadata_name'),
        'rendezvousIP': form_data.get('rendezvousIP'),
        'additionalNTPSources': form_data.get('additionalNTPSources'),
        'nodes': nodes
    }
    with open('templates/agent-config.yaml.j2') as f:
        template_str = f.read()
    rendered_yaml = render_template_string(template_str, **agent_config_data)
    
    target_path = os.path.join(CREATE_CONFIG_DIR, 'agent-config.yaml')
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(rendered_yaml)
        
    return f"✅ agent-config.yaml 파일이 {os.path.abspath(CREATE_CONFIG_DIR)}에 생성되었습니다."


# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5013)

