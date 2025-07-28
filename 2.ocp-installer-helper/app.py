import os
import json
import subprocess
import csv
from io import StringIO
from flask import Flask, render_template, request, jsonify, make_response, render_template_string

# --- 기본 설정 ---
app = Flask(__name__)
DATA_DIR = 'data'
KEY_DIR = '/ocp_install/generated_keys'
CREATE_CONFIG_DIR = '/ocp_install/create_config'
ALLOWED_EXTENSIONS = {'csv'}

# --- 애플리케이션 시작 시 디렉토리 생성 ---
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(KEY_DIR, exist_ok=True)
os.makedirs(CREATE_CONFIG_DIR, exist_ok=True)


def allowed_file(filename):
    """허용된 파일 확장자인지 확인합니다."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# [수정] 누락된 run_command 함수 추가
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



# --- 기본 페이지 라우팅 ---
@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')


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

# [수정] Mirror CA 인증서를 시스템 신뢰 저장소에서 읽어오도록 경로 변경
#@app.route('/api/get-mirror-ca')
#def get_mirror_ca():
#    """/etc/pki/ca-trust/source/anchors/rootCA.pem 파일 내용을 읽어 반환합니다."""
#    ca_path = "/etc/pki/ca-trust/source/anchors/rootCA.pem"
#    if not os.path.exists(ca_path):
#        return jsonify({"success": False, "error": f"{ca_path} 파일을 찾을 수 없습니다. 다른 앱(ocp-create-iso)에서 'CA 신뢰 설정'을 먼저 실행했는지 확인하세요."})
    
    # root 소유의 파일일 수 있으므로 sudo cat으로 읽음
#    result = run_command(f"sudo cat {ca_path}")
    
#    if result['success']:
#        return jsonify({"success": True, "ca_content": result['output']})
#    else:
#        return jsonify({"success": False, "error": f"CA 인증서 파일을 읽을 수 없습니다: {result['error']}"})


@app.route('/api/get-mirror-ca')
def get_mirror_ca():
    """/etc/pki/ca-trust/source/anchors/rootCA.pem 파일 내용을 읽어 반환합니다."""
    ca_path = "/etc/pki/ca-trust/source/anchors/rootCA.pem"
    if not os.path.exists(ca_path):
        return jsonify({"success": False, "error": f"{ca_path} 파일을 찾을 수 없습니다. 다른 앱(ocp-create-iso)에서 'CA 신뢰 설정'을 먼저 실행했는지 확인하세요."})

    try:
        # 파일을 읽기 전에 모든 사용자에게 읽기 권한을 부여합니다.
        chmod_result = run_command(f"sudo chmod a+r {ca_path}")
        if not chmod_result['success']:
            return jsonify({"success": False, "error": f"파일 권한 변경 실패: {chmod_result['error']}"})

        # 이제 sudo 없이 직접 파일을 읽을 수 있습니다.
        with open(ca_path, 'r') as f:
            cert_content = f.read()
        
        return jsonify({"success": True, "ca_content": cert_content})
    except Exception as e:
        return jsonify({"success": False, "error": f"파일을 읽는 중 오류 발생: {str(e)}"})


# --- YAML 생성 라우팅 ---
@app.route('/generate-install-config', methods=['POST'])
def generate_install_config():
    """폼 데이터로 install-config.yaml 파일을 생성하여 로컬에 저장합니다."""
    config_data = request.form.to_dict()
    config_data['proxy_enabled'] = 'proxy_enabled' in config_data
    

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
    app.run(debug=True, host='0.0.0.0', port=5023)
