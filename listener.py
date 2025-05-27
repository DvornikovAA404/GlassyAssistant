# Для работы необходим брайзер Firefox. Нужно добавить manifest.json в качестве временного дополнения на about:debugging и вручную запустить скрипт.

from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time

app = Flask(__name__)
CORS(app)

URL_STORAGE = None

def save_url_to_file(url):
    """Записывает URL в `url.txt` при каждом обновлении"""
    with open("url.txt", "w", encoding="utf-8") as f:
        f.write(url)
    print("✅ URL сохранён в `url.txt`:", url)

@app.route("/save_url", methods=["POST"])
def save_url():
    """Сохраняет переданный URL и записывает в файл"""
    global URL_STORAGE
    data = request.json
    url = data.get("url", "")

    if url:
        URL_STORAGE = url
        save_url_to_file(url)
        return jsonify({"status": "success", "url": URL_STORAGE}), 200

    return jsonify({"error": "Нет URL"}), 400

@app.route("/get_url", methods=["GET"])
def get_url():
    """Возвращает сохранённый URL"""
    print(f"🔍 Запрос GET /get_url → URL_STORAGE: {URL_STORAGE}")
    return jsonify({"url": URL_STORAGE}) if URL_STORAGE else jsonify({"error": "URL не найден"}), 404

def auto_update_url():
    """Фоновое обновление URL раз в 2 секунды"""
    global URL_STORAGE
    while True:
        if URL_STORAGE:
            print(f"🔄 Автообновление URL: {URL_STORAGE}")
        else:
            print("❌ URL ещё не сохранён")
        time.sleep(2)

threading.Thread(target=auto_update_url, daemon=True).start()

if __name__ == "__main__":
    app.run(host="localhost", port=5000)
