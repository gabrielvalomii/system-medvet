# Sobe back (Django :8000) e front (Express :3000) no mesmo terminal.
# Uso (na raiz do projeto):  .\dev.ps1
# Ctrl+C encerra os dois.

$root = $PSScriptRoot
$python = Join-Path $root "back\venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "venv nao encontrado em back\venv. Crie com: cd back; python -m venv venv" -ForegroundColor Red
    exit 1
}

Write-Host "Subindo back em http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$back = Start-Process -FilePath $python `
    -ArgumentList "manage.py", "runserver", "127.0.0.1:8000" `
    -WorkingDirectory (Join-Path $root "back") `
    -NoNewWindow -PassThru

try {
    Write-Host "Subindo front em http://localhost:3000 ... (Ctrl+C para parar os dois)" -ForegroundColor Cyan
    Push-Location (Join-Path $root "front")
    npm run dev
}
finally {
    Pop-Location
    Write-Host "Encerrando back..." -ForegroundColor Yellow
    # /T encerra tambem o processo filho do runserver (autoreload)
    taskkill /PID $back.Id /T /F | Out-Null
}
