# Uninstallation script for Shopee Image Downloader Native Messaging Host
# Removes ONLY: HKCU\Software\Google\Chrome\NativeMessagingHosts\com.shopee_image_downloader.bridge

$ErrorActionPreference = "Stop"

$HostName = "com.shopee_image_downloader.bridge"
$RegistryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName"

Write-Host "Unregistering Chrome Native Messaging Host from HKCU..."
Write-Host "Target Key: $RegistryPath"

if (Test-Path $RegistryPath) {
    Remove-Item -Path $RegistryPath -Recurse -Force
    Write-Host "Successfully removed registry key: $RegistryPath"
} else {
    Write-Host "Registry key does not exist. Nothing to remove."
}

Write-Host "Uninstallation complete!"
