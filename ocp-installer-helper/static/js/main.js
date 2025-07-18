function generateSshKey() {
    const keyName = document.getElementById('key_name').value;
    if (!keyName) { alert('SSH 키 이름을 입력하세요.'); return; }
    
    fetch('/generate-ssh-key', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ key_name: keyName })
    })
    .then(response => response.text())
    .then(data => alert(data));
}

// loadClusterInfo, insertSshKey, loadMirrorSecret 등 나머지 JS 함수 구현 필요



let nodeCounter = 0;
// 업로드된 노드 정보 (페이지 로드 시 미리 불러옴)
let availableNodes = {}; 

// 페이지 로드 시, /api/load-cluster-info 를 호출하여 availableNodes를 채워야 합니다.

function addNodeSection() {
    const container = document.getElementById('nodes-container');
    const nodeHtml = `
        <div class="node-section" id="node-${nodeCounter}">
            <h4>Node ${nodeCounter + 1}</h4>
            <label>Role:</label>
            <select name="nodes[${nodeCounter}][role]" onchange="updateHostnames(${nodeCounter})">
                <option value="master">master</option>
                <option value="worker">worker</option>
                <option value="infra">infra</option>
            </select><br>
            <label>Hostname:</label>
            <select name="nodes[${nodeCounter}][hostname]" id="hostname-${nodeCounter}" onchange="populateNodeData(${nodeCounter})">
                </select><br>
            <label>Interface Type:</label>
            <select name="nodes[${nodeCounter}][interface_type]">
                <option value="ethernet">Ethernet</option>
                <option value="bond">Bond</option>
            </select><br>
            <input type="hidden" id="mac-${nodeCounter}" name="nodes[${nodeCounter}][mac_address]">
            <input type="hidden" id="ip-${nodeCounter}" name="nodes[${nodeCounter}][ip_address]">
            ...
            <label>Root Device:</label> <input type="text" name="nodes[${nodeCounter}][disk_deviceName]"><br>
            <hr>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', nodeHtml);
    updateHostnames(nodeCounter); // 초기 호스트네임 목록 채우기
    nodeCounter++;
}

function updateHostnames(index) {
    // availableNodes 객체와 현재 선택된 role을 바탕으로
    // 중복되지 않는 호스트네임 목록을 생성하여 드롭다운을 채웁니다.
    // 다른 노드에서 이미 선택된 호스트네임은 제외하는 로직이 필요합니다.
}

function populateNodeData(index) {
    const hostname = document.getElementById(`hostname-${index}`).value;
    const nodeData = availableNodes[hostname];
    
    // nodeData를 사용하여 해당 노드의 MAC, IP 등 필드를 자동으로 채웁니다.
    document.getElementById(`mac-${index}`).value = nodeData.mac_address;
    document.getElementById(`ip-${index}`).value = nodeData.ip_address;
    // ...
}
