@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "LOG_FILE=%~dp0setup.log"
echo ======================================== > "%LOG_FILE%"
echo   GPT Chat Browser 环境配置脚本日志 >> "%LOG_FILE%"
echo   %DATE% %TIME% >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"

echo ========================================
echo   GPT Chat Browser 环境配置脚本
echo ========================================
echo.

echo [1/4] 检查 Python 环境...
echo [1/4] 检查 Python 环境... >> "%LOG_FILE%"
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: 未找到 Python，请先安装 Python 3.8+ >> "%LOG_FILE%"
    echo ❌ 错误: 未找到 Python，请先安装 Python 3.8+
    echo    下载地址: https://www.python.org/downloads/ >> "%LOG_FILE%"
    echo    下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VER=%%i
echo !PYTHON_VER! >> "%LOG_FILE%"
echo !PYTHON_VER!
echo.

echo [2/4] 创建并配置 Python 虚拟环境...
echo [2/4] 创建并配置 Python 虚拟环境... >> "%LOG_FILE%"
cd /d %~dp0backend
if exist venv (
    echo   虚拟环境已存在，跳过创建 >> "%LOG_FILE%"
    echo   虚拟环境已存在，跳过创建
) else (
    echo   正在创建虚拟环境... >> "%LOG_FILE%"
    echo   正在创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ❌ 错误: 虚拟环境创建失败 >> "%LOG_FILE%"
        echo ❌ 错误: 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo   ✓ 虚拟环境创建成功 >> "%LOG_FILE%"
    echo   ✓ 虚拟环境创建成功
)
echo.

echo   正在安装 Python 依赖...
echo   正在安装 Python 依赖... >> "%LOG_FILE%"
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo ❌ 错误: 无法激活虚拟环境 >> "%LOG_FILE%"
    echo ❌ 错误: 无法激活虚拟环境
    pause
    exit /b 1
)
pip install -r requirements.txt >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: Python 依赖安装失败 >> "%LOG_FILE%"
    echo ❌ 错误: Python 依赖安装失败
    pause
    exit /b 1
)
echo   ✓ Python 依赖安装完成 >> "%LOG_FILE%"
echo   ✓ Python 依赖安装完成
call venv\Scripts\deactivate.bat
cd /d %~dp0
echo.

echo [3/4] 检查 Node.js 环境...
echo [3/4] 检查 Node.js 环境... >> "%LOG_FILE%"
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: 未找到 Node.js，请先安装 Node.js 18+ >> "%LOG_FILE%"
    echo ❌ 错误: 未找到 Node.js，请先安装 Node.js 18+
    echo    下载地址: https://nodejs.org/ >> "%LOG_FILE%"
    echo    下载地址: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do set NODE_VER=%%i
for /f "tokens=*" %%i in ('npm --version') do set NPM_VER=%%i
echo !NODE_VER! >> "%LOG_FILE%"
echo !NPM_VER! >> "%LOG_FILE%"
echo !NODE_VER!
echo !NPM_VER!
echo.

echo [4/4] 安装前端依赖...
echo [4/4] 安装前端依赖... >> "%LOG_FILE%"
cd /d %~dp0frontend
if not exist "package.json" (
    echo ❌ 错误: package.json 不存在 >> "%LOG_FILE%"
    echo ❌ 错误: package.json 不存在
    pause
    exit /b 1
)
echo   正在安装 Node.js 依赖（可能需要几分钟）... >> "%LOG_FILE%"
echo   正在安装 Node.js 依赖（可能需要几分钟）...
npm cache clean --force >> "%LOG_FILE%" 2>&1
call npm install >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo   第一次安装失败，重试中... >> "%LOG_FILE%"
    echo   第一次安装失败，重试中...
    timeout /t 5 /nobreak >nul
    call npm install >> "%LOG_FILE%" 2>&1
    if %errorlevel% neq 0 (
        echo ❌ 错误: 前端依赖安装失败 >> "%LOG_FILE%"
        echo ❌ 错误: 前端依赖安装失败
        echo   请检查日志文件: %LOG_FILE% >> "%LOG_FILE%"
        echo   请检查日志文件: %LOG_FILE%
        pause
        exit /b 1
    )
)
echo   ✓ 前端依赖安装完成 >> "%LOG_FILE%"
echo   ✓ 前端依赖安装完成
cd /d %~dp0
echo.

echo ======================================== >> "%LOG_FILE%"
echo   ✓ 环境配置完成！ >> "%LOG_FILE%"
echo ========================================
echo ========================================
echo   ✓ 环境配置完成！
echo ========================================
echo.
echo   下一步:
echo   - 运行 start.bat 启动项目
echo   - 或手动启动后端: cd backend ^&^& venv\Scripts\python run.py
echo   - 或手动启动前端: cd frontend ^&^& npm run dev
echo.
echo ========================================
echo   日志文件: %LOG_FILE%
pause
