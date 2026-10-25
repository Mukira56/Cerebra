param([Parameter(Mandatory=$true)][string]$OutputPath)
# Packs the pre-rendered Cerebra logo PNGs (packaging/windows/icon, rendered from ai_hq/static/logo.svg) into one .ico.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot '..\packaging\windows\icon'
$images = @()
foreach ($size in @(16, 24, 32, 48, 64, 128, 256)) {
    $images += ,@($size, [System.IO.File]::ReadAllBytes((Join-Path $source "logo-$size.png")))
}
$file = [System.IO.File]::Create($OutputPath)
$writer = New-Object System.IO.BinaryWriter($file)
try {
    $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$images.Count)
    $offset = 6 + 16 * $images.Count
    foreach ($entry in $images) {
        $dimension = if ($entry[0] -eq 256) { 0 } else { $entry[0] }
        $writer.Write([byte]$dimension); $writer.Write([byte]$dimension)
        $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]32)
        $writer.Write([uint32]$entry[1].Length); $writer.Write([uint32]$offset)
        $offset += $entry[1].Length
    }
    foreach ($entry in $images) { $writer.Write([byte[]]$entry[1]) }
} finally { $writer.Dispose(); $file.Dispose() }
