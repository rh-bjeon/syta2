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

    // Section 2: Bastion Configuration
    document.querySelectorAll('button[data-config-type]').forEach(button => {
        button.addEventListener('click', async () => {
            const configType = button.dataset.configType;
            const outputBox = document.getElementById(`output-${configType}`);
            outputBox.textContent = '명령 실행 중...';

            const result = await callApi('/api/configure', { type: configType });
            showResult(outputBox, result);
        });
    });
});
