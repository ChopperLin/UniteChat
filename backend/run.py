"""应用启动入口"""
import os
import sys

from app import create_app
from config import Config

app = create_app()


def _get_host_port() -> tuple[str, int]:
    # Windows 上部分环境/安全策略可能禁止绑定到 0.0.0.0，默认仅监听本机更稳妥。
    host = (os.environ.get('BACKEND_HOST') or '127.0.0.1').strip()
    port_raw = (os.environ.get('BACKEND_PORT') or '5000').strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 5000
    return host, port


if __name__ == '__main__':
    host, port = _get_host_port()

    print("🚀 启动 UniteChat 后端...")
    print("🐍 Python:", sys.executable)
    print("🐍 Version:", sys.version.split()[0])
    print("📂 数据根目录:", Config.DATA_ROOT_PATH)
    print(f"🌐 访问地址: http://{host}:{port}")
    print("")

    try:
        app.run(host=host, port=port, debug=True, use_reloader=False)
    except OSError as e:
        print("\n❌ 后端启动失败: 监听端口失败")
        print(f"   host={host} port={port}")
        print(f"   OSError: {e}")
        print("\n可尝试：")
        print("- 修改 BACKEND_HOST=127.0.0.1（默认已是）")
        print("- 修改 BACKEND_PORT 为未被占用/未被策略拦截的端口（如 5001）")
        raise
