"""配置管理"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

# 数据根目录（包含所有聊天记录文件夹）
DATA_ROOT = BASE_DIR / "data"

# Flask 配置
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    DEBUG = True
    
    # CORS 配置
    CORS_HEADERS = 'Content-Type'
    
    # 数据根路径
    DATA_ROOT_PATH = DATA_ROOT
