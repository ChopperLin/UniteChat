"""工具函数"""
from datetime import datetime


def format_timestamp(timestamp: float) -> str:
    """
    格式化时间戳
    
    Args:
        timestamp: Unix 时间戳
        
    Returns:
        格式化的时间字符串
    """
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def truncate_text(text: str, max_length: int = 100) -> str:
    """
    截断文本
    
    Args:
        text: 原始文本
        max_length: 最大长度
        
    Returns:
        截断后的文本
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + '...'
