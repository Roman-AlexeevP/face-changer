#Requires -Version 5.1
<#
.SYNOPSIS
Обёртка над docker compose для типовых задач проекта.

.DESCRIPTION
На хосте не требуется ни Python, ни ffmpeg, ни make: всё выполняется
в контейнерах. Одноразовые джобы (миграции, тесты) запускаются через
docker compose run --rm и не оставляют следов.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'up', 'down', 'logs', 'migrate', 'test', 'lint', 'fmt', 'psql', 'ps', 'clean')]
    [string]$Task = 'help'
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Compose {
    param([string[]]$Arguments)

    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') завершился с кодом $LASTEXITCODE"
    }
}

function Show-Usage {
    $lines = @(
        'Использование: tasks.cmd <команда>',
        '',
        '  up       собрать и поднять postgres, bot, worker',
        '  down     остановить и удалить контейнеры',
        '  migrate  одноразовая джоба: alembic upgrade head',
        '  test     тесты в контейнере, HTML-отчёт в reports/',
        '  lint     ruff check + ruff format --check',
        '  fmt      ruff format',
        '  psql     psql внутри контейнера postgres',
        '  ps       статус контейнеров',
        '  clean    удалить контейнеры и тома'
    )
    $lines | ForEach-Object { Write-Host $_ }
}

switch ($Task) {
    'up' {
        Invoke-Compose @('up', '-d', '--wait', 'postgres')
        try {
            Invoke-Compose @('--profile', 'tools', 'run', '--rm', '--build', 'migrate')
        }
        catch {
            Write-Host 'Ошибка: миграции не применились, приложение не запущено.' -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
            exit 1
        }
        Invoke-Compose @('up', '-d', '--build', '--force-recreate', 'bot', 'worker')
    }
    'down' { Invoke-Compose @('down') }
    'logs' { Invoke-Compose @('logs', '-f', '--tail=100') }
    'migrate' { Invoke-Compose @('--profile', 'tools', 'run', '--rm', 'migrate') }
    'test' { Invoke-Compose @('--profile', 'test', 'run', '--rm', '--build', 'tests') }
    'lint' {
        Invoke-Compose @(
            '--profile', 'test', 'run', '--rm', 'tests',
            'sh', '-c', 'ruff check . && ruff format --check .'
        )
    }
    'fmt' { Invoke-Compose @('--profile', 'test', 'run', '--rm', 'tests', 'ruff', 'format', '.') }
    'psql' { Invoke-Compose @('exec', 'postgres', 'psql', '-U', 'user', '-d', 'facechanger') }
    'ps' { Invoke-Compose @('ps') }
    'clean' { Invoke-Compose @('--profile', 'test', '--profile', 'tools', 'down', '-v', '--remove-orphans') }
    default { Show-Usage }
}
