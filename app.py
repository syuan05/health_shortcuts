from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import cloudinary
import cloudinary.uploader
import os
import uuid

app = Flask(__name__)
CORS(app)

# --- 配置資訊 (從 Render 環境變數讀取) ---
def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        dbname=os.environ.get('DB_NAME', 'neondb'), # 若用 Aiven 預設通常是 defaultdb
        port=os.environ.get('DB_PORT', 5432),
        sslmode='require', # 雲端 PostgreSQL (Neon / Aiven) 皆需 SSL
        cursor_factory=RealDictCursor
    )

cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
    secure = True
)

# --- 1. 系統診斷路由 ---
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Flask is running"}), 200

@app.route('/db_health', methods=['GET'])
def db_health():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        return jsonify({"status": "success", "message": "Database connected"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/test', methods=['GET'])
def test_db():
    return jsonify({"status": "ok", "message": "Redirected test endpoint"}), 200

# --- 2. 圖片上傳路由 ---
@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        data = request.json
        image_data = data.get('image') 
        
        if not image_data:
            return jsonify({"status": "error", "message": "無圖片數據"}), 400

        upload_result = cloudinary.uploader.upload(
            image_data,
            folder="health_app_photos",
            resource_type="image"
        )

        return jsonify({
            "status": "success",
            "url": upload_result.get("secure_url")
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- 3. 數據讀取路由 ---
@app.route('/get_record', methods=['GET'])
def get_record():
    date = request.args.get('date')
    if not date:
        return jsonify({"status": "error", "message": "Missing date"}), 400
    
    conn = None
    try:
        conn = get_db_connection()
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

# --- 4. 數據刪除路由 ---
@app.route('/delete', methods=['POST'])
def delete_record():
    data = request.json
    date = data.get('date')
    if not date:
        return jsonify({"status": "error", "message": "缺少日期參數"}), 400
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "DELETE FROM daily_records WHERE record_date = %s"
            cursor.execute(sql, (date,))
        conn.commit()
        return jsonify({"status": "success", "message": f"日期 {date} 的雲端資料已刪除"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            conn.close()    

# --- 5. 批次匯出路由 ---
def ensure_export_batch_table(conn):
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS export_batches (
                token VARCHAR(64) PRIMARY KEY,
                images_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()

@app.route('/create_export_batch', methods=['POST'])
def create_export_batch():
    data = request.json or {}
    images = data.get('images') or []
    if not images:
        return jsonify({'status':'error','message':'沒有圖片'}), 400
    token = uuid.uuid4().hex
    conn = None
    try:
        conn = get_db_connection()
        ensure_export_batch_table(conn)
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM export_batches WHERE created_at < NOW() - INTERVAL '2 days'")
            cursor.execute("INSERT INTO export_batches (token, images_json) VALUES (%s,%s)",
                           (token, json.dumps(images, ensure_ascii=False)))
        conn.commit()
        manifest_url = request.host_url.rstrip('/') + '/export_batch/' + token
        return jsonify({'status':'success','token':token,'manifest_url':manifest_url,'count':len(images)})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/export_batch/<token>', methods=['GET'])
def export_batch(token):
    conn = None
    try:
        conn = get_db_connection()
        ensure_export_batch_table(conn)
        with conn.cursor() as cursor:
            cursor.execute("SELECT images_json FROM export_batches WHERE token=%s", (token,))
            row = cursor.fetchone()
        if not row:
            return jsonify({'status':'error','message':'批次不存在或已過期'}), 404
        return jsonify({'status':'success','images':json.loads(row['images_json'])})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 500
    finally:
        if conn:
            conn.close()

# --- 6. 儲存數據路由 ---
@app.route('/save', methods=['POST'])
def save_data():
    data = request.json
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO daily_records (
                record_date, water_intake, steps, exercise_status, 
                stress_level, fatigue_level, poop_level, 
                edema_level, fullness_level, evil_food, raw_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (record_date) DO UPDATE SET 
                water_intake = EXCLUDED.water_intake,
                steps = EXCLUDED.steps,
                exercise_status = EXCLUDED.exercise_status,
                stress_level = EXCLUDED.stress_level,
                fatigue_level = EXCLUDED.fatigue_level,
                poop_level = EXCLUDED.poop_level,
                edema_level = EXCLUDED.edema_level,
                fullness_level = EXCLUDED.fullness_level,
                evil_food = EXCLUDED.evil_food,
                raw_json = EXCLUDED.raw_json
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
                json.dumps(data, ensure_ascii=False)
            ))
        conn.commit()
        return jsonify({"status": "success", "message": "數據已備份至雲端！"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)