# Build script for Shopee Image Downloader Native Messaging Host
# Generates native_host\dist\shopee_native_host.exe using PyInstaller

param(
    [string]$DistDir = (Join-Path $PSScriptRoot "dist"),
    [string]$WorkDir = (Join-Path $PSScriptRoot "build")
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
$VenvPyInstaller = Join-Path $RepoRoot ".venv\Scripts\pyinstaller.exe"
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$IdentityHelper = Join-Path $RepoRoot "build_support\extension_identity.py"
$ExtensionManifest = Join-Path $RepoRoot "chrome_extension\manifest.json"

if (-not (Test-Path $VenvPyInstaller)) {
    Write-Error "PyInstaller not found at $VenvPyInstaller. Please run '.venv\Scripts\python.exe -m pip install pyinstaller' first."
    exit 1
}

if (-not (Test-Path $IdentityHelper)) {
    Write-Error "Extension identity helper not found at $IdentityHelper."
    exit 1
}

$ExtensionOrigin = & $VenvPython $IdentityHelper `
    --manifest $ExtensionManifest `
    --print-origin
if ($LASTEXITCODE -ne 0 -or -not $ExtensionOrigin) {
    Write-Error "Cannot derive the canonical Extension origin from manifest.json."
    exit 1
}

$HostScript = Join-Path $PSScriptRoot "host.py"
$ExeName = "shopee_native_host.exe"
$OutputExe = Join-Path $DistDir $ExeName

Write-Host "Building Native Messaging Host executable with PyInstaller..."
& $VenvPyInstaller `
    --noconfirm `
    --onefile `
    --console `
    --name "shopee_native_host" `
    --distpath $DistDir `
    --workpath $WorkDir `
    --specpath $PSScriptRoot `
    --paths $PSScriptRoot `
    $HostScript

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed to build the Native Messaging Host."
    exit $LASTEXITCODE
}

if (-not (Test-Path $OutputExe)) {
    Write-Error "Build failed: $OutputExe was not created."
    exit 1
}

Write-Host "Native host executable built successfully at: $OutputExe"

# Generate manifest from template
$TemplatePath = Join-Path $PSScriptRoot "com.shopee_image_downloader.bridge.json.template"
$ManifestPath = Join-Path $PSScriptRoot "com.shopee_image_downloader.bridge.json"

if (Test-Path $TemplatePath) {
    $TemplateContent = Get-Content -Raw -Path $TemplatePath
    $EscapedPath = $OutputExe.Replace('\', '\\')
    $ManifestContent = $TemplateContent.Replace('HOST_PATH_PLACEHOLDER', $EscapedPath)
    $ManifestContent = $ManifestContent.Replace('EXTENSION_ORIGIN_PLACEHOLDER', $ExtensionOrigin)
    Set-Content -Path $ManifestPath -Value $ManifestContent -Encoding UTF8
    & $VenvPython $IdentityHelper `
        --manifest $ExtensionManifest `
        --check-native-manifest $ManifestPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Generated Native Messaging manifest does not match the canonical Extension identity."
        exit 1
    }
    Write-Host "Generated native messaging manifest at: $ManifestPath"
} else {
    Write-Error "Manifest template not found: $TemplatePath"
    exit 1
}

Write-Host "Build complete!"
