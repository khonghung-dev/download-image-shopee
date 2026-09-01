# Builds and assembles the first Windows release as PyInstaller ONEDIR.
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $RepoRoot "build\task016a-release"
$DesktopWork = Join-Path $BuildRoot "desktop-work"
$DesktopDist = Join-Path $BuildRoot "desktop-dist"
$NativeHostWork = Join-Path $BuildRoot "native-host-work"
$NativeHostDist = Join-Path $BuildRoot "native-host-dist"
$ReleaseParent = Join-Path $RepoRoot "release"
$ReleaseRoot = Join-Path $ReleaseParent "ShopeeImageDownloader-Windows"
$ZipPath = Join-Path $ReleaseParent "ShopeeImageDownloader-Windows.zip"
$PyInstaller = Join-Path $RepoRoot ".venv\Scripts\pyinstaller.exe"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$IdentityHelper = Join-Path $RepoRoot "build_support\extension_identity.py"
$ExtensionManifest = Join-Path $RepoRoot "chrome_extension\manifest.json"
$DevNativeManifest = Join-Path $RepoRoot "native_host\com.shopee_image_downloader.bridge.json"
$DesktopSpec = Join-Path $PSScriptRoot "ShopeeImageDownloader.spec"

function Assert-SafeChildPath([string]$Candidate, [string]$Parent) {
    $FullCandidate = [IO.Path]::GetFullPath($Candidate)
    $FullParent = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $FullCandidate.StartsWith($FullParent, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe build target outside expected parent: $FullCandidate"
    }
}

Assert-SafeChildPath $BuildRoot $RepoRoot
Assert-SafeChildPath $ReleaseRoot $RepoRoot
if ([IO.Path]::GetFullPath($ZipPath) -ne [IO.Path]::GetFullPath(
    (Join-Path $ReleaseParent "ShopeeImageDownloader-Windows.zip"))) {
    throw "Unexpected ZIP target: $ZipPath"
}

foreach ($RequiredFile in @($PyInstaller, $Python, $IdentityHelper, $DesktopSpec)) {
    if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
        throw "Required build file not found: $RequiredFile"
    }
}

Write-Host "Checking canonical Extension identity..."
& $Python $IdentityHelper `
    --manifest $ExtensionManifest `
    --check-native-manifest $DevNativeManifest
if ($LASTEXITCODE -ne 0) {
    throw "Extension identity gate failed."
}

foreach ($GeneratedPath in @($BuildRoot, $ReleaseRoot)) {
    if (Test-Path -LiteralPath $GeneratedPath) {
        Remove-Item -LiteralPath $GeneratedPath -Recurse -Force
    }
}
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
New-Item -ItemType Directory -Path $BuildRoot, $ReleaseRoot | Out-Null

Write-Host "Building Desktop ONEDIR..."
& $PyInstaller `
    --noconfirm `
    --distpath $DesktopDist `
    --workpath $DesktopWork `
    $DesktopSpec
if ($LASTEXITCODE -ne 0) {
    throw "Desktop PyInstaller build failed."
}

Write-Host "Building fresh Native Host executable..."
& (Join-Path $RepoRoot "native_host\build_host.ps1") `
    -DistDir $NativeHostDist `
    -WorkDir $NativeHostWork
if ($LASTEXITCODE -ne 0) {
    throw "Native Host build failed."
}

$DesktopOnedir = Join-Path $DesktopDist "ShopeeImageDownloader"
$DesktopExe = Join-Path $DesktopOnedir "ShopeeImageDownloader.exe"
$NativeHostExe = Join-Path $NativeHostDist "shopee_native_host.exe"
foreach ($BuiltFile in @($DesktopExe, $NativeHostExe)) {
    if (-not (Test-Path -LiteralPath $BuiltFile -PathType Leaf)) {
        throw "Expected build output not found: $BuiltFile"
    }
}

Copy-Item -Path (Join-Path $DesktopOnedir "*") -Destination $ReleaseRoot -Recurse
Copy-Item `
    -LiteralPath (Join-Path $RepoRoot "chrome_extension") `
    -Destination (Join-Path $ReleaseRoot "chrome_extension") `
    -Recurse
New-Item -ItemType Directory -Path (Join-Path $ReleaseRoot "native_host") | Out-Null
Copy-Item -LiteralPath $NativeHostExe -Destination (
    Join-Path $ReleaseRoot "native_host\shopee_native_host.exe"
)
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "install_native_host.ps1") -Destination $ReleaseRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "uninstall_native_host.ps1") -Destination $ReleaseRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README_FIRST.txt") -Destination $ReleaseRoot

Write-Host "Verifying packaged Extension identity and paths..."
& $Python $IdentityHelper `
    --manifest (Join-Path $ReleaseRoot "chrome_extension\manifest.json")
if ($LASTEXITCODE -ne 0) {
    throw "Packaged Extension identity check failed."
}
& (Join-Path $ReleaseRoot "install_native_host.ps1") -VerifyOnly
if ($LASTEXITCODE -ne 0) {
    throw "Packaged Native Host install-script verification failed."
}

$ForbiddenNames = @(
    ".git", ".venv", "tests", "downloads", "cookies", "passwords",
    "tokens", "otp", "diagnostic-captures"
)
$ForbiddenEntries = Get-ChildItem -LiteralPath $ReleaseRoot -Recurse -Force |
    Where-Object { $ForbiddenNames -contains $_.Name.ToLowerInvariant() }
if ($ForbiddenEntries) {
    throw "Forbidden package entries detected: $($ForbiddenEntries.FullName -join ', ')"
}

$PrivateKeyPatterns = @("*.pem", "*.key", "*.p12", "*.pfx")
foreach ($Pattern in $PrivateKeyPatterns) {
    $Matches = Get-ChildItem -LiteralPath $ReleaseRoot -Recurse -File -Filter $Pattern
    if ($Matches) {
        throw "Private-key-like package entries detected: $($Matches.FullName -join ', ')"
    }
}

$PortableTextFiles = Get-ChildItem -LiteralPath $ReleaseRoot -Recurse -File |
    Where-Object { $_.Extension -in @(".json", ".ps1", ".txt", ".js", ".html", ".md") }
$DeveloperPathMatches = $PortableTextFiles | Select-String -SimpleMatch @(
    "D:\download-picture-shopee", "C:\Users\khong", ".venv", "source Python"
)
if ($DeveloperPathMatches) {
    throw "Developer path/dependency found in packaged text: $DeveloperPathMatches"
}

Compress-Archive -LiteralPath $ReleaseRoot -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "RELEASE_DIRECTORY=$ReleaseRoot"
Write-Host "RELEASE_ZIP=$ZipPath"
