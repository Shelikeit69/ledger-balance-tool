.\.venv\Scripts\Activate.ps1

if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

python -m PyInstaller `
    --onefile `
    --windowed `
    --name "LedgerBalanceTool" `
    --add-data "src;src" `
    --paths "src" `
    --collect-all PySide6 `
    main.py

Write-Host "构建完成，输出在 dist\LedgerBalanceTool.exe"
