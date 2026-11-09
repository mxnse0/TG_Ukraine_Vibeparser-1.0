# Builds dist\VibeParser.exe (Windows, one file).
# Usage:  powershell -ExecutionPolicy Bypass -File .\build_exe.ps1

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "❌ Не знайдено .venv. Спочатку створи середовище:" -ForegroundColor Red
    Write-Host "   python -m venv .venv"
    Write-Host "   .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt"
    exit 1
}

Write-Host "📦 Встановлюю залежності для збірки…" -ForegroundColor Cyan
& $python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('pip') else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "   pip відсутній у .venv — встановлюю через ensurepip…"
    & $python -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw "ensurepip failed" }
}
& $python -m pip install --disable-pip-version-check -r requirements.txt -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "🎨 Генерую іконку…" -ForegroundColor Cyan
& $python scripts\build_icon.py
if ($LASTEXITCODE -ne 0) { throw "icon generation failed" }

Write-Host "🔨 Збираю VibeParser.exe (це може зайняти 1–3 хвилини)…" -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm --clean VibeParser.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Copy-Item -LiteralPath ".env.example" -Destination "dist\.env.example" -Force
Copy-Item -LiteralPath "packaging\EXE-README.txt" -Destination "dist\README.txt" -Force

$exe = Join-Path $PSScriptRoot "dist\VibeParser.exe"
$sizeMb = [math]::Round((Get-Item -LiteralPath $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "✅ Готово: $exe ($sizeMb МБ)" -ForegroundColor Green
Write-Host "   Поклади .env поруч з exe (або запусти exe — він створить шаблон сам)."
