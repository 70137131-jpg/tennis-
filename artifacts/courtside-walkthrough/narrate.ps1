$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$videoRoot = $PSScriptRoot
$videoScenes = Get-Content -LiteralPath (Join-Path $videoRoot 'scenes.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$videoVoice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$videoVoice.SelectVoice('Microsoft Zira Desktop')
$videoVoice.Rate = 0
$videoVoice.Volume = 100
$videoSegments = New-Object System.Collections.Generic.List[object]
try {
    foreach ($videoScene in $videoScenes) {
        $videoSentences = [regex]::Split($videoScene.text, '(?<=[.!?])\s+')
        $videoSentenceIndex = 0
        foreach ($videoSentence in $videoSentences) {
            $videoSentenceIndex += 1
            $videoAudioName = '{0}-{1:D2}.wav' -f $videoScene.id, $videoSentenceIndex
            $videoAudioPath = Join-Path (Join-Path $videoRoot 'audio') $videoAudioName
            $videoVoice.SetOutputToWaveFile($videoAudioPath)
            $videoVoice.Speak($videoSentence)
            $videoVoice.SetOutputToNull()
            $videoSegments.Add([ordered]@{scene=$videoScene.id; file=$videoAudioName; text=$videoSentence})
        }
        Write-Output ('Narrated chapter ' + $videoScene.id)
    }
    $videoSegments | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $videoRoot 'segments.json') -Encoding UTF8
}
finally {
    $videoVoice.Dispose()
}
