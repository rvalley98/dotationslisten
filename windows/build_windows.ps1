# Builds the Windows app and its installer (Dotationslisten-Setup-<version>.exe).
#
#   powershell -ExecutionPolicy Bypass -File windows\build_windows.ps1
#
# Needs: Python 3.12 (python.org or "py" launcher), Tesseract from the UB Mannheim
# (winget install UB-Mannheim.TesseractOCR / choco install tesseract) and Inno Setup 6
# (winget install JRSoftware.InnoSetup / choco install innosetup).
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$Root = Split-Path $Here
$Build = Join-Path $Here "build"
$Dist = Join-Path $Here "dist"
$Version = (Get-Content (Join-Path $Root "VERSION") -Raw).Trim()
New-Item -ItemType Directory -Force $Build | Out-Null

function Download { param([string]$Url, [string]$OutFile)
    # GitHub answers 503 now and then - retry before failing the build
    for ($i = 1; ; $i++) {
        try { Invoke-WebRequest $Url -OutFile $OutFile -UseBasicParsing; return }
        catch { if ($i -ge 5) { throw }; Write-Host "Download fehlgeschlagen ($i/5), neuer Versuch: $Url"; Start-Sleep -Seconds (10 * $i) }
    }
}
function Run { param([string]$Exe, [string[]]$ArgList)
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($ArgList -join ' ') fehlgeschlagen ($LASTEXITCODE)" }
}

# --- Tesseract: the UB Mannheim build (exe + DLLs) plus German/orientation data and configs
$Tess = Join-Path $Build "tesseract"
if (-not (Test-Path (Join-Path $Tess "tesseract.exe"))) {
    $Installed = @($env:TESSERACT_DIR, "$env:ProgramFiles\Tesseract-OCR", "${env:ProgramFiles(x86)}\Tesseract-OCR",
                   "$env:LOCALAPPDATA\Programs\Tesseract-OCR") | Where-Object { $_ -and (Test-Path "$_\tesseract.exe") } | Select-Object -First 1
    if (-not $Installed) { throw "Tesseract nicht gefunden - bitte installieren (choco install tesseract)" }
    New-Item -ItemType Directory -Force "$Tess\tessdata" | Out-Null
    Copy-Item "$Installed\*.exe", "$Installed\*.dll" $Tess
    Remove-Item "$Tess\unins*.exe", "$Tess\*training*.exe", "$Tess\winpath.exe" -ErrorAction SilentlyContinue
    Get-ChildItem $Tess -Filter *.exe | Where-Object { $_.Name -ne "tesseract.exe" } | Remove-Item
    foreach ($d in "configs", "tessconfigs") { if (Test-Path "$Installed\tessdata\$d") { Copy-Item -Recurse "$Installed\tessdata\$d" "$Tess\tessdata\" } }
    foreach ($lang in "deu", "osd") {
        Download "https://github.com/tesseract-ocr/tessdata/raw/main/$lang.traineddata" "$Tess\tessdata\$lang.traineddata"
    }
    if (Test-Path "$Installed\doc\LICENSE") { Copy-Item "$Installed\doc\LICENSE" "$Build\tesseract-LICENSE.txt" }
}
if (-not (Test-Path "$Build\tesseract-LICENSE.txt")) {
    Download "https://raw.githubusercontent.com/tesseract-ocr/tesseract/main/LICENSE" "$Build\tesseract-LICENSE.txt"
}
Run "$Tess\tesseract.exe" @("--version")

# --- Python environment
$Venv = Join-Path $Build "venv"
$Py = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Py)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { Run "py" @("-3.12", "-m", "venv", $Venv) }
    else { Run "python" @("-m", "venv", $Venv) }
}
Run $Py @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
Run $Py @("-m", "pip", "install", "--quiet", "-r", "$Root\requirements.txt", "pyinstaller", "pystray")

# --- icons, version resource, licenses
Run $Py @("$Root\desktop\make_icons.py", $Build)
$v = ($Version.Split(".") + @("0", "0", "0"))[0..3] -join ", "
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v), prodvers=($v)),
  kids=[StringFileInfo([StringTable('040704B0', [
    StringStruct('CompanyName', 'Robin Valley'),
    StringStruct('FileDescription', 'Dotationslisten'),
    StringStruct('FileVersion', '$Version'),
    StringStruct('LegalCopyright', 'Copyright (c) Robin Valley. Alle Rechte vorbehalten.'),
    StringStruct('ProductName', 'Dotationslisten'),
    StringStruct('ProductVersion', '$Version')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])]
)
"@ | Set-Content -Encoding UTF8 "$Build\version_info.txt"
Run $Py @("$Root\desktop\collect_licenses.py", "$Build\THIRD_PARTY_LICENSES.txt",
          "Tesseract OCR (Windows-Build der UB Mannheim) und Sprachdaten (Apache-2.0)=$Build\tesseract-LICENSE.txt")

# Inno Setup reads .txt files as UTF-8 only with a BOM
foreach ($f in @(@("$Root\LICENSE", "$Build\LICENSE.txt"), @("$Here\INSTALLATION.txt", "$Build\INSTALLATION.txt"))) {
    Get-Content -Encoding UTF8 $f[0] | Set-Content -Encoding UTF8 $f[1]
}

# --- app
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
Run $Py @("-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
          "--distpath", $Dist, "--workpath", "$Build\pyinstaller", "$Here\Dotationslisten.spec")

# --- installer
$Iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { $Iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source }
if (-not $Iscc) { throw "Inno Setup 6 nicht gefunden (choco install innosetup)" }
Run $Iscc @("/Q", "/DAppVersion=$Version", "/DRoot=$Root", "/O$Dist", "$Here\Dotationslisten.iss")
Get-ChildItem $Dist -Filter *.exe | ForEach-Object { "Fertig: $($_.FullName) ($([math]::Round($_.Length / 1MB)) MB)" }
