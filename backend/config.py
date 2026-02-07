"""配置管理"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent
BACKEND_DIR = Path(__file__).parent

# 数据根目录（包含所有聊天记录文件夹）
DATA_ROOT = BASE_DIR / "data"

# 数据源配置文件（用户可在设置中修改）
DATA_SOURCE_CONFIG_PATH = BASE_DIR / "data_sources.json"

# Flask 配置
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    DEBUG = True
    
    # CORS 配置
    CORS_HEADERS = 'Content-Type'
    
    # 数据根路径
    DATA_ROOT_PATH = DATA_ROOT
    DATA_SOURCE_CONFIG_FILE = DATA_SOURCE_CONFIG_PATH
    BASE_DIR_PATH = BASE_DIR
    BACKEND_DIR_PATH = BACKEND_DIR
