// ==================================================================
// Global State Management
// ==================================================================
let clusterData = {};
const availableHostnames = {
    master: ['master0', 'master1', 'master2'],
    infra: ['infra0', 'infra1', 'infra2'],
    worker: ['worker0', 'worker1', 'worker2', 'worker3', 'worker4']
};
let selectedHostnames = new Set();
let roleCounts = { master: 0, infra: 0, worker: 0 };
let nodeState = {};
let nodeCounter = 0;
let lastSubmittedSection = null; // 마지막으로 제출된 폼의 섹션 번호를 추적

// ==================================================================
// Initial Load & Data Fetch
// ==================================================================
window.onload = () => {
    loadClusterData();
    setupIframeListener();
    setupSubmitButtonListener();
};

async function loadClusterData() {
    try {
        const response = await fetch('/api/load-cluster-info');
        if (response.ok) {
            clusterData = await response.json();
            console.log("클러스터 정보 로드/갱신 완료:", clusterData);
        } else {
            clusterData = {};
            console.error("클러스터 정보 로드 실패 또는 파일 없음");
        }
    } catch (e) {
        console.error("API 호출 오류:", e);
    }
}

function setupIframeListener() {
    const iframe = document.getElementById('result_iframe');
    iframe.onload = () => {
        // iframe 로드 완료 후 약간의 지연을 주어 내용이 완전히 렌더링되도록 함
        setTimeout(() => {
            try {
                const iframeBody = iframe.contentWindow.document.body;
                const message = iframeBody.textContent || iframeBody.innerText;
                
                // 올바른 섹션에 상태 메시지 표시
                const statusDiv = document.getElementById(`status-message-${lastSubmittedSection}`) || document.getElementById('status-message-fallback');
                statusDiv.textContent = message;
                
                if (message.includes('성공적으로 저장') || message.includes('생성되었습니다')) {
                    statusDiv.style.color = 'green';
                    if (message.includes('클러스터 정보가 성공적으로 저장')) {
                        console.log('파일 업로드 성공. 클러스터 데이터를 다시 로드합니다.');
                        loadClusterData();
                    }
                } else {
                    statusDiv.style.color = 'red';
                }
            } catch (e) {
                console.error("iframe 내용 접근 오류:", e);
                document.getElementById('status-message-fallback').textContent = "작업 완료 (결과를 표시할 수 없음)";
            }
        }, 100);
    };
}

// 제출 버튼 클릭 시 어떤 섹션인지 추적하는 리스너
function setupSubmitButtonListener() {
    document.querySelectorAll('button[type="submit"]').forEach(button => {
        button.addEventListener('click', function() {
            lastSubmittedSection = this.dataset.section;
            // 메시지 초기화
            const statusDiv = document.getElementById(`status-message-${lastSubmittedSection}`);
            if(statusDiv) statusDiv.textContent = '처리 중...';
        });
    });
}


// ==================================================================
// Section 2: install-config.yaml Functions
// ==================================================================
function loadClusterInfoForInstallConfig() {
    if (!clusterData || Object.keys(clusterData).length === 0) {
        alert("먼저 '섹션 1'에서 클러스터 정보 파일(CSV)을 업로드하세요.");
        return;
    }
    document.getElementById('baseDomain').value = clusterData.base_domain || '';
    document.getElementById('metadataName').value = clusterData.metadata_name || '';
    document.getElementById('machineNetworkCIDR').value = clusterData.machine_network_cidr || '';
    document.getElementById('clusterNetworkCIDR').value = clusterData.cluster_network_cidr || '10.128.0.0/14';
    document.getElementById('serviceNetwork').value = clusterData.service_network || '172.30.0.0/16';
    document.getElementById('hostPrefix').value = clusterData.host_prefix || '23';

    if (document.getElementById('proxy_enabled').checked) {
        document.getElementById('httpProxy').value = clusterData.httpProxy || '';
        document.getElementById('httpsProxy').value = clusterData.httpsProxy || '';
        document.getElementById('noProxy').value = clusterData.noProxy || '';
    }
}

function toggleProxy() {
    const proxySettings = document.getElementById('proxy_settings');
    const isChecked = document.getElementById('proxy_enabled').checked;
    proxySettings.style.display = isChecked ? 'block' : 'none';
    if (isChecked) {
        loadClusterInfoForInstallConfig();
    }
}

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
    const pullSecretValue = JSON.stringify({
        "auths": {
            [data.registry_url]: {
                "auth": btoa(`${data.registry_user}:${data.registry_password}`),
                "email": "you@example.com"
            }
        }
    }, null, 4);
    document.getElementById('pullSecret').value = pullSecretValue;
}


// ==================================================================
// Section 3: agent-config.yaml Functions
// ==================================================================
function loadClusterInfoForAgentConfig() {
    if (!clusterData || Object.keys(clusterData).length === 0) {
        alert("먼저 '섹션 1'에서 클러스터 정보 파일(CSV)을 업로드하세요.");
        return;
    }
    document.getElementById('agent_metadata_name').value = clusterData.metadata_name || '';
    document.getElementById('rendezvousIP').value = clusterData.rendezvousIP || clusterData.nodeip_master0 || '';
    document.getElementById('additionalNTPSources').value = clusterData.ntp || '';
}

function addNodeSection() {
    const container = document.getElementById('nodes-container');
    const nodeIndex = nodeCounter++;
    
    nodeState[nodeIndex] = { role: null, hostname: null, interfaceType: 'ethernet' };

    const nodeHtml = `
        <div class="node-section" id="node-${nodeIndex}">
            <h4>Node ${nodeIndex + 1} <button type="button" onclick="removeNodeSection(${nodeIndex})">X</button></h4>
            <label>Role:</label>
            <select class="node-role" data-index="${nodeIndex}" onchange="handleRoleChange(this)">
                <option value="" disabled selected>역할 선택</option>
                <option value="master">master</option>
                <option value="infra">infra</option>
                <option value="worker">worker</option>
            </select><br>
            <label>Hostname:</label>
            <select class="node-hostname" data-index="${nodeIndex}" onchange="handleHostnameChange(this)" disabled>
                <option value="" disabled selected>호스트 선택</option>
            </select><br>
            <label>Interface Type:</label>
            <select class="node-interface-type" data-index="${nodeIndex}" onchange="handleInterfaceTypeChange(this)">
                <option value="ethernet" selected>Ethernet</option>
                <option value="bond">Bond</option>
            </select><br><br>
            
            <div class="interface-fields ethernet-fields" data-index="${nodeIndex}" style="display: block;">
                <label>Interface Name:</label> <input type="text" class="node-field" data-field="interface" readonly><br>
                <label>MAC Address:</label> <input type="text" class="node-field" data-field="mac" readonly><br>
                <label>MTU:</label> <input type="text" class="node-field" data-field="mtu" readonly><br>
                <label>IP Address:</label> <input type="text" class="node-field" data-field="nodeip" readonly><br>
                <label>Prefix Length:</label> <input type="text" class="node-field" data-field="prefix" readonly><br>
                <label>DNS Resolver:</label> <input type="text" class="node-field" data-field="dns" readonly><br>
                <label>Gateway:</label> <input type="text" class="node-field" data-field="gw" readonly><br>
            </div>
            <div class="interface-fields bond-fields" data-index="${nodeIndex}" style="display: none;">
                <label>Bond Name:</label> <input type="text" class="node-field" data-field="bond_Interface_name" readonly><br>
                <label>Interface 1 Name:</label> <input type="text" class="node-field" data-field="bond_Interface1" readonly><br>
                <label>Interface 1 MAC:</label> <input type="text" class="node-field" data-field="bond_mac1" readonly><br>
                <label>Interface 2 Name:</label> <input type="text" class="node-field" data-field="bond_Interface2" readonly><br>
                <label>Interface 2 MAC:</label> <input type="text" class="node-field" data-field="bond_mac2" readonly><br>
                <label>Bond Mode:</label> <input type="text" class="node-field" data-field="bond_link-aggregation_mode" readonly><br>
                <label>MIIMon:</label> <input type="text" class="node-field" data-field="bond_miimon" readonly><br>
                <label>MTU:</label> <input type="text" class="node-field" data-field="mtu" readonly><br>
                <label>IP Address:</label> <input type="text" class="node-field" data-field="nodeip" readonly><br>
                <label>Prefix Length:</label> <input type="text" class="node-field" data-field="prefix" readonly><br>
                <label>DNS Resolver:</label> <input type="text" class="node-field" data-field="dns" readonly><br>
                <label>Gateway:</label> <input type="text" class="node-field" data-field="gw" readonly><br>
            </div>
            
            <label>Root Device:</label> <input type="text" class="node-field" data-field="disk" readonly><br>
            <hr>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', nodeHtml);
}

function handleInterfaceTypeChange(selectElement) {
    const index = selectElement.dataset.index;
    const newType = selectElement.value;
    nodeState[index].interfaceType = newType;
    document.querySelector(`.ethernet-fields[data-index='${index}']`).style.display = (newType === 'ethernet') ? 'block' : 'none';
    document.querySelector(`.bond-fields[data-index='${index}']`).style.display = (newType === 'bond') ? 'block' : 'none';
    const currentHostname = nodeState[index].hostname;
    if (currentHostname) {
        populateNodeFields(index, currentHostname);
    }
}

function removeNodeSection(index) {
    const state = nodeState[index];
    if (state.role) roleCounts[state.role]--;
    if (state.hostname) selectedHostnames.delete(state.hostname);
    delete nodeState[index];
    document.getElementById(`node-${index}`).remove();
    updateAllHostnameDropdowns();
}

function handleRoleChange(selectElement) {
    const index = selectElement.dataset.index;
    const newRole = selectElement.value;
    const oldRole = nodeState[index].role;
    if ((newRole === 'master' || newRole === 'infra') && roleCounts[newRole] >= 3) {
        alert(`'${newRole}' 역할은 최대 3개까지만 선택할 수 있습니다.`);
        selectElement.value = oldRole || '';
        return;
    }
    if (oldRole) roleCounts[oldRole]--;
    roleCounts[newRole]++;
    nodeState[index].role = newRole;
    const oldHostname = nodeState[index].hostname;
    if (oldHostname) {
        selectedHostnames.delete(oldHostname);
        nodeState[index].hostname = null;
        clearNodeFields(index);
    }
    populateHostnameDropdown(index);
    updateAllHostnameDropdowns();
}

function populateHostnameDropdown(index) {
    const state = nodeState[index];
    const role = state.role;
    const hostnameSelect = document.querySelector(`.node-hostname[data-index='${index}']`);
    const currentSelectedHostname = state.hostname;

    hostnameSelect.innerHTML = '<option value="" disabled selected>호스트 선택</option>';
    hostnameSelect.disabled = true;
    if (!role) return;

    const hostnamesForRole = availableHostnames[role] || [];
    hostnamesForRole.forEach(hostname => {
        if (!selectedHostnames.has(hostname) || hostname === currentSelectedHostname) {
            const option = new Option(hostname, hostname);
            hostnameSelect.add(option);
        }
    });

    hostnameSelect.value = currentSelectedHostname;
    hostnameSelect.disabled = false;
}

function updateAllHostnameDropdowns() {
    Object.keys(nodeState).forEach(indexStr => {
        const index = parseInt(indexStr, 10);
        populateHostnameDropdown(index);
    });
}

function handleHostnameChange(selectElement) {
    const index = selectElement.dataset.index;
    const newHostname = selectElement.value;
    const oldHostname = nodeState[index].hostname;
    if (oldHostname) selectedHostnames.delete(oldHostname);
    selectedHostnames.add(newHostname);
    nodeState[index].hostname = newHostname;
    updateAllHostnameDropdowns();
}

function populateNodeFields(index, hostname) {
    clearNodeFields(index);
    if (!hostname) return;
    
    const allFields = document.querySelectorAll(`#node-${index} .node-field`);
    allFields.forEach(input => {
        const field = input.dataset.field;
        const dataKey = `${field}_${hostname}`;
        if (clusterData.hasOwnProperty(dataKey)) {
            input.value = clusterData[dataKey];
        }
    });
}

function clearNodeFields(index) {
    document.querySelectorAll(`#node-${index} .node-field`).forEach(input => input.value = '');
}

function populateAllNodeData() {
    if (!clusterData || Object.keys(clusterData).length === 0) {
        alert("먼저 '섹션 1'에서 클러스터 정보 파일(CSV)을 업로드하세요.");
        return;
    }
    let populatedCount = 0;
    Object.keys(nodeState).forEach(indexStr => {
        const index = parseInt(indexStr, 10);
        const state = nodeState[index];
        if (state.hostname) {
            populateNodeFields(index, state.hostname);
            populatedCount++;
        } else {
            console.warn(`Node ${index + 1}는 호스트네임이 선택되지 않아 데이터를 불러올 수 없습니다.`);
        }
    });
    if (populatedCount > 0) {
        alert("모든 노드의 정보 불러오기를 완료했습니다.");
    } else {
        alert("정보를 불러올 노드가 없습니다. 먼저 각 노드의 역할과 호스트네임을 선택해주세요.");
    }
}

document.getElementById('agent-config-form').addEventListener('submit', function(event) {
    const nodesArray = [];
    const nodeSections = document.querySelectorAll('.node-section');
    for (const section of nodeSections) {
        const index = section.id.split('-')[1];
        const state = nodeState[index];
        if (!state.role || !state.hostname) {
            alert(`Node ${parseInt(index) + 1}의 역할과 호스트네임을 모두 선택해주세요.`);
            event.preventDefault();
            return;
        }
        const interfaceType = state.interfaceType;
        const getFieldValue = (field) => section.querySelector(`.node-field[data-field='${field}']`)?.value || '';
        
        const finalNodeData = {
            role: state.role,
            // [수정 1] 호스트네임 생성 방식 변경
            hostname: `${state.hostname}.${clusterData.metadata_name}.${clusterData.base_domain}`,
            rootDeviceHints: { deviceName: getFieldValue('disk') },
            interfaces: [],
            networkConfig: { interfaces: [] }
        };

        let gateway, nextHopInterface, ip_address, prefix_length, dns_resolver, mtu;

        if (interfaceType === 'ethernet') {
            const ifaceName = getFieldValue("interface");
            finalNodeData.interfaces.push({ name: ifaceName, macAddress: getFieldValue("mac") });
            
            mtu = getFieldValue('mtu');
            ip_address = getFieldValue("nodeip");
            prefix_length = getFieldValue("prefix");
            dns_resolver = getFieldValue("dns");
            gateway = getFieldValue("gw");
            nextHopInterface = ifaceName;
            
            const networkInterface = {
                name: ifaceName,
                type: 'ethernet',
                state: 'up',
                'mac-address': getFieldValue("mac"),
                ipv4: {
                    // [수정 3] boolean 값을 소문자 문자열로 변경
                    enabled: String(true).toLowerCase(),
                    address: [{ ip: ip_address, 'prefix-length': parseInt(prefix_length, 10) }],
                    dhcp: String(false).toLowerCase()
                },
                ipv6: { enabled: String(false).toLowerCase() }
            };
            if (mtu) networkInterface.mtu = parseInt(mtu, 10);
            finalNodeData.networkConfig.interfaces.push(networkInterface);

        } else { // bond
            const bondName = getFieldValue("bond_Interface_name");
            const port1Name = getFieldValue("bond_Interface1");
            const port2Name = getFieldValue("bond_Interface2");

            finalNodeData.interfaces.push({ name: port1Name, macAddress: getFieldValue("bond_mac1") });
            finalNodeData.interfaces.push({ name: port2Name, macAddress: getFieldValue("bond_mac2") });
            
            mtu = getFieldValue("mtu");
            ip_address = getFieldValue("nodeip");
            prefix_length = getFieldValue("prefix");
            dns_resolver = getFieldValue("dns");
            gateway = getFieldValue("gw");
            nextHopInterface = bondName;

            const networkInterface = {
                name: bondName,
                type: 'bond',
                state: 'up',
                'mac-address': getFieldValue("bond_mac1"),
                ipv4: {
                    // [수정 3] boolean 값을 소문자 문자열로 변경
                    enabled: String(true).toLowerCase(),
                    address: [{ ip: ip_address, 'prefix-length': parseInt(prefix_length, 10) }],
                    dhcp: String(false).toLowerCase()
                },
                ipv6: { enabled: String(false).toLowerCase() },
                'link-aggregation': {
                    mode: getFieldValue("bond_link-aggregation_mode"),
                    // [수정 2] miimon 형식을 중첩 객체로 변경
                    options: {
                        miimon: getFieldValue("bond_miimon")
                    },
                    port: [port1Name, port2Name]
                }
            };
            if (mtu) networkInterface.mtu = parseInt(mtu, 10);
            finalNodeData.networkConfig.interfaces.push(networkInterface);
        }

        finalNodeData.networkConfig['dns-resolver'] = { config: { server: [dns_resolver] } };
        if (gateway && nextHopInterface) {
            finalNodeData.networkConfig.routes = { config: [{
                destination: '0.0.0.0/0',
                'next-hop-address': gateway,
                'next-hop-interface': nextHopInterface,
                'table-id': 254
            }]};
        }

        nodesArray.push(finalNodeData);
    }
    document.getElementById('nodes_data_hidden').value = JSON.stringify(nodesArray);
});
