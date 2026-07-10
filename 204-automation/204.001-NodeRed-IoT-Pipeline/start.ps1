# start.ps1 · Arranca todo el entorno de práctica Node-RED IoT
# Ejecutar desde la raiz del proyecto: .\start.ps1

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  POC Node-RED IoT Pipeline · Fase 1   " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Mosquitto
Write-Host "[1/4] Arrancando Mosquitto MQTT..." -ForegroundColor Yellow
$mosquitto = docker ps -a --filter "name=mosquitto" --format "{{.Names}}"
if ($mosquitto -eq "mosquitto") {
    docker start mosquitto | Out-Null
} else {
    $confPath = (Resolve-Path ".\mosquitto\mosquitto.conf").Path -replace '\\', '/'
    docker run -d --name mosquitto -p 1883:1883 -v "${confPath}:/mosquitto/config/mosquitto.conf" eclipse-mosquitto | Out-Null
}
Write-Host "    OK · Mosquitto en localhost:1883" -ForegroundColor Green

# 2. Uptime Kuma
Write-Host "[2/4] Arrancando Uptime Kuma..." -ForegroundColor Yellow
$kuma = docker ps -a --filter "name=uptime-kuma" --format "{{.Names}}"
if ($kuma -eq "uptime-kuma") {
    docker start uptime-kuma | Out-Null
} else {
    docker run -d --name uptime-kuma -p 3001:3001 -v uptime-kuma:/app/data louislam/uptime-kuma:1 | Out-Null
}
Write-Host "    OK · Uptime Kuma en http://localhost:3001" -ForegroundColor Green

# 3. OPC UA simulado (nueva terminal)
Write-Host "[3/4] Arrancando servidor OPC UA simulado..." -ForegroundColor Yellow
$opcuaPath = Join-Path $PSScriptRoot "simulated-environment\opcua-sim"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$opcuaPath'; node server.js"
Write-Host "    OK · OPC UA en opc.tcp://localhost:4840 (nueva ventana)" -ForegroundColor Green

# Esperar un momento
Start-Sleep -Seconds 2

# 4. Node-RED (nueva terminal)
Write-Host "[4/4] Arrancando Node-RED..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "node-red"
Write-Host "    OK · Node-RED en http://localhost:1880 (nueva ventana)" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Todo arrancado. Servicios:            " -ForegroundColor Cyan
Write-Host "  · Node-RED    http://localhost:1880   " -ForegroundColor White
Write-Host "  · Uptime Kuma http://localhost:3001   " -ForegroundColor White
Write-Host "  · MQTT        localhost:1883          " -ForegroundColor White
Write-Host "  · OPC UA      localhost:4840          " -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
