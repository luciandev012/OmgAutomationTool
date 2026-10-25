param([Parameter(Mandatory=$true)][string]$ImagePath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asyncMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and
    $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-Operation($Operation, [Type]$ResultType) {
    $task = $asyncMethod.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(12000)) { throw 'Windows OCR operation timed out' }
    return $task.Result
}
$fileType = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$streamType = [Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$decoderType = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$bitmapType = [Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$resultType = [Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
$file = Await-Operation ($fileType::GetFileFromPathAsync($ImagePath)) $fileType
$stream = Await-Operation ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) $streamType
$bitmap = $null
try {
    $decoder = Await-Operation ($decoderType::CreateAsync($stream)) $decoderType
    $bitmap = Await-Operation ($decoder.GetSoftwareBitmapAsync()) $bitmapType
    $language = [Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]::new('en-US')
    $engine = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]::TryCreateFromLanguage($language)
    if ($null -eq $engine) { throw 'English Windows OCR language is unavailable' }
    $result = Await-Operation ($engine.RecognizeAsync($bitmap)) $resultType
    @{text=$result.Text;words=@($result.Lines | ForEach-Object { $_.Words | ForEach-Object { @{text=$_.Text;x=[double]$_.BoundingRect.X;y=[double]$_.BoundingRect.Y;w=[double]$_.BoundingRect.Width;h=[double]$_.BoundingRect.Height} }})} | ConvertTo-Json -Compress -Depth 6
} finally {
    if ($null -ne $bitmap) { $bitmap.Dispose() }
    $stream.Dispose()
}
