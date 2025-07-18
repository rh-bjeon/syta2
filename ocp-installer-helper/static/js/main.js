// 전역 변수로 클러스터 정보 저장
let clusterData = {};

// 페이지 로드 시 클러스터 정보 미리 불러오기
window.onload = async () => {
    try {
        const response = await fetch('/api/load-cluster-info');
        if (response.ok) {
            clusterData = await response.json();
            console.log("클러스터 정보 로드 완료:", clusterData);
        } else {
            console.error("클러스터 정보 로드 실패");
        }
    } catch (e) {
        console.error("API 호출 오류:", e);
    }
};

// --- 섹션 2: install-config.yaml 관련 함수 ---

async function generateSshKey() {
    const keyName = document.getElementById('key_name').value;
    if (!keyName) {
        alert('SSH 키 이름을 입력하세요.');
        return;
    }
    const response = await fetch('/generate-ssh-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key_name: keyName })
    });
    const message = await response.text();
    alert(message);
}

function loadClusterInfoForInstallConfig() {
    if (!clusterData || Object.keys(clusterData).length === 0) {
        alert("먼저 '섹션 1'에서 노드 정보 파일을 업로드하세요.");
        return;
    }
    // Excel 데이터에서 대표값 가져오기 (예시)
    const firstNodeKey = Object.keys(clusterData)[0];
    const firstNode = clusterData[firstNodeKey];

    document.getElementById('baseDomain').value = firstNode.baseDomain || '';
    document.getElementById('metadataName').value = firstNode.clusterName || '';
    document.getElementById('clusterNetworkCIDR').value = firstNode.clusterNetwork_CIDR || '10.128.0.0/14';
    document.getElementById('serviceNetwork').value = firstNode.serviceNetwork || '172.30.0.0/16';
    document.getElementById('hostPrefix').value = firstNode.hostPrefix || '23';
    document.getElementById('httpProxy').value = firstNode.httpProxy || '';
    document.getElementById('httpsProxy').value = firstNode.httpsProxy || '';
    document.getElementById('noProxy').value = firstNode.noProxy || '';
}

function toggleProxy() {
    const proxySettings = document.getElementById('proxy_settings');
    proxySettings.style.display = document.getElementById('proxy_enabled').checked ? 'block' : 'none';
}

async function insertSshKey() {
    const keyName = document.getElementById('key_name').value;
    if (!keyName) {
        alert('먼저 SSH 키 이름을 입력하고 생성하세요.');
        return;
    }
    const response = await fetch(`/api/get-ssh-key/${keyName}`);
    const data = await response.json();
    if (data.error) {
        alert(data.error);
    } else {
        document.getElementById('sshKey').value = data.key;
    }
}

async function loadMirrorSecret() {
    const response = await fetch('/api/load-mirror-secret');
    const data = await response.json();
    if (data.error) {
        alert(data.error);
        return;
    }
    // 실제 pull secret 형식으로 만들어야 함. 여기서는 예시로 JSON 문자열을 사용
    const pullSecretValue = JSON.stringify({
        "auths": {
            [data.registry_url]: {
                "auth": btoa(`${data.registry_user}:${data.registry_password}`),
                "email": "you@example.com"
            }
        }
    }, null, 2);
    document.getElementById('pullSecret').value = pullSecretValue;
}

// --- 섹션 4: agent-config.yaml 관련 함수 ---
let nodeCounter = 0;

function loadClusterInfoForAgentConfig() {
    if (!clusterData || Object.keys(clusterData).length === 0) {
        alert("먼저 '섹션 1'에서 노드 정보 파일을 업로드하세요.");
        return;
    }
    const firstNodeKey = Object.keys(clusterData)[0];
    const firstNode = clusterData[firstNodeKey];
    
    document.getElementById('agent_metadata_name').value = firstNode.clusterName || '';
    document.getElementById('rendezvousIP').value = firstNode.rendezvousIP || '';
    document.getElementById('additionalNTPSources').value = firstNode.ntp_server || '';
}


function addNodeSection() {
    const container = document.getElementById('nodes-container');
    const nodeIndex = nodeCounter++;
    
    const nodeHtml = `
        <div class="node-section" id="node-${nodeIndex}">
            <h4>Node ${nodeIndex + 1} <button type="button" onclick="removeNodeSection(${nodeIndex})">X</button></h4>
            <label>Role:</label>
            <select class="node-role" data-index="${nodeIndex}" onchange="updateHostnames(this)">
                <option value="" disabled selected>역할 선택</option>
                <option value="master">master</option>
                <option value="worker">worker</option>
                <option value="infra">infra</option>
            </select><br>
            <label>Hostname:</label>
            <select class="node-hostname" data-index="${nodeIndex}" onchange="populateNodeData(this)">
                <option value="" disabled selected>호스트 선택</option>
            </select><br>
            <label>Interface Type:</label>
            <select class="node-interface-type" data-index="${nodeIndex}">
                <option value="ethernet">Ethernet</option>
                <option value="bond">Bond</option>
            </select><br>
            <label>Root Device:</label> <input type="text" class="node-disk" data-index="${nodeIndex}" placeholder="/dev/sda"><br>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', nodeHtml);
}

function removeNodeSection(index) {
    document.getElementById(`node-${index}`).remove();
}

function updateHostnames(roleSelect) {
    const selectedRole = roleSelect.value;
    const index = roleSelect.dataset.index;
    const hostnameSelect = document.querySelector(`.node-hostname[data-index='${index}']`);
    
    // 이전에 선택된 호스트네임들을 가져옴
    const selectedHostnames = new Set();
    document.querySelectorAll('.node-hostname').forEach(select => {
        if (select !== hostnameSelect && select.value) {
            selectedHostnames.add(select.value);
        }
    });

    // 옵션 초기화
    hostnameSelect.innerHTML = '<option value="" disabled selected>호스트 선택</option>';
    
    Object.keys(clusterData)
        .filter(hostname => clusterData[hostname].role === selectedRole && !selectedHostnames.has(hostname))
        .forEach(hostname => {
            const option = new Option(hostname, hostname);
            hostnameSelect.add(option);
        });
}

function populateNodeData(hostnameSelect) {
    // 이 함수는 현재 예제에서 직접 필드를 채우지 않습니다.
    // 대신, 제출 시 모든 노드 데이터를 수집하여 전송합니다.
    console.log(`${hostnameSelect.value} 선택됨`);
}

// agent-config.yaml form 제출 시 이벤트 처리
document.getElementById('agent-config-form').addEventListener('submit', function(event) {
    const nodesArray = [];
    const nodeSections = document.querySelectorAll('.node-section');
    
    for (const section of nodeSections) {
        const index = section.id.split('-')[1];
        const hostname = section.querySelector('.node-hostname').value;
        const role = section.querySelector('.node-role').value;
        const disk = section.querySelector('.node-disk').value;
        const interfaceType = section.querySelector('.node-interface-type').value;

        if (!hostname || !role || !disk) {
            alert(`Node ${parseInt(index)+1}의 모든 필드를 채워주세요.`);
            event.preventDefault(); // 폼 제출 중단
            return;
        }

        const nodeExcelData = clusterData[hostname];
        
        const nodeInfo = {
            hostname: hostname,
            role: role,
            interface_name: nodeExcelData.interface_name,
            mac_address: nodeExcelData.mac,
            disk_deviceName: disk,
            interface_type: interfaceType,
            ip_address: nodeExcelData.ip,
            prefix_length: nodeExcelData.prefix,
            dns_resolver: nodeExcelData.dns,
        };

        // Bond 타입일 경우 Bond 정보 추가
        if (interfaceType === 'bond') {
            nodeInfo.interfaces_neme_bond = nodeExcelData.bond_name;
            nodeInfo.link_aggregation_mode = nodeExcelData.bond_mode;
            nodeInfo.miimon = nodeExcelData.bond_miimon;
            nodeInfo.xmit_hash_policy = nodeExcelData.bond_xmit_hash_policy;
            nodeInfo.port1 = nodeExcelData.bond_port1;
            nodeInfo.port2 = nodeExcelData.bond_port2;
        }

        nodesArray.push(nodeInfo);
    }
    
    // 수집된 노드 데이터를 JSON 문자열로 변환하여 hidden input에 저장
    document.getElementById('nodes_data_hidden').value = JSON.stringify(nodesArray);
});
