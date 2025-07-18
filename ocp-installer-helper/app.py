import os
import json
import subprocess
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_from_directory, make_response, render_template_string

# --- 기본 설정 ---
app = Flask(__name__)
DATA_DIR = 'data'
KEY_DIR = 'generated_keys'
# 보안을 위해 업로드 파일 확장자 제한
ALLOWED_EXTENSIONS = {'xlsx'}

# --- 애플리케이션 시작 시 디렉토리 생성 ---
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(KEY_DIR, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 기본 페이지 및 정적 파일 라우팅 ---
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
        # 실제 미러링을 위해서는 oc adm release mirror 명령 실행 및
        # imageContentSources 등을 생성하는 로직이 추가되어야 합니다.
        # 이 예제에서는 입력받은 정보를 저장하는 것에 집중합니다.
        "imageContentSources": f"""- mirrors:
  - {data['reg_domain']}:{data['reg_port']}
  source: registry.redhat.io/openshift-release-dev/ocp-v4.0-art-dev""" # 예시 소스
    }

    with open(os.path.join(DATA_DIR, 'mirror_reg.json'), 'w') as f:
        json.dump(mirror_info, f, indent=4)

    # TODO: 실제 미러 레지스트리를 구성하는 스크립트 실행
    # 예: os.system(f"bash create_mirror.sh {data['ocp_version']} ...")

    return "✅ 미러 레지스트리 정보가 'data/mirror_reg.json'에 저장되었습니다."


# --- 섹션 1: 노드 정보 업로드 ---
@app.route('/upload-nodes', methods=['POST'])
def upload_nodes():
    """엑셀 파일을 업로드 받아 노드 정보를 JSON으로 저장합니다."""
    if 'node_info_file' not in request.files:
        return "파일이 없습니다.", 400
    file = request.files['node_info_file']
    if file.filename == '' or not allowed_file(file.filename):
        return "파일이 선택되지 않았거나 허용되지 않는 형식입니다. (.xlsx)", 400

    try:
        df = pd.read_excel(file)
        # 'hostname' 컬럼이 없는 경우 에러 처리
        if 'hostname' not in df.columns:
            return "'hostname' 컬럼이 파일에 존재하지 않습니다.", 400
        
        # 'hostname'을 key로 사용하여 dictionary(JSON) 형태로 변환
        node_data = df.set_index('hostname').to_dict('index')

        with open(os.path.join(DATA_DIR, 'cluster_info.json'), 'w') as f:
            json.dump(node_data, f, indent=4)
        return "✅ 노드 정보가 'data/cluster_info.json'에 성공적으로 저장되었습니다."
    except Exception as e:
        return f"파일 처리 중 오류 발생: {e}", 500


# --- 섹션 2 & 4: YAML 생성을 위한 API 엔드포인트 ---

@app.route('/api/load-cluster-info')
def load_cluster_info_api():
    """저장된 클러스터(노드) 정보를 불러옵니다."""
    try:
        with open(os.path.join(DATA_DIR, 'cluster_info.json')) as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({"error": "클러스터 정보 파일(cluster_info.json)이 없습니다."}), 404

@app.route('/api/load-mirror-secret')
def load_mirror_secret_api():
    """저장된 미러 레지스트리 정보를 불러옵니다."""
    try:
        with open(os.path.join(DATA_DIR, 'mirror_reg.json')) as f:
            # 실제 pull secret 형식으로 가공하여 반환해야 함
            # 여기서는 예시로 전체 정보를 반환
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({"error": "미러 레지스트리 정보 파일(mirror_reg.json)이 없습니다."}), 404

@app.route('/generate-ssh-key', methods=['POST'])
def generate_ssh_key():
    """SSH 키를 생성합니다."""
    key_name = request.json.get('key_name')
    if not key_name:
        return "키 이름이 필요합니다.", 400

    private_key_path = os.path.join(KEY_DIR, key_name)
    public_key_path = f"{private_key_path}.pub"

    if os.path.exists(private_key_path):
        return "이미 해당 이름의 키가 존재합니다.", 409

    command = f"ssh-keygen -t rsa -b 4096 -f {private_key_path} -N ''"
    subprocess.run(command, shell=True, check=True)
    return f"✅ SSH 키가 '{public_key_path}'에 생성되었습니다."

@app.route('/api/get-ssh-key/<key_name>')
def get_ssh_key(key_name):
    """생성된 Public SSH 키의 내용을 반환합니다."""
    public_key_path = os.path.join(KEY_DIR, f"{key_name}.pub")
    try:
        with open(public_key_path, 'r') as f:
            return jsonify({"key": f.read().strip()})
    except FileNotFoundError:
        return jsonify({"error": "해당 이름의 Public Key를 찾을 수 없습니다."}), 404

# --- 섹션 2: install-config.yaml 생성 ---
@app.route('/generate-install-config', methods=['POST'])
def generate_install_config():
    """폼 데이터로 install-config.yaml 파일을 생성하여 다운로드합니다."""
    config_data = request.form.to_dict()
    config_data['proxy_enabled'] = 'proxy_enabled' in config_data

    # 템플릿 파일 로드
    with open('templates/install-config.yaml.j2') as f:
        template_str = f.read()

    # Mirror Registry Secret을 사용하는 경우, imageContentSources를 추가
    if config_data.get('secret_type') == 'mirror_secret':
        try:
            with open(os.path.join(DATA_DIR, 'mirror_reg.json')) as f:
                mirror_data = json.load(f)
            config_data['imageContentSources'] = mirror_data.get('imageContentSources', '')
        except FileNotFoundError:
            config_data['imageContentSources'] = '' # 파일 없으면 공백

    rendered_yaml = render_template_string(template_str, **config_data)

    response = make_response(rendered_yaml)
    response.headers["Content-Disposition"] = "attachment; filename=install-config.yaml"
    response.mimetype = 'text/yaml'
    return response

# --- 섹션 4: agent-config.yaml 생성 ---
@app.route('/generate-agent-config', methods=['POST'])
def generate_agent_config():
    """폼 데이터로 agent-config.yaml 파일을 생성하여 다운로드합니다."""
    form_data = request.form
    
    # JavaScript에서 전송한 JSON 문자열을 파싱
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
    
    response = make_response(rendered_yaml)
    response.headers["Content-Disposition"] = "attachment; filename=agent-config.yaml"
    response.mimetype = 'text/yaml'
    return response

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
