param(
  [string]$OutDir = "dist-portable"
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements.txt | Out-Null
python -m pip install pyinstaller | Out-Null

# Build app exe
pyinstaller --noconfirm --clean --onefile --name platform_scrapper app_entry.py

# Build launcher exe (use onedir to avoid embedded-python issues)
pyinstaller --noconfirm --clean --onedir --name Launcher launcher.py

# Prepare portable folder (clean contents but keep root to avoid lock errors)
if (Test-Path $OutDir) { Remove-Item -Recurse -Force (Join-Path $OutDir "*") }
else { New-Item -ItemType Directory -Path $OutDir | Out-Null }
New-Item -ItemType Directory -Path (Join-Path $OutDir "app") | Out-Null

# Copy full launcher onedir (Launcher.exe + its Python runtime)
Copy-Item ".\dist\Launcher\*" $OutDir -Recurse
Copy-Item ".\dist\platform_scrapper.exe" (Join-Path $OutDir "app\platform_scrapper.exe")

# Ship required runtime files alongside the app (so it can run from any folder)
Copy-Item ".\server.py" (Join-Path $OutDir "app\server.py")
Copy-Item ".\main.py" (Join-Path $OutDir "app\main.py")
Copy-Item ".\config.py" (Join-Path $OutDir "app\config.py")
Copy-Item ".\scraper.py" (Join-Path $OutDir "app\scraper.py")
Copy-Item ".\scraper_browser.py" (Join-Path $OutDir "app\scraper_browser.py")
Copy-Item ".\scraper_x.py" (Join-Path $OutDir "app\scraper_x.py")
Copy-Item ".\scraper_reddit.py" (Join-Path $OutDir "app\scraper_reddit.py")
Copy-Item ".\scraper_google_trends.py" (Join-Path $OutDir "app\scraper_google_trends.py")
Copy-Item ".\scraper_youtube.py" (Join-Path $OutDir "app\scraper_youtube.py")
Copy-Item ".\browser_auth.py" (Join-Path $OutDir "app\browser_auth.py")
Copy-Item ".\app_version.py" (Join-Path $OutDir "app\app_version.py")
Copy-Item ".\requirements.txt" (Join-Path $OutDir "app\requirements.txt")

Write-Host "Built portable package at $OutDir"

