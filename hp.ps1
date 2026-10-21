# Управление Docker-стендом Harvest Pay.
#
#   .\hp.cmd            поднять всё (то же, что .\hp.cmd up)
#   .\hp.cmd up         собрать образы и запустить в фоне, дождаться готовности API
#   .\hp.cmd down       остановить (данные БД сохраняются)
#   .\hp.cmd restart    перезапустить без пересборки
#   .\hp.cmd logs [svc] смотреть логи (всех сервисов или одного: api, worker, web, db, redis)
#   .\hp.cmd ps         состояние контейнеров
#   .\hp.cmd reset      остановить и УДАЛИТЬ базу (все заявки пропадут)
#
# hp.cmd — обёртка, чтобы скрипт запускался без смены политики выполнения PowerShell.

param(
    [Parameter(Position = 0)]
    [ValidateSet("up", "down", "restart", "logs", "ps", "reset")]
    [string]$Command = "up",

    [Parameter(Position = 1)]
    [string]$Service
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8   # русский текст в любой консоли
Set-Location $PSScriptRoot

function Test-Docker {
    # Через cmd: в PowerShell 5.1 stderr от docker при ErrorActionPreference=Stop стал бы исключением
    cmd /c "docker info >nul 2>&1"
    return $LASTEXITCODE -eq 0
}

function Wait-Docker {
    if (Test-Docker) { return }

    $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $desktop)) {
        throw "Docker не найден. Установите Docker Desktop: https://www.docker.com/products/docker-desktop/"
    }
    Write-Host "Docker Desktop не запущен — запускаю и жду (до 3 минут)..." -ForegroundColor Yellow
    Start-Process $desktop
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 2
        if (Test-Docker) { return }
    }
    throw "Docker так и не запустился. Откройте Docker Desktop вручную и повторите."
}

function Get-Port([string]$Name, [int]$Default) {
    # Порт из .env (HP_WEB_PORT=8081), иначе значение по умолчанию — как в docker-compose.yml
    if (Test-Path ".env") {
        $line = Select-String -Path ".env" -Pattern "^\s*$Name\s*=\s*(\d+)" | Select-Object -First 1
        if ($line) { return [int]$line.Matches[0].Groups[1].Value }
    }
    return $Default
}

function Wait-Api {
    $apiPort = Get-Port "HP_API_PORT" 8000
    Write-Host "Жду, пока API применит миграции и ответит..." -NoNewline
    for ($i = 0; $i -lt 60; $i++) {
        try {
            Invoke-RestMethod "http://localhost:$apiPort/api/health" -TimeoutSec 2 | Out-Null
            Write-Host " готово" -ForegroundColor Green
            return
        } catch {
            Write-Host "." -NoNewline
            Start-Sleep -Seconds 2
        }
    }
    Write-Host ""
    throw "API не ответил за 2 минуты. Смотрите логи: .\hp.cmd logs api"
}

function Invoke-Compose {
    $ErrorActionPreference = "Continue"   # compose пишет прогресс в stderr — это не ошибка
    docker compose @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose $args завершился с ошибкой" }
}

Wait-Docker

switch ($Command) {
    "up" {
        if (-not (Test-Path ".env")) {
            Copy-Item ".env.example" ".env"
            Write-Host "Создан .env из .env.example (демо-режим)" -ForegroundColor Cyan
        }
        try {
            Invoke-Compose up --build -d
        } catch {
            Write-Host "Если выше 'port is already allocated' — порт занят другой программой." -ForegroundColor Yellow
            Write-Host "Поменяйте HP_WEB_PORT / HP_API_PORT в файле .env и запустите снова." -ForegroundColor Yellow
            throw
        }
        Wait-Api
        Write-Host ""
        Write-Host "Сайт:     http://localhost:$(Get-Port 'HP_WEB_PORT' 8080)" -ForegroundColor Green
        Write-Host "Swagger:  http://localhost:$(Get-Port 'HP_API_PORT' 8000)/docs" -ForegroundColor Green
        Write-Host "Аналитик: токен analyst-demo-token"
        Write-Host "Логи:     .\hp.cmd logs    Остановить: .\hp.cmd down"
    }
    "down"    { Invoke-Compose down }
    "restart" { Invoke-Compose restart; Wait-Api }
    "logs"    { if ($Service) { Invoke-Compose logs -f --tail 100 $Service } else { Invoke-Compose logs -f --tail 100 } }
    "ps"      { Invoke-Compose ps }
    "reset" {
        $answer = Read-Host "Удалить базу со всеми заявками? (y/N)"
        if ($answer -eq "y") { Invoke-Compose down -v; Write-Host "Стенд остановлен, база удалена." }
    }
}
