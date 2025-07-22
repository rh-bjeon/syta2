document.addEventListener('DOMContentLoaded', () => {
    const ocpVersionSelect = document.getElementById('ocp_version_select');
    let allFetchedVersions = []; // 전체 버전 목록 저장

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
            const text = await response.text();
            try {
                return JSON.parse(text);
            } catch (e) {
                return { success: false, error: `서버 응답이 유효한 JSON이 아닙니다:\n${text}` };
            }
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
                allFetchedVersions = data.versions; // 전체 버전 저장
                ocpVersionSelect.innerHTML = '';
                allFetchedVersions.forEach(version => {
                    const option = new Option(version, version);
                    ocpVersionSelect.add(option);
                });
                // 초기 로드 후 첫 번째 버전에 대해 마이너 버전 목록 업데이트
                updateMinorVersionDropdowns();
            } else {
                ocpVersionSelect.innerHTML = `<option>버전 로드 실패: ${data.error}</option>`;
            }
        } catch (error) {
            ocpVersionSelect.innerHTML = `<option>API 오류: ${error.message}</option>`;
        }
    };

    document.getElementById('btn_fetch_versions').addEventListener('click', fetchOcpVersions);
    // 메인 버전 선택 시 마이너 버전 드롭다운 업데이트
    ocpVersionSelect.addEventListener('change', updateMinorVersionDropdowns);

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
    document.getElementById('btn_apply_pull_secret').addEventListener('click', async () => {
        const pullSecretInput = document.getElementById('pull_secret_input');
        const outputBox = document.getElementById('output_apply_pull_secret');
        const pullSecretContent = pullSecretInput.value.trim();
        if (!pullSecretContent) {
            alert('Pull Secret 내용을 입력해주세요.');
            return;
        }
        showLoading(outputBox);
        const result = await callApi('/api/apply-pull-secret', {
            pull_secret: pullSecretContent
        });
        showResult(outputBox, result);
    });

    // 마이너 버전 드롭다운을 채우는 함수
    function updateMinorVersionDropdowns() {
        const selectedVersion = ocpVersionSelect.value;
        if (!selectedVersion) return;

        const majorVersion = selectedVersion.split('.').slice(0, 2).join('.');
        document.getElementById('major_version_display').value = majorVersion;

        const minorVersions = allFetchedVersions.filter(v => v.startsWith(majorVersion));
        
        const minSelect = document.getElementById('min_version_select');
        const maxSelect = document.getElementById('max_version_select');
        minSelect.innerHTML = '';
        maxSelect.innerHTML = '';

        minorVersions.forEach(version => {
            minSelect.add(new Option(version, version));
            maxSelect.add(new Option(version, version));
        });
    }

    document.querySelectorAll('.btn-list-operators').forEach(button => {
        button.addEventListener('click', async () => {
            const catalog = button.dataset.catalog;
            const listDiv = document.getElementById(`list_${catalog}`);
            const selectedVersion = ocpVersionSelect.value;
            const pullSecretStatus = document.getElementById('output_apply_pull_secret').textContent;
            
            // [수정] Marketplace 버튼 버그 수정 (더 안정적인 DOM 탐색)
            const catalogContainer = button.closest('.operator-catalog');
            const checkbox = catalogContainer.querySelector('input[type="checkbox"]');

            if (!pullSecretStatus.includes('성공적으로 적용되었습니다')) {
                alert('먼저 Pull Secret을 입력하고 "적용" 버튼을 눌러주세요.');
                return;
            }
            if (!checkbox || !checkbox.checked) {
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
                version: selectedVersion.split('.').slice(0, 2).join('.'),
            });
            
            if (result.success) {
                listDiv.innerHTML = '';
                result.operators.forEach(opName => {
                    const checkboxId = `op-${catalog}-${opName}`;
                    const item = document.createElement('div');
                    item.className = 'operator-item';
                    item.innerHTML = `<input type="checkbox" id="${checkboxId}" data-name="${opName}"><label for="${checkboxId}">${opName}</label>`;
                    listDiv.appendChild(item);
                });
            } else {
                listDiv.innerHTML = `<span style="color: red;">목록 로드 실패: ${result.error}</span>`;
            }
        });
    });

    document.getElementById('btn_generate_imageset').addEventListener('click', async () => {
        const outputBox = document.getElementById('output_generate_imageset');
        const majorVersion = document.getElementById('major_version_display').value;
        const minVersion = document.getElementById('min_version_select').value;
        const maxVersion = document.getElementById('max_version_select').value;

        if (!majorVersion || !minVersion || !maxVersion) {
            alert('버전 정보를 선택해주세요.');
            return;
        }

        const configData = {
            majorVersion: majorVersion,
            minVersion: minVersion,
            maxVersion: maxVersion,
            operators: []
        };
        document.querySelectorAll('.operator-catalog').forEach(catalogDiv => {
            const checkbox = catalogDiv.querySelector('input[type="checkbox"]');
            if (checkbox.checked) {
                const catalogId = checkbox.dataset.catalog;
                const catalog = {
                    catalog: `registry.redhat.io/redhat/${catalogId}:v${majorVersion}`,
                    packages: []
                };
                
                catalogDiv.querySelectorAll('.operator-list input[type="checkbox"]:checked').forEach(opCheckbox => {
                    catalog.packages.push({
                        name: opCheckbox.dataset.name
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
