param([string]$PoolDir = "$PSScriptRoot\dsr_demo\random_pool")

$ErrorActionPreference = 'Stop'
$items = Get-Content -Raw "$PoolDir\vocabulary.json" | ConvertFrom-Json
$targetDir = New-Item -ItemType Directory -Force "$PoolDir\target"
$reconDir = New-Item -ItemType Directory -Force "$PoolDir\reconstructed_process"
$voice = New-Object -ComObject SAPI.SpVoice
$voice.Voice = $voice.GetVoices() | Where-Object { $_.GetDescription() -like '*Zira*' } | Select-Object -First 1

function Write-Speech([string]$Text, [string]$Path, [switch]$LowVoice) {
    if (Test-Path $Path) { return }
    $stream = New-Object -ComObject SAPI.SpFileStream
    $format = New-Object -ComObject SAPI.SpAudioFormat
    $format.Type = 22
    $stream.Format = $format
    $stream.Open($Path, 3, $false)
    $voice.AudioOutputStream = $stream
    $voice.Rate = if ($LowVoice) { -2 } else { -1 }
    if ($LowVoice) { [void]$voice.Speak("<pitch middle='-12'><rate speed='-8'>$Text</rate></pitch>", 8) } else { [void]$voice.Speak($Text) }
    $stream.Close()
    if ((Get-Item $Path).Length -le 44) { throw "Invalid WAV: $Path" }
}

foreach ($item in $items) {
    $id = "{0:D3}" -f [int]$item.id
    Write-Speech $item.word (Join-Path $targetDir.FullName "$id.wav")
    Write-Speech $item.word (Join-Path $reconDir.FullName "$id.wav") -LowVoice
    if (([int]$item.id + 1) % 50 -eq 0) { Write-Host "voices $([int]$item.id + 1)/$($items.Count)" }
}
