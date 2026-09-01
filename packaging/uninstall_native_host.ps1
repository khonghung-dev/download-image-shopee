# Removes only the current user's exact Chrome Native Messaging host key.
$ErrorActionPreference = "Stop"
$HostName = "com.shopee_image_downloader.bridge"
$RegistryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName"

if (Test-Path -LiteralPath $RegistryPath) {
    Remove-Item -LiteralPath $RegistryPath -Recurse -Force
    Write-Host "Native Host registration removed: $RegistryPath"
} else {
    Write-Host "Native Host registration is not present."
}
