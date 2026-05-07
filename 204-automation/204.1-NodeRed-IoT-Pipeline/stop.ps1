# stop.ps1 · Para todo el entorno de práctica Node-RED IoT
# Ejecutar desde la raiz del proyecto: .\stop.ps1

Write-Host ""
Write-Host "Parando entorno POC Node-RED IoT..." -ForegroundColor Yellow

# Parar Node-RED y OPC UA (procesos node)
Write-Host "Parando Node-RED y OPC UA simulado..."
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "    OK" -ForegroundColor Green

# Parar contenedores Docker
Write-Host "Parando Mosquitto..."
docker stop mosquitto | Out-Null
Write-Host "    OK" -ForegroundColor Green

Write-Host "Parando Uptime Kuma..."
docker stop uptime-kuma | Out-Null
Write-Host "    OK" -ForegroundColor Green

Write-Host ""
Write-Host "Todo parado correctamente." -ForegroundColor Cyan
Write-Host ""
