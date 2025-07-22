document.addEventListener('DOMContentLoaded', () => {
    const ocpVersionSelect = document.getElementById('ocp_version_select');

    // --- Helper Functions ---
    const showLoading = (outputBox) => {
        outputBox.textContent = '명령 실행 중...';
        outputBox.style.color = 'blue';
    };

    const showResult = (outputBox, result) => {
        if (result.success) {
            outputBox.style.color = 'green';
            outputBox.textContent = '✅ 성공!\n' + (result.output || result.message || '');
        } else {
            outputBox.style.color = 'red';
            outputBox.textContent = '❌ 실패!\n' + (result.error || '알 수 없는 오류');
        }
    };

    const callApi = async (endpoint, body) => {
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            return await response.json();
        } catch (error) {
            return { success: false, error: `API 호출 실패: ${error.message}` };
        }
    };

    // --- Section 1: OCP Installer 준비 ---
    const fetchOcpVersions = async () => {
        ocpVersionSelect.innerHTML = '<option>버전 목록을 불러오는 중...</option>';
        try {
            const response = await fetch('/api/get-ocp-versions');
            const data = await response.json();
            if (data.success) {
                ocpVersionSelect.innerHTML = '';
                data.versions.forEach(version => {
                    const option = new Option(version, version);
                    ocpVersionSelect.add(option);
                });
            } else {
                ocpVersionSelect.innerHTML = `<option>버전 로드 실패: ${data.error}</option>`;
            }
        } catch (error) {
            ocpVersionSelect.innerHTML = `<option>API 오류: ${error.message}</option>`;
        }
    };

    document.getElementById('btn_fetch_versions').addEventListener('click', fetchOcpVersions);

    // --- Section 1 & 2: 명령어 실행 버튼 공통 처리 ---
    document.querySelectorAll('button[data-command-key]').forEach(button => {
        button.addEventListener('click', async () => {
            const commandKey = button.dataset.commandKey;
            const outputBox = document.getElementById(`output_${commandKey}`);
            const selectedVersion = ocpVersionSelect.value;

            if (!selectedVersion && (commandKey.includes('installer') || commandKey.includes('oc_mirror'))) {
                alert('먼저 OCP 버전을 선택해주세요.');
                return;
            }

            showLoading(outputBox);
            const result = await callApi('/api/execute-command', {
                command_key: commandKey,
                version: selectedVersion,
            });
            showResult(outputBox, result);
        });
    });

    // --- Section 3: Mirror Image 준비 ---
    document.querySelectorAll('.btn-list-operators').forEach(button => {
        button.addEventListener('click', async () => {
            const catalog = button.dataset.catalog;
            const listDiv = document.getElementById(`list_${catalog}`);
            const selectedVersion = ocpVersionSelect.value;

            if (!document.getElementById(`chk_${catalog.split('-')[0]}`).checked) {
                alert('먼저 해당 카탈로그의 체크박스를 선택해주세요.');
                return;
            }
            if (!selectedVersion) {
                alert('먼저 OCP 버전을 선택해주세요.');
                return;
            }

            listDiv.innerHTML = 'Operator 목록을 불러오는 중...';
            const result = await callApi('/api/list-operators', {
                catalog: catalog,
                version: selectedVersion.split('.').slice(0, 2).join('.'), // 4.14.20 -> 4.14
            });

            if (result.success) {
                listDiv.innerHTML = '';
                result.operators.forEach(op => {
                    const checkboxId = `op-${catalog}-${op.name}`;
                    const item = document.createElement('div');
                    item.className = 'operator-item';
                    item.innerHTML = `
                        <input type="checkbox" id="${checkboxId}" data-name="${op.name}" data-channel="${op.defaultChannel}">
                        <label for="${checkboxId}">${op.displayName} (${op.name})</label>
                    `;
                    listDiv.appendChild(item);
                });
            } else {
                listDiv.innerHTML = `<span style="color: red;">목록 로드 실패: ${result.error}</span>`;
            }
        });
    });

    document.getElementById('btn_generate_imageset').addEventListener('click', async () => {
        const outputBox = document.getElementById('output_generate_imageset');
        const selectedVersion = ocpVersionSelect.value.split('.').slice(0, 2).join('.');
        const registryUrl = document.getElementById('registry_url').value;

        if (!registryUrl) {
            alert('Registry 주소를 입력해주세요.');
            return;
        }

        const configData = {
            registry: registryUrl,
            version: selectedVersion,
            operators: []
        };

        document.querySelectorAll('.operator-catalog').forEach(catalogDiv => {
            const checkbox = catalogDiv.querySelector('input[type="checkbox"]');
            if (checkbox.checked) {
                const catalogId = checkbox.dataset.catalog;
                const catalog = {
                    catalog: `registry.redhat.io/redhat/${catalogId}:v${selectedVersion}`,
                    packages: []
                };

                catalogDiv.querySelectorAll('.operator-list input[type="checkbox"]:checked').forEach(opCheckbox => {
                    catalog.packages.push({
                        name: opCheckbox.dataset.name,
                        channels: [{ name: opCheckbox.dataset.channel }]
                    });
                });

                if (catalog.packages.length > 0) {
                    configData.operators.push(catalog);
                }
            }
        });
        
        showLoading(outputBox);
        const result = await callApi('/api/generate-imageset', configData);
        showResult(outputBox, result);
    });

    document.getElementById('btn_run_mirror').addEventListener('click', async () => {
        const outputBox = document.getElementById('output_run_mirror');
        showLoading(outputBox);
        const result = await callApi('/api/run-mirror', {});
        showResult(outputBox, result);
    });

    // --- Initial Load ---
    fetchOcpVersions();
});
