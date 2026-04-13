from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
import json
import os  # <--- 這裡一定要加！

app = Flask(__name__)
CORS(app)

# Aiven MySQL 連線資訊 (從環境變數讀取)
db_config = {
    'host': os.environ.get('DB_HOST'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'database': 'defaultdb',
    'port': 19281,
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

@app.route('/test', methods=['GET'])
def test_db():
    try:
        conn = pymysql.connect(**db_config)
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
        conn.close()
        return jsonify({"status": "連線成功", "mysql_version": version})
    except Exception as e:
        return jsonify({"status": "連線失敗", "error": str(e)}), 500

@app.route('/save', methods=['POST'])
def save_data():
    data = request.json
    try:
        conn = pymysql.connect(**db_config)
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO daily_records (record_date, water_intake, steps, exercise_status, stress_level, raw_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                data.get('date'),
                data.get('water', 0),
                data.get('steps', 0),
                data.get('isExercise', '否'),
                data.get('stress', 0),
                json.dumps(data)
            ))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "資料已存入 Aiven 雲端！"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Render 會自動給 PORT 環境變數
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)