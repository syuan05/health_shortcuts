from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
import json
import cloudinary
import cloudinary.uploader
import os

app = Flask(__name__)
# 允許跨域請求，讓你的網頁（前端）可以呼叫這個 API
CORS(app)

# --- 配置資訊 (從 Render 環境變數讀取) ---
db_config = {
    'host': os.environ.get('DB_HOST'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'database': 'defaultdb',
    'port': 19281,
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
    secure = True
)

# --- 1. 系統診斷路由 ---
@app.route('/health', methods=['GET'])
def health():
    """ 用於前端狀態燈檢查 Render 狀態 """
    return jsonify({"status": "ok", "db": "connected"}), 200

@app.route('/test', methods=['GET'])
def test_db():
    """ 手動測試資料庫連線是否正常 """
    try:
        conn = pymysql.connect(**db_config)
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
        conn.close()
        return jsonify({"status": "連線成功", "mysql_version": version})
    except Exception as e:
        return jsonify({"status": "連線失敗", "error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_image():
    """ 安全上傳：由後端代理將圖片傳至 Cloudinary """
    try:
        data = request.json
        image_data = data.get('image') 
        
        if not image_data:
            return jsonify({"status": "error", "message": "無圖片數據"}), 400

        # 上傳到 Cloudinary 並指定資料夾
        upload_result = cloudinary.uploader.upload(
            image_data,
            folder="health_app_photos",
            resource_type="image"
        )

        return jsonify({
            "status": "success",
            "url": upload_result.get("secure_url") # 回傳 https 網址
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- 3. 數據讀取路由 ---
@app.route('/get_record', methods=['GET'])
def get_record():
    """ 依據日期抓取雲端紀錄 """
    date = request.args.get('date')
    if not date:
        return jsonify({"status": "error", "message": "Missing date"}), 400
    
    conn = None
    try:
        conn = pymysql.connect(**db_config)
        with conn.cursor() as cursor:
            sql = "SELECT raw_json FROM daily_records WHERE record_date = %s"
            cursor.execute(sql, (date,))
            result = cursor.fetchone()
        
        if result and result.get('raw_json'):
            return jsonify({
                "status": "success", 
                "data": json.loads(result['raw_json'])
            })
        else:
            return jsonify({"status": "empty", "message": "No record found"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            conn.close()



@app.route('/save', methods=['POST'])
def save_data():
    """ 儲存數據：現在 JSON 內的 img 欄位存的是 URL 字串 """
    data = request.json
    try:
        conn = pymysql.connect(**db_config)
        with conn.cursor() as cursor:
            # Aiven 資料庫中 raw_json 建議使用 TEXT 或 LONGTEXT
            sql = """
            INSERT INTO daily_records (
                record_date, water_intake, steps, exercise_status, 
                stress_level, fatigue_level, poop_level, 
                edema_level, fullness_level, evil_food, raw_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                water_intake=VALUES(water_intake), steps=VALUES(steps),
                raw_json=VALUES(raw_json)
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
                json.dumps(data) # 這裡存入的是包含 Cloudinary 網址的 JSON
            ))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "數據已備份至雲端！"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)