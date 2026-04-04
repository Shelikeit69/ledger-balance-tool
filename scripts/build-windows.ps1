# 激活虚拟环境
. ".\.venv\Scripts\Activate.ps1"

# 安装打包工具
pip install pyinstaller

# 清理旧构建
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# 打包
pyinstaller `
    --onefile `
    --windowed `
    --name "账目配平工具" `
    --add-data "src;src" `
    --paths "src" `
    src\ledger\ui\main_window.py

Write-Host "构建完成，输出在 dist\ 目录"
