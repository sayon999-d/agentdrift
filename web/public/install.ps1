# ==============================================================================
# AgentDrift Official Bootstrap Installer (Windows PowerShell)
# Usage:
#   irm https://agentdrift.io/install.ps1 | iex
#   or:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 [OPTIONS]
# ==============================================================================

[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$InstallDir = "",
    [string]$BinDir = "",
    [switch]$NoModifyPath,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

# Ensure modern TLS protocols are enabled
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
    # Ignore if TLS 1.2 is already configured or unsupported on platform
}

function Write-Info {
    param([string]$Message)
    Write-Host "[info] $Message" -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Magenta
}

function Write-Success {
    param([string]$Message)
    Write-Host "[ok] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[warn] $Message" -ForegroundColor Yellow
}

function Write-ErrorExit {
    param([string]$Message)
    Write-Host "[error] $Message" -ForegroundColor Red
    exit 1
}

function Show-Banner {
    Write-Host @"
     ___                    __   ____       _  ______ 
    /   | ____ ____  ____  / /__/ __ \_____(_)/ __/ /_
   / /| |/ __ `/ _ \/ __ \/ __/ / / / ___/ / / /_/ __/
  / ___ / /_/ /  __/ / / / /_/ /_/ / /  / / / __/ /_  
 /_/  |_\__, /\___/_/ /_/\__/_____/_/  /_/_/_/  \__/  
       /____/                                         
"@ -ForegroundColor Cyan
    Write-Host " Runtime supervisor and circuit breaker for autonomous coding agents`n" -ForegroundColor DarkGray
}

function Show-Help {
    Write-Host @"
AgentDrift CLI Bootstrap Installer for Windows

USAGE:
    irm https://agentdrift.io/install.ps1 | iex
    or:
    powershell -ExecutionPolicy Bypass -File .\install.ps1 [OPTIONS]

PARAMETERS:
    -Version <string>       Specific version of AgentDrift to install (e.g. 0.1.0)
    -InstallDir <string>    Directory for dedicated virtual environment
                            (default: `$env:LOCALAPPDATA\agentdrift)
    -BinDir <string>        Directory where launcher shims are placed
                            (default: `$InstallDir\bin)
    -NoModifyPath           Do not add binary directory to User PATH
    -Force                  Force reinstallation and overwrite existing environment
    -DryRun                 Simulate installation actions without executing changes
    -Help                   Show this help message and exit

ENVIRONMENT VARIABLES:
    AGENTDRIFT_VERSION          Equivalent to -Version
    AGENTDRIFT_INSTALL_DIR      Equivalent to -InstallDir
    AGENTDRIFT_BIN_DIR          Equivalent to -BinDir
    AGENTDRIFT_NO_MODIFY_PATH   Set to 1 to skip modifying PATH
    AGENTDRIFT_FORCE            Set to 1 to force reinstallation
"@
}

if ($Help) {
    Show-Help
    exit 0
}

# Platform check
$isWindowsOS = $true
if ($PSVersionTable.PSVersion.Major -ge 6) {
    if (Get-Variable -Name "IsWindows" -ErrorAction SilentlyContinue) {
        $isWindowsOS = $IsWindows
    }
} elseif ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    $isWindowsOS = $false
}

# Resolve parameters with environment variable fallbacks
if ([string]::IsNullOrWhiteSpace($Version) -and -not [string]::IsNullOrWhiteSpace($env:AGENTDRIFT_VERSION)) {
    $Version = $env:AGENTDRIFT_VERSION
}
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    if (-not [string]::IsNullOrWhiteSpace($env:AGENTDRIFT_INSTALL_DIR)) {
        $InstallDir = $env:AGENTDRIFT_INSTALL_DIR
    } elseif (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $InstallDir = Join-Path $env:LOCALAPPDATA "agentdrift"
    } else {
        $userHome = if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) { $env:USERPROFILE } else { $HOME }
        $InstallDir = Join-Path $userHome ".agentdrift"
    }
}
if ([string]::IsNullOrWhiteSpace($BinDir)) {
    if (-not [string]::IsNullOrWhiteSpace($env:AGENTDRIFT_BIN_DIR)) {
        $BinDir = $env:AGENTDRIFT_BIN_DIR
    } else {
        $BinDir = Join-Path $InstallDir "bin"
    }
}
if (-not $NoModifyPath -and $env:AGENTDRIFT_NO_MODIFY_PATH -eq "1") {
    $NoModifyPath = $true
}
if (-not $Force -and $env:AGENTDRIFT_FORCE -eq "1") {
    $Force = $true
}

Show-Banner

$arch = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
if ($isWindowsOS) {
    Write-Info "Detected platform: Windows ($arch)"
} else {
    Write-Warning "PowerShell running on non-Windows system ($arch)."
    Write-Warning "For native macOS/Linux installation, use: curl -fsSL https://agentdrift.io/install.sh | bash"
}

$pkgSpec = "agentdrift"
if (-not [string]::IsNullOrWhiteSpace($Version) -and $Version -ne "latest") {
    $pkgSpec = "agentdrift==$Version"
}

if ($DryRun) {
    Write-Info "DRY-RUN mode enabled. No changes will be applied."
    Write-Info "Target package: $pkgSpec"
    Write-Info "Target bin directory: $BinDir"
    Write-Info "Target install directory: $InstallDir"
    exit 0
}

# Helper to find eligible Python interpreter >= 3.12
function Find-PythonInterpreter {
    $candidates = @("py.exe", "python.exe", "python3.exe", "python3", "python")
    foreach ($cand in $candidates) {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        if ($null -ne $cmd) {
            $testArgs = if ($cand -like "*py.exe") { @("-3.12", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") } else { @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") }
            try {
                $verOutput = (& $cand $testArgs 2>$null | Out-String).Trim()
                if ($verOutput -match '^(\d+)\.(\d+)$') {
                    $major = [int]$matches[1]
                    $minor = [int]$matches[2]
                    if ($major -eq 3 -and $minor -ge 12) {
                        return @{
                            Executable = $cand
                            Arguments = if ($cand -like "*py.exe") { @("-3.12") } else { @() }
                            Version = $verOutput
                        }
                    }
                }
            } catch {
                # Continue searching
            }
        }
    }
    return $null
}

$installMethod = ""

# Strategy 1: astral-sh/uv tool
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($null -ne $uvCmd) {
    Write-Step "Installing agentdrift CLI via 'uv tool'..."
    try {
        $uvArgs = @("tool", "install")
        if ($Force) { $uvArgs += "--force" }
        $uvArgs += $pkgSpec
        & uv @uvArgs
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Successfully installed $pkgSpec via uv!"
            $installMethod = "uv"
        } else {
            Write-Warning "'uv tool install' exited with code $LASTEXITCODE; falling back..."
        }
    } catch {
        Write-Warning "uv tool install failed; falling back to virtualenv..."
    }
}

# Strategy 2: pipx
if ($installMethod -eq "") {
    $pipxCmd = Get-Command pipx -ErrorAction SilentlyContinue
    if ($null -ne $pipxCmd) {
        Write-Step "Installing agentdrift CLI via 'pipx'..."
        try {
            $pipxArgs = @("install")
            if ($Force) { $pipxArgs += "--force" }
            $pipxArgs += $pkgSpec
            & pipx @pipxArgs
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Successfully installed $pkgSpec via pipx!"
                $installMethod = "pipx"
            } else {
                Write-Warning "'pipx install' exited with code $LASTEXITCODE; falling back..."
            }
        } catch {
            Write-Warning "pipx install failed; falling back to virtualenv..."
        }
    }
}

# Strategy 3: Dedicated Isolated Virtual Environment
if ($installMethod -eq "") {
    Write-Step "Checking Python requirements..."
    $pyInfo = Find-PythonInterpreter
    if ($null -eq $pyInfo) {
        Write-Host ""
        Write-ErrorExit @"
AgentDrift requires Python >= 3.12.
No suitable Python 3.12+ interpreter was found on your system PATH.

To install Python 3.12 or uv on Windows, run:
  winget install Python.Python.3.12
or install the ultra-fast uv tool manager:
  winget install astral-sh.uv
"@
    }

    Write-Info "Using Python interpreter: $($pyInfo.Executable) (v$($pyInfo.Version))"

    $venvDir = Join-Path $InstallDir "venv"
    if (Test-Path $venvDir) {
        if ($Force) {
            Write-Info "Overwriting existing virtual environment at $venvDir..."
            Remove-Item -Recurse -Force $venvDir
        } else {
            Write-Info "Existing virtual environment detected at $venvDir (use -Force to recreate)."
        }
    }

    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    Write-Step "Creating isolated virtual environment in $venvDir..."
    $venvArgs = $pyInfo.Arguments + @("-m", "venv", $venvDir)
    & $pyInfo.Executable @venvArgs
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorExit "Failed to create Python virtual environment."
    }

    $scriptsFolder = if (Test-Path (Join-Path $venvDir "Scripts")) { "Scripts" } else { "bin" }
    $venvPython = Join-Path $venvDir "$scriptsFolder\python.exe"
    if (-not (Test-Path $venvPython)) { $venvPython = Join-Path $venvDir "$scriptsFolder\python" }
    $venvPip = Join-Path $venvDir "$scriptsFolder\pip.exe"
    if (-not (Test-Path $venvPip)) { $venvPip = Join-Path $venvDir "$scriptsFolder\pip" }

    Write-Step "Installing $pkgSpec into isolated environment..."
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPip install --quiet $pkgSpec
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorExit "Failed to install $pkgSpec via pip."
    }

    # Generate launcher batch scripts & PowerShell wrappers in BinDir
    Write-Step "Generating command shims in $BinDir..."
    if (-not (Test-Path $BinDir)) {
        New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
    }

    $tools = @("agentdrift", "agentdrift-mcp")
    foreach ($tool in $tools) {
        $toolExe = Join-Path $venvDir "$scriptsFolder\$tool.exe"
        if (-not (Test-Path $toolExe)) {
            $toolExe = Join-Path $venvDir "$scriptsFolder\$tool"
        }

        if (Test-Path $toolExe) {
            # .cmd launcher
            $cmdFile = Join-Path $BinDir "$tool.cmd"
            "@echo off`r`n`"$toolExe`" %*`r`n" | Out-File -FilePath $cmdFile -Encoding ascii -Force

            # .ps1 launcher
            $ps1File = Join-Path $BinDir "$tool.ps1"
            "& `"$toolExe`" @args`r`n" | Out-File -FilePath $ps1File -Encoding ascii -Force

            Write-Success "Created launcher: $cmdFile"
        }
    }

    $installMethod = "venv"
}

# Determine active target bin folder for PATH check
$targetBin = $BinDir
if ($installMethod -eq "uv") {
    $targetBin = if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) { Join-Path $env:USERPROFILE ".local\bin" } else { Join-Path $HOME ".local/bin" }
} elseif ($installMethod -eq "pipx") {
    $pipxHome = [Environment]::GetEnvironmentVariable("PIPX_BIN_DIR")
    if (-not [string]::IsNullOrWhiteSpace($pipxHome)) {
        $targetBin = $pipxHome
    } else {
        $targetBin = if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) { Join-Path $env:USERPROFILE ".local\bin" } else { Join-Path $HOME ".local/bin" }
    }
}

$pathUpdated = $false
if (-not $NoModifyPath -and $isWindowsOS) {
    try {
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($null -eq $userPath) { $userPath = "" }
        $pathParts = $userPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

        if ($pathParts -notcontains $targetBin) {
            Write-Step "Adding $targetBin to User PATH..."
            $newUserPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $targetBin } else { "$userPath;$targetBin" }
            [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
            $env:Path = "$targetBin;$env:Path"
            Write-Success "Added $targetBin to User PATH."
            $pathUpdated = $true
        }
    } catch {
        Write-Warning "Could not update User PATH in registry: $_"
    }
}

# Verify binary execution
Write-Step "Verifying installation..."
$agentdriftInstalled = Get-Command "agentdrift" -ErrorAction SilentlyContinue
if ($null -ne $agentdriftInstalled -or (Test-Path (Join-Path $BinDir "agentdrift.cmd")) -or (Test-Path (Join-Path $BinDir "agentdrift"))) {
    Write-Success "AgentDrift CLI is ready!"
} else {
    Write-Warning "AgentDrift CLI installed, but could not be located on the active PATH."
}

Write-Host ""
Write-Host "✓ Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To verify and start using AgentDrift:"
if ($pathUpdated) {
    Write-Host "  * Note: Restart your PowerShell terminal or VS Code window to refresh PATH." -ForegroundColor DarkYellow
}
Write-Host "  agentdrift --help" -ForegroundColor Cyan
Write-Host "  agentdrift health     # check sentinel & daemon connectivity" -ForegroundColor Cyan
Write-Host "  agentdrift watch      # stream local agent executions`n" -ForegroundColor Cyan
