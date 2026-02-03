"""Flask 应用初始化"""
from flask import Flask
from flask_cors import CORS
from config import Config

def create_app(config_class=Config):
    """应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 启用 CORS
    CORS(app)
    
    # 注册路由
    from app.routes import api
    app.register_blueprint(api, url_prefix='/api')
    
    return app
