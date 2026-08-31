# Installation script for Shopee Image Downloader Native Messaging Host
# Target registry key: HKCU\Software\Google\Chrome\NativeMessagingHosts\com.shopee_image_downloader.bridge
# Modifies ONLY this specific HKCU key. Requires NO administrator privileges.

$ErrorActionPreference = "Stop"

$HostName = "com.shopee_image_downloader.bridge"
$ManifestPath = Join-Path $PSScriptRoot "$HostName.json"

if (-not (Test-Path $ManifestPath)) {
    Write-Error "Manifest file not found at: $ManifestPath. Please run build_host.ps1 first."
    exit 1
}

$RegistryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName"

Write-Host "Registering Chrome Native Messaging Host in HKCU..."
Write-Host "Target Key: $RegistryPath"
Write-Host "Manifest Path: $ManifestPath"

# Create registry key if it does not exist
if (-not (Test-Path $RegistryPath)) {
    New-Item -Path $RegistryPath -Force | Out-Null
}

# Set (Default) value to the absolute path of the manifest JSON
Set-ItemProperty -Path $RegistryPath -Name "(Default)" -Value (Resolve-Path $ManifestPath).Path

Write-Host "Registration successful!"
Write-Host "Chrome Extension can now connect to host: $HostName"
