param(
    [string]$IsccPath = ""
)

# Compiles the canonical per-user Inno Setup installer without downloading tools.
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$InstallerDefinition = Join-Path $PSScriptRoot "ShopeeImageDownloader.iss"
$PortableRoot = Join-Path $RepoRoot "release\ShopeeImageDownloader-Windows"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$IdentityHelper = Join-Path $RepoRoot "build_support\extension_identity.py"
$ExpectedExtensionId = "bhbnfalghoklngoohdpnjedcdcplbjhm"
$ExpectedSetup = Join-Path $RepoRoot (
    "release\installer\ShopeeImageDownloader-Setup-0.1.0.exe"
)

if (-not $IsccPath) {
    $PathCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    $CompilerCandidates = @()
    if ($PathCommand) {
        $CompilerCandidates += $PathCommand.Source
    }
    $CompilerCandidates += @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "C:\ProgramData\chocolatey\bin\iscc.exe",
        "$env:USERPROFILE\scoop\apps\innosetup\current\ISCC.exe"
    )
    $IsccPath = $CompilerCandidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
}

if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath -PathType Leaf)) {
    Write-Error -ErrorAction Continue (
        "INNO_SETUP_COMPILER_MISSING: Install Inno Setup 6 and rerun " +
        "packaging\build_windows_installer.ps1, or pass -IsccPath to ISCC.exe."
    )
    exit 2
}

$RequiredPayload = @(
    "ShopeeImageDownloader.exe",
    "_internal",
    "native_host\shopee_native_host.exe",
    "chrome_extension\manifest.json",
    "chrome_extension\background.js",
    "chrome_extension\content.js",
    "chrome_extension\extractor_core.js",
    "install_native_host.ps1",
    "uninstall_native_host.ps1",
    "README_FIRST.txt"
)
foreach ($RelativePath in $RequiredPayload) {
    $PayloadPath = Join-Path $PortableRoot $RelativePath
    if (-not (Test-Path -LiteralPath $PayloadPath)) {
        throw "Approved portable payload is incomplete: $RelativePath"
    }
}

foreach ($BuildDependency in @($Python, $IdentityHelper)) {
    if (-not (Test-Path -LiteralPath $BuildDependency -PathType Leaf)) {
        throw "Required installer-build dependency not found: $BuildDependency"
    }
}

& (Join-Path $PortableRoot "install_native_host.ps1") -VerifyOnly
if ($LASTEXITCODE -ne 0) {
    throw "Approved portable payload path verification failed."
}
$DerivedExtensionId = & $Python $IdentityHelper `
    --manifest (Join-Path $PortableRoot "chrome_extension\manifest.json")
if (
    $LASTEXITCODE -ne 0 -or
    ($DerivedExtensionId | Select-Object -Last 1).Trim() -ne $ExpectedExtensionId
) {
    throw "Approved portable payload has an unexpected Extension identity."
}

$ForbiddenNames = @(
    ".git", ".venv", "tests", ".pytest_cache", "__pycache__", "downloads",
    "cookies", "passwords", "tokens", "otp", "diagnostic-captures"
)
$ForbiddenEntries = Get-ChildItem -LiteralPath $PortableRoot -Recurse -Force |
    Where-Object { $ForbiddenNames -contains $_.Name.ToLowerInvariant() }
if ($ForbiddenEntries) {
    throw "Forbidden installer payload entries: $($ForbiddenEntries.FullName -join ', ')"
}

foreach ($Pattern in @("*.pem", "*.key", "*.p12", "*.pfx")) {
    $PrivateKeys = Get-ChildItem `
        -LiteralPath $PortableRoot `
        -Recurse `
        -File `
        -Filter $Pattern
    if ($PrivateKeys) {
        throw "Private-key-like installer payload: $($PrivateKeys.FullName -join ', ')"
    }
}

# The portable manifest and guide are intentionally replaced by install-time files.
$IncludedTextFiles = Get-ChildItem -LiteralPath $PortableRoot -Recurse -File |
    Where-Object {
        $_.Extension -in @(".json", ".ps1", ".txt", ".js", ".html", ".md") -and
        $_.FullName -ne (Join-Path $PortableRoot (
            "native_host\com.shopee_image_downloader.bridge.json"
        )) -and
        $_.FullName -ne (Join-Path $PortableRoot "README_FIRST.txt")
    }
$DeveloperPaths = $IncludedTextFiles | Select-String -Pattern @(
    '(?i)[A-Z]:\\Users\\[^\\]+',
    '(?i)[A-Z]:\\[^"''\r\n]*download-picture-shopee',
    '(?i)\.venv'
)
if ($DeveloperPaths) {
    throw "Developer path/dependency found in installer payload: $DeveloperPaths"
}

& $IsccPath $InstallerDefinition
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
if (-not (Test-Path -LiteralPath $ExpectedSetup -PathType Leaf)) {
    throw "Expected installer output not found: $ExpectedSetup"
}

$Setup = Get-Item -LiteralPath $ExpectedSetup
$SetupHash = Get-FileHash -LiteralPath $Setup.FullName -Algorithm SHA256
Write-Host "SETUP_EXE=$($Setup.FullName)"
Write-Host "SETUP_SIZE_BYTES=$($Setup.Length)"
Write-Host "SETUP_SHA256=$($SetupHash.Hash)"
