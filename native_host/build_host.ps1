# Build script for Shopee Image Downloader Native Messaging Host
# Generates native_host\dist\shopee_native_host.exe using PyInstaller

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
$VenvPyInstaller = Join-Path $RepoRoot ".venv\Scripts\pyinstaller.exe"

if (-not (Test-Path $VenvPyInstaller)) {
    Write-Error "PyInstaller not found at $VenvPyInstaller. Please run '.venv\Scripts\python.exe -m pip install pyinstaller' first."
    exit 1
}

$HostScript = Join-Path $PSScriptRoot "host.py"
$DistDir = Join-Path $PSScriptRoot "dist"
$BuildDir = Join-Path $PSScriptRoot "build"
$ExeName = "shopee_native_host.exe"
$OutputExe = Join-Path $DistDir $ExeName

Write-Host "Building Native Messaging Host executable with PyInstaller..."
& $VenvPyInstaller `
    --noconfirm `
    --onefile `
    --console `
    --name "shopee_native_host" `
    --distpath $DistDir `
    --workpath $BuildDir `
    --specpath $PSScriptRoot `
    --paths $PSScriptRoot `
    $HostScript

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
    Set-Content -Path $ManifestPath -Value $ManifestContent -Encoding UTF8
    Write-Host "Generated native messaging manifest at: $ManifestPath"
} else {
    Write-Error "Manifest template not found: $TemplatePath"
    exit 1
}

Write-Host "Build complete!"
