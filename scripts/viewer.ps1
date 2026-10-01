# Start / stop Claude History Viewer in the background (pythonw, no console window).
# Called from start.cmd / stop.cmd. Keep this file ASCII only: Windows PowerShell 5.1
# reads BOM-less UTF-8 as the ANSI code page.
#
#   viewer.ps1 start [viewer args...]   stop the running viewer (if any), then start it
#   viewer.ps1 stop
#
# The running viewer is found by its command line (the full path of claude_chat_viewer.py
# in this folder), not by a PID file, so a reused PID never stops an unrelated process.
param(
    [Parameter(Mandatory = $true, Position = 0)][ValidateSet('start', 'stop')][string]$Action,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ViewerArgs
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$main = Join-Path $root 'claude_chat_viewer.py'

function Get-ViewerProcesses {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($main, [StringComparison]::OrdinalIgnoreCase) -ge 0 }
}

function Stop-Viewer {
    $procs = @(Get-ViewerProcesses)
    if ($procs.Count -eq 0) {
        Write-Host 'Viewer is not running.'
        return
    }
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $p.ProcessId -Timeout 5 -ErrorAction SilentlyContinue
        Write-Host "Stopped viewer [PID $($p.ProcessId)]"
    }
}

function Get-ViewerPort {
    $port = 57080
    $settings = Join-Path $root 'settings.json'
    if (Test-Path $settings) {
        try {
            $json = Get-Content $settings -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($json.port) { $port = [int]$json.port }
        } catch {
            Write-Host "Warning: could not read settings.json ($($_.Exception.Message)); assuming port $port"
        }
    }
    # --port on the command line wins, as in claude_chat_viewer.py
    for ($i = 0; $i -lt $ViewerArgs.Count - 1; $i++) {
        if ($ViewerArgs[$i] -eq '--port') { $port = [int]$ViewerArgs[$i + 1] }
    }
    return $port
}

function Start-Viewer {
    Stop-Viewer
    $argList = @("`"$main`"") + @($ViewerArgs | ForEach-Object { "`"$_`"" })
    $proc = Start-Process pythonw -ArgumentList $argList -WorkingDirectory $root -PassThru
    $port = Get-ViewerPort
    # Wait until the viewer listens. If it exits first, it could not start (port in use, bad settings, ...)
    for ($i = 0; $i -lt 100; $i++) {
        if ($proc.HasExited) {
            Write-Host "Error: the viewer exited right after starting (exit code $($proc.ExitCode))."
            Write-Host "Run this to see the message:  python `"$main`" --no-browser"
            exit 1
        }
        if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                Where-Object { $_.OwningProcess -eq $proc.Id }) {
            Write-Host "Started viewer [PID $($proc.Id)]  http://localhost:$port"
            return
        }
        Start-Sleep -Milliseconds 100
    }
    Write-Host "Warning: started [PID $($proc.Id)] but it is not listening on port $port after 10 s."
}

if ($Action -eq 'start') { Start-Viewer } else { Stop-Viewer }
