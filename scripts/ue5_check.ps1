<#
.SYNOPSIS
  Package a UE5 Shipping build and confirm IndieWard's trap markers survived.

.DESCRIPTION
  0. Checks that the vault has a verified store link (`indieward status`) and stops if not.
  1. Checks that the trap files from `indieward traps new --engine ue5` are in your
     game module and that something calls <Class>::Touch().
  2. Runs RunUAT BuildCookRun (Shipping, staged + archived to -ArchiveDir).
  3. Runs `indieward build register` on the archived build and reports the result.

  Without -Apply the script never writes to your project's Source/, Content/ or
  Config/ folders. If the trap files are missing it tells you where they go and
  stops. With -Apply it copies the generated .h/.cpp into Source/<Module>/ (it
  never edits your GameInstance; it prints the line to add).

  Unreal itself still writes its usual build caches (Binaries/, Intermediate/,
  Saved/, DerivedDataCache/) inside the project while packaging, as it does when
  you package from the editor.

  Nothing here touches the network or sends anything.

.EXAMPLE
  .\scripts\ue5_check.ps1 -UProject D:\Games\Parasomnia\Parasomnia.uproject -Build b1a2b3c4d5 -PrintOnly

.EXAMPLE
  .\scripts\ue5_check.ps1 -UProject D:\Games\Parasomnia\Parasomnia.uproject -Build b1a2b3c4d5 -Apply
#>
[CmdletBinding()]
param(
    # Your game's .uproject file.
    [Parameter(Mandatory = $true)] [string] $UProject,
    # Build id printed by `indieward traps new` (starts with "b").
    [Parameter(Mandatory = $true)] [string] $Build,
    # Unreal Engine root (the folder holding Engine\). Default: $env:UE_ROOT, then the newest
    # "C:\Program Files\Epic Games\UE_5.*".
    [string] $EngineRoot,
    # Folder holding the IndieWard vault (.indieward\). Default: the .uproject's folder.
    [string] $VaultDir,
    # Folder with the generated trap files. Default: <VaultDir>\.indieward\traps\<Build>.
    [string] $SnippetDir,
    # Game module that gets the .h/.cpp. Default: the .uproject's name.
    [string] $Module,
    # Where the packaged build is archived. Default: <project>\..\<Name>_IndieWard\<Build>.
    [string] $ArchiveDir,
    [string] $Platform = "Win64",
    [ValidateSet("Shipping", "Development", "DebugGame")] [string] $Config = "Shipping",
    # Command used to run IndieWard. Default: `indieward` on PATH, else `python -m indieward.cli`.
    [string] $IndieWard,
    # Copy the trap .h/.cpp into Source\<Module>\ if they're missing. Off by default.
    [switch] $Apply,
    # Print what would run. Only reads the vault (to check verification); changes nothing.
    [switch] $PrintOnly,
    # Skip packaging and only register an existing build in -ArchiveDir.
    [switch] $SkipPackage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string] $msg) { Write-Host "FAIL: $msg" -ForegroundColor Red; exit 1 }

# --- paths --------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $UProject -PathType Leaf)) { Fail "No .uproject at $UProject" }
$UProject = (Resolve-Path -LiteralPath $UProject).Path
$ProjectDir = Split-Path -Parent $UProject
$ProjectName = [IO.Path]::GetFileNameWithoutExtension($UProject)
if (-not $Module) { $Module = $ProjectName }
if (-not $VaultDir) { $VaultDir = $ProjectDir }
if (-not (Test-Path -LiteralPath (Join-Path $VaultDir ".indieward\vault.db"))) {
    Fail "No IndieWard vault in $VaultDir. Run ``indieward init`` there, or pass -VaultDir."
}
if (-not $SnippetDir) { $SnippetDir = Join-Path $VaultDir ".indieward\traps\$Build" }
if (-not $ArchiveDir) { $ArchiveDir = Join-Path (Split-Path -Parent $ProjectDir) "$($ProjectName)_IndieWard\$Build" }

if (-not $EngineRoot) { $EngineRoot = $env:UE_ROOT }
if (-not $EngineRoot) {
    $cand = Get-ChildItem -Path "C:\Program Files\Epic Games" -Directory -Filter "UE_5.*" -ErrorAction SilentlyContinue |
        Sort-Object { [version]($_.Name -replace '^UE_', '') } -Descending | Select-Object -First 1
    if ($cand) { $EngineRoot = $cand.FullName }
}
$RunUAT = if ($EngineRoot) { Join-Path $EngineRoot "Engine\Build\BatchFiles\RunUAT.bat" } else { $null }
if (-not $SkipPackage -and -not ($RunUAT -and (Test-Path -LiteralPath $RunUAT))) {
    Fail "Can't find RunUAT.bat. Pass -EngineRoot 'C:\Program Files\Epic Games\UE_5.4' or set UE_ROOT."
}

if ($IndieWard) { $IW = @($IndieWard -split ' ') }
elseif (Get-Command indieward -ErrorAction SilentlyContinue) { $IW = @("indieward") }
else { $IW = @("python", "-m", "indieward.cli") }

# --- 0. verified store link ---------------------------------------------------
# Trapping and packaging need a verified store link, same as the rest of IndieWard. Check it before
# anything is copied into the project or packaged (local vault read; no network).
$stRaw = & $IW[0] @(@($IW | Select-Object -Skip 1) + @("--json", "-C", $VaultDir, "status"))
if ($LASTEXITCODE -ne 0) { Fail "indieward status failed (exit $LASTEXITCODE)." }
$st = ($stRaw -join "`n") | ConvertFrom-Json
if (-not $st.verified) {
    Fail "This vault has no verified store link yet. Run ``indieward status`` and follow its next step, then re-run this script."
}

Write-Host "Project : $UProject"
Write-Host "Module  : $Module"
Write-Host "Vault   : $VaultDir"
Write-Host "Traps   : $SnippetDir"
Write-Host "Archive : $ArchiveDir"
Write-Host "Engine  : $EngineRoot"

# --- 1. trap files in the module ----------------------------------------------
$ModuleDir = Join-Path $ProjectDir "Source\$Module"
if (-not (Test-Path -LiteralPath $ModuleDir -PathType Container)) {
    Fail "No module folder $ModuleDir. Blueprint-only projects: add a C++ class first (Tools > New C++ Class), or pass -Module."
}
$Generated = @(Get-ChildItem -LiteralPath (Join-Path $SnippetDir "Source") -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in ".h", ".cpp" })
if ($Generated.Count -ne 2) {
    Fail "No generated .h/.cpp in $SnippetDir\Source. Run: indieward traps new --label `"<version>`" --engine ue5"
}
$Class = [IO.Path]::GetFileNameWithoutExtension($Generated[0].Name)

$missing = @()
foreach ($g in $Generated) {
    $found = @(Get-ChildItem -LiteralPath $ModuleDir -Recurse -File -Filter $g.Name -ErrorAction SilentlyContinue)
    if ($found.Count -eq 0) { $missing += $g }
    elseif ((Get-FileHash -LiteralPath $found[0].FullName).Hash -ne (Get-FileHash -LiteralPath $g.FullName).Hash) {
        Write-Host "WARN: $($found[0].FullName) differs from the generated $($g.Name). Is it from another build?" -ForegroundColor Yellow
    }
}
if ($missing.Count -gt 0) {
    if (-not $Apply) {
        Write-Host "Trap files are not in $ModuleDir yet:" -ForegroundColor Yellow
        $missing | ForEach-Object { Write-Host "  $($_.FullName)" }
        Fail "Copy them into $ModuleDir yourself, or re-run with -Apply to have this script copy them."
    }
    foreach ($g in $missing) {
        $dest = Join-Path $ModuleDir $g.Name
        if ($PrintOnly) { Write-Host "Would copy $($g.FullName) -> $dest" }
        else { Copy-Item -LiteralPath $g.FullName -Destination $dest; Write-Host "Copied $($g.Name) -> $ModuleDir" }
    }
}

$touch = @(Get-ChildItem -LiteralPath $ModuleDir -Recurse -File -Include *.cpp, *.h -ErrorAction SilentlyContinue |
    Select-String -SimpleMatch "${Class}::Touch()" | Where-Object { $_.Path -notlike "*\$Class.cpp" })
if ($touch.Count -eq 0) {
    Write-Host "WARN: nothing in $ModuleDir calls ${Class}::Touch(). Add to your GameInstance's Init():" -ForegroundColor Yellow
    Write-Host "         #include `"$Class.h`"        (top of the GameInstance .cpp)"
    Write-Host "         ${Class}::Touch();            (inside Init(), after Super::Init())"
    Write-Host "      The strings usually survive anyway, but the call keeps the linker from dropping them."
}

# --- 2. package ---------------------------------------------------------------
$uat = @("BuildCookRun", "-project=$UProject", "-noP4", "-platform=$Platform", "-clientconfig=$Config",
    "-build", "-cook", "-stage", "-pak", "-prereqs", "-archive", "-archivedirectory=$ArchiveDir", "-unattended", "-utf8output")
if ($SkipPackage) {
    Write-Host "Skipping packaging (-SkipPackage)."
}
elseif ($PrintOnly) {
    Write-Host "Would run: `"$RunUAT`" $($uat -join ' ')"
}
else {
    Write-Host "Packaging ($Config, $Platform). This takes a while..."
    & $RunUAT @uat
    if ($LASTEXITCODE -ne 0) { Fail "RunUAT BuildCookRun failed with exit code $LASTEXITCODE (see the log above)." }
}

# --- 3. register --------------------------------------------------------------
$iwArgs = @("--json", "-C", $VaultDir, "build", "register", "--build", $Build, $ArchiveDir)
$iwCmd = $IW[0]
$iwRest = @($IW | Select-Object -Skip 1) + $iwArgs
if ($PrintOnly) {
    Write-Host "Would run: $($IW -join ' ') $($iwArgs -join ' ')"
    exit 0
}
if (-not (Test-Path -LiteralPath $ArchiveDir)) { Fail "No packaged build at $ArchiveDir" }
$raw = & $iwCmd @iwRest
if ($LASTEXITCODE -ne 0) { Fail "indieward build register failed (exit $LASTEXITCODE)." }
$res = ($raw -join "`n") | ConvertFrom-Json

Write-Host ""
Write-Host "Files scanned : $($res.files_scanned)"
Write-Host "Traps found   : $($res.found) of $($res.of)"
foreach ($m in $res.missing) { Write-Host "  not found   : $($m.label) ($($m.tier))" }
if ($res.ok) {
    Write-Host "PASS: traps survived. Build $Build is registered (manifest $($res.manifest_sha256))." -ForegroundColor Green
    Write-Host "Before you upload, make sure README_INDIEWARD.txt is not in the build."
    exit 0
}
Fail "Not enough traps survived. $($res.advice)"
