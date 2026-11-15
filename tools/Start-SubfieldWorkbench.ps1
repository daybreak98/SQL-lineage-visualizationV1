[CmdletBinding()]
param(
    [string]$Python,
    [ValidateRange(1, 65535)][int]$ApiPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 5173,
    [switch]$Install,
    [switch]$SmokeTest,
    [switch]$EnableSubfieldFactCache
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root 'frontend'
$constraints = Join-Path $PSScriptRoot 'subfield-workbench-constraints.txt'
$requirements = Join-Path $root 'backend/requirements.txt'
$defaultPython = -not $Python
if ($defaultPython) {
    $Python = Join-Path $root 'backend/.venv/Scripts/python.exe'
}
if ($ApiPort -eq $FrontendPort) {
    throw 'ApiPort and FrontendPort must differ.'
}

function Assert-FreePort([int]$Port) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    $listener.ExclusiveAddressUse = $true
    try { $listener.Start() }
    catch { throw "127.0.0.1:${Port} is unavailable. Pick another port. $($_.Exception.Message)" }
    finally { $listener.Stop() }
}

function Wait-LocalPort([int]$Port, [Diagnostics.Process]$Process, [string]$Log) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt 30) {
        if ($Process.HasExited) {
            throw "Process exited ($($Process.ExitCode)). See $Log"
        }
        $client = [Net.Sockets.TcpClient]::new()
        try {
            $client.Connect([Net.IPAddress]::Loopback, $Port)
            return
        }
        catch [Net.Sockets.SocketException] { Start-Sleep -Milliseconds 200 }
        finally { $client.Dispose() }
    }
    throw "127.0.0.1:${Port} did not start. See $Log"
}

function Stop-StartedProcess([Diagnostics.Process]$Process) {
    if ($null -ne $Process) {
        try {
            if (-not $Process.HasExited) {
                $Process.Kill()
                if (-not $Process.WaitForExit(5000)) {
                    Write-Warning "Process $($Process.Id) did not exit within five seconds."
                }
            }
        }
        catch {
            if (-not $Process.HasExited) {
                Write-Warning "Could not stop process $($Process.Id): $_"
            }
        }
        finally { $Process.Dispose() }
    }
}

$installHint = "& '$Python' -I -m pip install -r '$requirements' -c '$constraints'"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    if (-not ($Install -and $defaultPython)) {
        throw "Python venv executable not found: $Python. Use -Install for backend/.venv, or pass -Python <venv>/Scripts/python.exe. Create the default venv with: py -3.11 -m venv '$root/backend/.venv'"
    }
    $pyLauncher = (Get-Command py.exe -ErrorAction Stop).Source
    & $pyLauncher -3.11 -m venv (Join-Path $root 'backend/.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create backend/.venv with Python 3.11.' }
}
$Python = (Resolve-Path -LiteralPath $Python).Path
$node = (Get-Command node.exe -ErrorAction Stop).Source
$vite = Join-Path $frontend 'node_modules/vite/bin/vite.js'

& $Python -I -c 'import sys; raise SystemExit(sys.prefix == sys.base_prefix)'
if ($LASTEXITCODE -ne 0) { throw 'Pass the python.exe of a Python virtual environment.' }

if ($Install) {
    & $Python -I -m pip install -r $requirements -c $constraints
    if ($LASTEXITCODE -ne 0) { throw "Backend install failed. Retry with: $installHint" }
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    Push-Location $frontend
    try {
        & $npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed: npm ci.' }
    }
    finally { Pop-Location }
}
& $Python -I -c 'import fastapi, python_multipart, sqlglot, uvicorn; print("SQLGlot " + sqlglot.__version__); raise SystemExit(sqlglot.__version__ != "30.31.0")'
if ($LASTEXITCODE -ne 0) { throw "Backend dependencies missing or SQLGlot version differs. Run: $installHint" }
if (-not (Test-Path -LiteralPath $vite -PathType Leaf)) {
    throw "Frontend dependencies missing. In '$frontend' run: npm ci"
}

Assert-FreePort $ApiPort
Assert-FreePort $FrontendPort
$runDir = Join-Path (Join-Path $root 'data/subfield-workbench-local') ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$dbPath = Join-Path $runDir 'metadata.db'
$apiError = Join-Path $runDir 'api.stderr.log'
$viteError = Join-Path $runDir 'vite.stderr.log'
$apiUrl = "http://127.0.0.1:$ApiPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"
$workbenchUrl = "$frontendUrl/?view=subfield"
$apiProcess = $null
$viteProcess = $null
$oldDb = $env:SQL_LINEAGE_DB
$oldProxy = $env:BACKEND_PROXY_TARGET
$oldFactCache = $env:SUBFIELD_FACT_CACHE
$cacheEnabled = if ($PSBoundParameters.ContainsKey('EnableSubfieldFactCache')) {
    [bool]$EnableSubfieldFactCache
}
else {
    $oldFactCache -ceq '1'
}
try {
    # Launch the real runtimes directly: no cmd/npm wrapper, reloader, or workers.
    try {
        $env:SQL_LINEAGE_DB = $dbPath
        $env:SUBFIELD_FACT_CACHE = if ($cacheEnabled) { '1' } else { $null }
        $apiProcess = Start-Process -FilePath $Python -ArgumentList @(
            '-I', '-X', 'utf8', '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend',
            '--host', '127.0.0.1', '--port', $ApiPort, '--workers', '1', '--no-proxy-headers'
        ) -WorkingDirectory $root -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $runDir 'api.stdout.log') -RedirectStandardError $apiError
        # Vite must not inherit the switch or an opt-in from the caller.
        $env:SUBFIELD_FACT_CACHE = $null
        $env:BACKEND_PROXY_TARGET = $apiUrl
        $viteProcess = Start-Process -FilePath $node -ArgumentList @(
            'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', $FrontendPort, '--strictPort'
        ) -WorkingDirectory $frontend -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $runDir 'vite.stdout.log') -RedirectStandardError $viteError
    }
    finally {
        $env:SQL_LINEAGE_DB = $oldDb
        $env:BACKEND_PROXY_TARGET = $oldProxy
        $env:SUBFIELD_FACT_CACHE = $oldFactCache
    }
    Wait-LocalPort $ApiPort $apiProcess $apiError
    Wait-LocalPort $FrontendPort $viteProcess $viteError
    Write-Host "Workbench: $workbenchUrl"
    Write-Host "API: $apiUrl (PID $($apiProcess.Id)); Vite: PID $($viteProcess.Id)"
    Write-Host "Local SQLite and logs: $runDir"
    Write-Host "Subfield fact cache opt-in (API only): $cacheEnabled"

    if ($SmokeTest) {
        $page = Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 -Uri $workbenchUrl
        if ($page.StatusCode -ne 200 -or $page.Content -notmatch '<title>') {
            throw 'Workbench GET did not return the HTML page.'
        }
        $request = @{
            dialect = 'spark'
            sql = 'SELECT get_json_object(e.payload, ''$.id'') AS id FROM events e'
        } | ConvertTo-Json -Compress
        $response = Invoke-RestMethod -TimeoutSec 15 -Uri "$frontendUrl/api/sql/subfield-lineage" `
            -Method Post -ContentType 'application/json' -Body $request
        if (-not $response.coverage.parsed -or $response.coverage.sqlglot -ne '30.31.0' -or
            -not ($response.uses | Where-Object {
                $_.source -eq 'events' -and $_.column -eq 'payload' -and $_.path -eq '$.id'
            }) -or -not (Test-Path -LiteralPath $dbPath -PathType Leaf)) {
            throw 'Proxied analysis or local SQLite check failed.'
        }
        Write-Host 'Smoke passed: GET /?view=subfield and POST /api/sql/subfield-lineage via Vite; events.payload $.id.'
    }
    else {
        Write-Host 'Press Ctrl+C to stop both services.'
        while (-not $apiProcess.HasExited -and -not $viteProcess.HasExited) {
            Start-Sleep -Milliseconds 500
        }
        throw "A service exited. See $runDir"
    }
}
finally {
    Stop-StartedProcess $viteProcess
    Stop-StartedProcess $apiProcess
}
