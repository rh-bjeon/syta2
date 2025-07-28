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
let lastSubmittedSection = null;

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
        setTimeout(() => {
            try {
                const iframeBody = iframe.contentWindow.document.body;
                const message = iframeBody.textContent || iframeBody.innerText;
                const statusDiv = document.getElementById(`status-message-${lastSubmittedSection}`) || document.getElementById('status-message-fallback');
                statusDiv.textContent = message;
                
                if (message.includes('성공적으로 저장') || message.includes('생성되었습니다')) {
                    statusDiv.style.color = 'green';
                    if (message.includes('클러스터 정보가 성공적으로 저장')) {
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

function setupSubmitButtonListener() {
    document.querySelectorAll('button[type="submit"]').forEach(button => {
        button.addEventListener('click', function() {
            lastSubmittedSection = this.dataset.section;
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
    if (document.getElementById('mirror_enabled').checked) {
        loadMirrorRegistryInfo();
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

function toggleMirrorRegistry() {
    const mirrorSettings = document.getElementById('mirror_settings');
    const isChecked = document.getElementById('mirror_enabled').checked;
    mirrorSettings.style.display = isChecked ? 'block' : 'none';
    if (isChecked) {
        loadMirrorRegistryInfo();
    }
}

function loadMirrorRegistryInfo() {
    if (!clusterData || Object.keys(clusterData).length === 0) {
        alert("먼저 '섹션 1'에서 클러스터 정보 파일(CSV)을 업로드하세요.");
        return;
    }
    document.getElementById('registry_address').value = clusterData.local_registry || '';
    document.getElementById('registry_user').value = clusterData.local_registry_user || '';
    document.getElementById('registry_password').value = clusterData.local_registry_password || '';
}

function generateMirrorPullSecret() {
    const regAddr = document.getElementById('registry_address').value;
    const regUser = document.getElementById('registry_user').value;
    const regPass = document.getElementById('registry_password').value;

    if (!document.getElementById('mirror_enabled').checked) {
        alert("'미러레지스트리 사용'을 먼저 체크해주세요.");
        return;
    }
    if (!regAddr || !regUser || !regPass) {
        alert("레지스트리 정보가 없습니다. CSV에 local_registry, local_registry_user, local_registry_password 키가 있는지 확인하세요.");
        return;
    }

    const authString = btoa(`${regUser}:${regPass}`);
    const pullSecretObject = {
        "auths": {
            [regAddr]: {
                "auth": authString
            }
        }
    };
    document.getElementById('pullSecret').value = JSON.stringify(pullSecretObject, null, 4);
}


// [신규] Mirror CA 인증서를 불러오는 함수 (오류 처리 강화)
async function loadMirrorCa() {
    try {
        const response = await fetch('/api/get-mirror-ca');
        
        // 서버 응답이 성공적인지 먼저 확인
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`서버 오류: ${response.status} ${response.statusText}\n${errorText}`);
        }

        const data = await response.json();

        if (data.success) {
            document.getElementById('additionalTrustBundle').value = data.ca_content;
            alert('✅ Mirror CA 인증서를 성공적으로 불러왔습니다.');
        } else {
            alert(`❌ 오류: ${data.error}`);
        }
    } catch (error) {
        // 네트워크 오류 또는 JSON 파싱 오류 처리
        alert(`❌ 요청 실패: ${error.message}`);
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
            hostname: `${state.hostname}.${clusterData.metadata_name}.${clusterData.base_domain}`,
            rootDeviceHints: { deviceName: getFieldValue('disk') },
            interfaces: [],
            networkConfig: { interfaces: [] }
        };

        let gateway, nextHopInterface;

        if (interfaceType === 'ethernet') {
            const ifaceName = getFieldValue("interface");
            finalNodeData.interfaces.push({ name: ifaceName, macAddress: getFieldValue("mac") });
            
            const networkInterface = {
                name: ifaceName,
                type: 'ethernet',
                state: 'up',
                'mac-address': getFieldValue("mac"),
                ipv4: {
                    enabled: String(true).toLowerCase(),
                    address: [{ ip: getFieldValue("nodeip"), 'prefix-length': parseInt(getFieldValue("prefix"), 10) }],
                    dhcp: String(false).toLowerCase()
                },
                ipv6: { enabled: String(false).toLowerCase() }
            };
            const mtu = getFieldValue('mtu');
            if (mtu) networkInterface.mtu = parseInt(mtu, 10);
            finalNodeData.networkConfig.interfaces.push(networkInterface);
            
            gateway = getFieldValue("gw");
            nextHopInterface = ifaceName;
            finalNodeData.networkConfig['dns-resolver'] = { config: { server: [getFieldValue("dns")] } };

        } else { // bond
            const bondName = getFieldValue("bond_Interface_name");
            const port1Name = getFieldValue("bond_Interface1");
            const port2Name = getFieldValue("bond_Interface2");

            finalNodeData.interfaces.push({ name: port1Name, macAddress: getFieldValue("bond_mac1") });
            finalNodeData.interfaces.push({ name: port2Name, macAddress: getFieldValue("bond_mac2") });
            
            const networkInterface = {
                name: bondName,
                type: 'bond',
                state: 'up',
                'mac-address': getFieldValue("bond_mac1"),
                ipv4: {
                    enabled: String(true).toLowerCase(),
                    address: [{ ip: getFieldValue("nodeip"), 'prefix-length': parseInt(getFieldValue("prefix"), 10) }],
                    dhcp: String(false).toLowerCase()
                },
                ipv6: { enabled: String(false).toLowerCase() },
                'link-aggregation': {
                    mode: getFieldValue("bond_link-aggregation_mode"),
                    options: {
                        miimon: getFieldValue("bond_miimon")
                    },
                    port: [port1Name, port2Name]
                }
            };
            const mtu = getFieldValue("mtu");
            if (mtu) networkInterface.mtu = parseInt(mtu, 10);
            finalNodeData.networkConfig.interfaces.push(networkInterface);

            gateway = getFieldValue("gw");
            nextHopInterface = bondName;
            finalNodeData.networkConfig['dns-resolver'] = { config: { server: [getFieldValue("dns")] } };
        }

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
