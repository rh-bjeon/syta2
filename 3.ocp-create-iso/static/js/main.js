// static/js/main.js
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

    const showResult = (outputBox, result) => {
        if (result.success) {
            outputBox.style.color = 'green';
            outputBox.textContent = '✅ 성공!\n' + (result.output || result.message || '');
        } else {
            outputBox.style.color = 'red';
            outputBox.textContent = '❌ 실패!\n' + (result.output || result.error || '알 수 없는 오류');
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
        showResult(outputBox, result);
    });

    // Section 2, 3, 5, 6: Button Actions
    document.querySelectorAll('button[data-action-type]').forEach(button => {
        button.addEventListener('click', async () => {
            const actionType = button.dataset.actionType;
            const outputBox = document.getElementById(`output-${actionType}`);
            outputBox.textContent = '명령 실행 중...';

            const result = await callApi('/api/execute-action', { type: actionType });
            
            // CA 인증서 가져오기 특별 처리
            if (actionType === 'get_ca_cert' && result.success) {
                document.getElementById('ca_cert_textbox').value = result.output;
            }
            
            showResult(outputBox, result);
        });
    });

    // 클립보드 복사 버튼
    const copyBtn = document.getElementById('btn_copy_ca');
    if (copyBtn) {
        copyBtn.addEventListener('click', () => {
            const textbox = document.getElementById('ca_cert_textbox');
            textbox.select();
            document.execCommand('copy');
            alert('CA 인증서가 클립보드에 복사되었습니다.');
        });
    }
});
