# 激活虚拟环境
. ".\.venv\Scripts\Activate.ps1"

# 安装打包工具
pip install pyinstaller

# 清理旧构建
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# 打包（使用 spec 文件以确保依赖完整）
pyinstaller ledger.spec

Write-Host "构建完成，输出在 dist\ 目录"
