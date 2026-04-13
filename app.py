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
@app.route('/save', methods=['POST'])
def save_data():
    data = request.json
    try:
        conn = pymysql.connect(**db_config)
        with conn.cursor() as cursor:
            # 使用 ON DUPLICATE KEY UPDATE，如果日期重複就更新舊資料
            sql = """
            INSERT INTO daily_records (
                record_date, water_intake, steps, exercise_status, 
                stress_level, fatigue_level, poop_level, 
                edema_level, fullness_level, evil_food, raw_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                water_intake=VALUES(water_intake), steps=VALUES(steps),
                exercise_status=VALUES(exercise_status), stress_level=VALUES(stress_level),
                fatigue_level=VALUES(fatigue_level), poop_level=VALUES(poop_level),
                edema_level=VALUES(edema_level), fullness_level=VALUES(fullness_level),
                evil_food=VALUES(evil_food), raw_json=VALUES(raw_json)
            """
            cursor.execute(sql, (
                data.get('date'),
                data.get('water') or 0,
                data.get('steps') or 0,
                data.get('isExercise', '否'),
                data.get('stress') or 0,
                data.get('fatigue') or 0,
                data.get('poop') or 0,
                data.get('edema') or 0,
                data.get('fullness') or 0,
                data.get('evil', '否'),
                json.dumps(data)
            ))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "完整數據已同步至 Aiven 雲端！"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Render 會自動給 PORT 環境變數
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)