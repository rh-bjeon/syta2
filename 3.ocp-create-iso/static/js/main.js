document.addEventListener('DOMContentLoaded', () => {

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

    const showResult = (outputBox, result, actionType) => {
        const copyBtn = document.querySelector(`.copy-btn[data-target='${outputBox.id}']`);

        if (result.success) {
            // [수정] 서버가 is_command 플래그를 보내면 명령어 표시 UI로 전환
            if (result.is_command) {
                outputBox.style.color = 'inherit'; // 기본 텍스트 색상
                outputBox.innerHTML = `<div class="warning-text">${result.message}</div><pre class="command-to-copy">${result.output}</pre>`;
                if (copyBtn) copyBtn.style.display = 'inline-block';
            } else {
                outputBox.style.color = 'green';
                outputBox.textContent = '✅ 성공!\n' + (result.output || result.message || '');
                if (copyBtn) copyBtn.style.display = 'none';
            }
        } else {
            outputBox.style.color = 'red';
            outputBox.textContent = '❌ 실패!\n' + (result.output || result.error || '알 수 없는 오류');
            if (copyBtn) copyBtn.style.display = 'none';
        }
    };

    // Section 1: CSV Upload
    document.getElementById('upload-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const outputBox = document.getElementById('output-upload');
        outputBox.textContent = '업로드 중...';
        
        const formData = new FormData(e.target);
        const response = await fetch('/upload-csv', {
            method: 'POST',
            body: formData,
        });
        const result = await response.json();
        showResult(outputBox, result, 'upload');
    });

    // Section 2, 3, 5, 6: Button Actions
    document.querySelectorAll('button[data-action-type]').forEach(button => {
        button.addEventListener('click', async () => {
            const actionType = button.dataset.actionType;
            const outputBox = document.getElementById(`output-${actionType}`);
            outputBox.textContent = '명령 실행 중...';

            const result = await callApi('/api/execute-action', { type: actionType });
            
            if (actionType === 'get_ca_cert' && result.success) {
                document.getElementById('ca_cert_textbox').value = result.output;
            }
            
            showResult(outputBox, result, actionType);
        });
    });

    // [신규] 모든 복사하기 버튼에 대한 이벤트 리스너
    document.querySelectorAll('.copy-btn').forEach(button => {
        button.addEventListener('click', () => {
            const targetId = button.dataset.target;
            const outputBox = document.getElementById(targetId);
            const commandPre = outputBox.querySelector('.command-to-copy');
            if (commandPre) {
                const tempTextArea = document.createElement('textarea');
                tempTextArea.value = commandPre.innerText;
                document.body.appendChild(tempTextArea);
                tempTextArea.select();
                document.execCommand('copy');
                document.body.removeChild(tempTextArea);
                alert('명령어가 클립보드에 복사되었습니다.');
            }
        });
    });

    // CA 인증서 복사 버튼
    const copyCaBtn = document.getElementById('btn_copy_ca');
    if (copyCaBtn) {
        copyCaBtn.addEventListener('click', () => {
            const textbox = document.getElementById('ca_cert_textbox');
            textbox.select();
            document.execCommand('copy');
            alert('CA 인증서가 클립보드에 복사되었습니다.');
        });
    }
});
