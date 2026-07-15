# Erzeugt deutsche Test-Audios (16 kHz mono WAV) per Windows-TTS fuer
# test_hallucination.py. Einmal ausfuehren; WAVs sind gitignored.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice("Microsoft Hedda Desktop")
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)

$phrases = [ordered]@{
    "neue_zeile"        = "Neue Zeile"
    "fragezeichen"      = "Fragezeichen"
    "test_fragezeichen" = "Das ist ein Test Fragezeichen"
    "neuer_absatz"      = "Neuer Absatz"
    "normaler_satz"     = "Wir treffen uns morgen um zehn Uhr"
}
foreach ($k in $phrases.Keys) {
    $p = Join-Path $HERE "tts_$k.wav"
    $s.SetOutputToWaveFile($p, $fmt)
    $s.Speak($phrases[$k])
    $s.SetOutputToNull()
    Write-Host "OK: $p"
}
$s.Dispose()
