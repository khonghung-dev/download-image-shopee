param(
    [switch]$VerifyOnly
)

# Installs only the current user's exact Chrome Native Messaging host key.
$ErrorActionPreference = "Stop"
$HostName = "com.shopee_image_downloader.bridge"
$RegistryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName"
$ExtensionManifestPath = Join-Path $PSScriptRoot "chrome_extension\manifest.json"
$HostExePath = Join-Path $PSScriptRoot "native_host\shopee_native_host.exe"
$NativeManifestPath = Join-Path $PSScriptRoot "native_host\$HostName.json"

if (-not (Test-Path -LiteralPath $ExtensionManifestPath -PathType Leaf)) {
    throw "Extension manifest not found: $ExtensionManifestPath"
}
if (-not (Test-Path -LiteralPath $HostExePath -PathType Leaf)) {
    throw "Native Host executable not found: $HostExePath"
}

$ExtensionManifest = Get-Content -LiteralPath $ExtensionManifestPath -Raw |
    ConvertFrom-Json
if (-not $ExtensionManifest.key) {
    throw 'Extension manifest does not contain the canonical public "key".'
}

try {
    $PublicKeyDer = [Convert]::FromBase64String([string]$ExtensionManifest.key)
} catch {
    throw 'Extension manifest "key" is not valid Base64.'
}

$Sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $Digest = $Sha256.ComputeHash($PublicKeyDer)
} finally {
    $Sha256.Dispose()
}

$IdBuilder = [Text.StringBuilder]::new(32)
foreach ($Byte in $Digest[0..15]) {
    [void]$IdBuilder.Append([char](97 + (($Byte -shr 4) -band 15)))
    [void]$IdBuilder.Append([char](97 + ($Byte -band 15)))
}
$ExtensionId = $IdBuilder.ToString()
$ExtensionOrigin = "chrome-extension://$ExtensionId/"

Write-Host "STABLE_EXTENSION_ID=$ExtensionId"
Write-Host "ALLOWED_ORIGIN=$ExtensionOrigin"
if ($VerifyOnly) {
    Write-Host "Identity and packaged paths verified; registry was not changed."
    exit 0
}

$ResolvedHostExe = (Resolve-Path -LiteralPath $HostExePath).Path
$NativeManifest = [ordered]@{
    name = $HostName
    description = "Shopee Image Downloader Native Bridge"
    path = $ResolvedHostExe
    type = "stdio"
    allowed_origins = @($ExtensionOrigin)
}
$Utf8WithoutBom = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText(
    $NativeManifestPath,
    ($NativeManifest | ConvertTo-Json -Depth 4),
    $Utf8WithoutBom
)

if (-not (Test-Path -LiteralPath $RegistryPath)) {
    New-Item -Path $RegistryPath -Force | Out-Null
}
Set-ItemProperty `
    -LiteralPath $RegistryPath `
    -Name "(Default)" `
    -Value (Resolve-Path -LiteralPath $NativeManifestPath).Path

Write-Host "Native Host registered for the current user only."
Write-Host "Registry key: $RegistryPath"
Write-Host "Manifest: $NativeManifestPath"
