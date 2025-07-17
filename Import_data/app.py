from flask import Flask, render_template, request, jsonify
import pandas as pd

app = Flask(__name__)

@app.route('/')
def index():
    # index.html 페이지만 렌더링합니다.
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """엑셀 파일 업로드를 처리하는 API 엔드포인트입니다."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        try:
            # Pandas를 사용하여 업로드된 엑셀 파일을 읽습니다.
            # .xlsx 파일을 읽기 위해 openpyxl 엔진이 필요합니다.
            df = pd.read_excel(file, engine='openpyxl')
            
            # DataFrame을 key-value 형태의 JSON 배열로 변환합니다.
            data = df.to_dict(orient='records')
            
            # JSON 데이터를 클라이언트에게 반환합니다.
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
            
    return '', 204


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5012, debug=True)
