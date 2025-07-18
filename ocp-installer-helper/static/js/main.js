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
