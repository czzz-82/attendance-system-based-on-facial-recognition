"""启动入口：python run.py"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # 0.0.0.0 允许局域网访问；浏览器调用摄像头需要 https 或 localhost
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
