# =====================================================================
# B-9 / D-086  --  B.2 POST-FLIGHT VERIFICATION  (V1..V13)
# STRICTLY READ-ONLY. No mutation, no --confirm, no writes, no git writes.
# Run from: C:\Users\User\Trading-startegy-ai
# =====================================================================

$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\User\Trading-startegy-ai'

$global:Status = [ordered]@{}
function Set-Res([string]$id, [string]$st) { $global:Status[$id] = $st }
function Hdr([string]$t) { Write-Host ""; Write-Host "=====================================================================";
                           Write-Host $t; Write-Host "=====================================================================" }

$TicksRoot   = 'data\ticks\XAUUSD'
$HoldoutRoot = 'data\holdout\XAUUSD'
$HoldMonths  = @('07','08','09','10','11','12')

$KnownHashes = [ordered]@{
  '07' = '17c8470097e26b04133b71a6fcd6881bf97dc55fafa512147411c3568e529557'
  '08' = '1904258acf1708a43fdeafd89ed51ad17a2735bcddb5ae13c0946ec596c19461'
  '09' = 'e4b541f5b9a52293384350236b5d0df5d548d70599cda86991b8b9192fc0b4cd'
  '10' = 'ce8189398198dcc82d94f85bf6ceee4d07f1fcbaa4a0ce3de6c0a03b0bfcb74a'
  '11' = '6eb167305684467f54984b11819873b852d5d093b55d68913817254ab37e1842'
  '12' = '268ca8c7347834e844341f5d8f17626c1d1e3ecef5e4ce937919eb0c068dc820'
}

Hdr "RO-GUARD (BEFORE)  --  repo state baseline"
Write-Host "PWD          : $((Get-Location).Path)"
Write-Host "git rev-parse HEAD:"
git rev-parse HEAD
Write-Host "git status --short (BEFORE):"
$RoBefore = (git status --short | Out-String)
Write-Host $RoBefore
Write-Host "--- end BEFORE baseline ---"

# ---------------------------------------------------------------------
Hdr "V1  --  0 parquet AND 0 sha256 for 2025/07..12 under data\ticks\XAUUSD"
$v1Hits = @()
foreach ($m in $HoldMonths) {
  foreach ($suffix in @("$m.parquet", "$m.parquet.sha256")) {
    $p = Join-Path $TicksRoot "2025\$suffix"
    $ex = Test-Path -LiteralPath $p
    Write-Host ("EVIDENCE  Test-Path {0,-46} = {1}" -f $p, $ex)
    if ($ex) { $v1Hits += $p }
  }
}
Write-Host "EVIDENCE  Directory listing of $TicksRoot\2025 :"
if (Test-Path -LiteralPath "$TicksRoot\2025") {
  Get-ChildItem -LiteralPath "$TicksRoot\2025" -File | Select-Object Name, Length | Format-Table -AutoSize | Out-String | Write-Host
} else {
  Write-Host "  (directory $TicksRoot\2025 does not exist)"
}
if (-not (Test-Path -LiteralPath $TicksRoot)) {
  Write-Host "STATUS: N/A  (data\ticks\XAUUSD does not exist -- cannot evaluate)"; Set-Res 'V1' 'N/A'
} elseif ($v1Hits.Count -eq 0) {
  Write-Host "STATUS: PASS  (0 hold-out-month files remain under data\ticks)"; Set-Res 'V1' 'PASS'
} else {
  Write-Host "STATUS: FAIL  ($($v1Hits.Count) hold-out file(s) still present: $($v1Hits -join ', '))"; Set-Res 'V1' 'FAIL'
}

# ---------------------------------------------------------------------
Hdr "V2  --  all 6 hold-out months present under data\holdout\XAUUSD\2025"
$v2Missing = @()
foreach ($m in $HoldMonths) {
  $p = Join-Path $HoldoutRoot "2025\$m.parquet"
  $ex = Test-Path -LiteralPath $p
  $sz = if ($ex) { (Get-Item -LiteralPath $p).Length } else { 'n/a' }
  Write-Host ("EVIDENCE  {0,-46} exists={1}  bytes={2}" -f $p, $ex, $sz)
  if (-not $ex) { $v2Missing += $p }
}
if (-not (Test-Path -LiteralPath $HoldoutRoot)) {
  Write-Host "STATUS: N/A  (data\holdout\XAUUSD does not exist)"; Set-Res 'V2' 'N/A'
} elseif ($v2Missing.Count -eq 0) {
  Write-Host "STATUS: PASS  (6/6 hold-out parquet files present)"; Set-Res 'V2' 'PASS'
} else {
  Write-Host "STATUS: FAIL  (missing: $($v2Missing -join ', '))"; Set-Res 'V2' 'FAIL'
}

# ---------------------------------------------------------------------
Hdr "V3  --  all 6 .sha256 sidecars present at destination"
$v3Missing = @()
foreach ($m in $HoldMonths) {
  $p = Join-Path $HoldoutRoot "2025\$m.parquet.sha256"
  $ex = Test-Path -LiteralPath $p
  $content = if ($ex) { (Get-Content -LiteralPath $p -Raw).Trim() } else { 'n/a' }
  Write-Host ("EVIDENCE  {0,-53} exists={1}" -f $p, $ex)
  Write-Host ("          recorded = {0}" -f $content)
  if (-not $ex) { $v3Missing += $p }
}
if (-not (Test-Path -LiteralPath $HoldoutRoot)) {
  Write-Host "STATUS: N/A  (data\holdout\XAUUSD does not exist)"; Set-Res 'V3' 'N/A'
} elseif ($v3Missing.Count -eq 0) {
  Write-Host "STATUS: PASS  (6/6 sidecars present)"; Set-Res 'V3' 'PASS'
} else {
  Write-Host "STATUS: FAIL  (missing: $($v3Missing -join ', '))"; Set-Res 'V3' 'FAIL'
}

# ---------------------------------------------------------------------
Hdr "V4  --  destination parquet hash == destination recorded sidecar hash"
$v4Bad = @(); $v4Skip = @()
foreach ($m in $HoldMonths) {
  $pq = Join-Path $HoldoutRoot "2025\$m.parquet"
  $sc = Join-Path $HoldoutRoot "2025\$m.parquet.sha256"
  if (-not (Test-Path -LiteralPath $pq) -or -not (Test-Path -LiteralPath $sc)) {
    Write-Host "EVIDENCE  2025-$m : SKIPPED (parquet exists=$(Test-Path -LiteralPath $pq), sidecar exists=$(Test-Path -LiteralPath $sc))"
    $v4Skip += $m; continue
  }
  $computed = (Get-FileHash -LiteralPath $pq -Algorithm SHA256).Hash.ToLower()
  $recorded = (Get-Content -LiteralPath $sc -Raw).Trim().ToLower()
  $ok = ($computed -eq $recorded)
  Write-Host "EVIDENCE  2025-$m"
  Write-Host "          computed = $computed"
  Write-Host "          recorded = $recorded"
  Write-Host "          match    = $ok"
  if (-not $ok) { $v4Bad += $m }
}
if ($v4Skip.Count -eq 6) {
  Write-Host "STATUS: N/A  (no destination file pairs available to compare)"; Set-Res 'V4' 'N/A'
} elseif ($v4Bad.Count -eq 0 -and $v4Skip.Count -eq 0) {
  Write-Host "STATUS: PASS  (6/6 destination hashes match their sidecars)"; Set-Res 'V4' 'PASS'
} elseif ($v4Bad.Count -eq 0) {
  Write-Host "STATUS: PARTIAL/NEEDS REVIEW  (matched where present, but skipped: $($v4Skip -join ', '))"; Set-Res 'V4' 'NEEDS REVIEW'
} else {
  Write-Host "STATUS: FAIL  (mismatch: $($v4Bad -join ', '))"; Set-Res 'V4' 'FAIL'
}

# ---------------------------------------------------------------------
Hdr "V5  --  33 Research months present under data\ticks\XAUUSD: exactly 2022/10 .. 2025/06, no holes"
$expected = @()
$y = 2022; $mm = 10
while ( ($y -lt 2025) -or (($y -eq 2025) -and ($mm -le 6)) ) {
  $expected += ('{0:0000}/{1:00}' -f $y, $mm)
  $mm++; if ($mm -gt 12) { $mm = 1; $y++ }
}
Write-Host "EVIDENCE  expected Research months (count=$($expected.Count)):"
Write-Host ("          " + ($expected -join ' '))

$actualTicks = @()
if (Test-Path -LiteralPath $TicksRoot) {
  $actualTicks = Get-ChildItem -LiteralPath $TicksRoot -Recurse -File |
    Where-Object { $_.Name -like '*.parquet' } |
    ForEach-Object { '{0}/{1}' -f $_.Directory.Name, $_.BaseName } |
    Sort-Object
}
Write-Host "EVIDENCE  actual .parquet months under data\ticks\XAUUSD (count=$($actualTicks.Count)):"
Write-Host ("          " + ($actualTicks -join ' '))
$v5Missing = @($expected | Where-Object { $actualTicks -notcontains $_ })
$v5Extra   = @($actualTicks | Where-Object { $expected -notcontains $_ })
Write-Host "EVIDENCE  missing vs expected : $(if($v5Missing.Count){$v5Missing -join ' '}else{'(none)'})"
Write-Host "EVIDENCE  extra   vs expected : $(if($v5Extra.Count){$v5Extra -join ' '}else{'(none)'})"
if (-not (Test-Path -LiteralPath $TicksRoot)) {
  Write-Host "STATUS: N/A  (data\ticks\XAUUSD does not exist)"; Set-Res 'V5' 'N/A'
} elseif ($actualTicks.Count -eq 33 -and $v5Missing.Count -eq 0 -and $v5Extra.Count -eq 0) {
  Write-Host "STATUS: PASS  (exactly 33 contiguous Research months 2022/10..2025/06)"; Set-Res 'V5' 'PASS'
} else {
  Write-Host "STATUS: FAIL  (count=$($actualTicks.Count), missing=$($v5Missing.Count), extra=$($v5Extra.Count))"; Set-Res 'V5' 'FAIL'
}

# ---------------------------------------------------------------------
Hdr "V6  --  HoldoutGuard blocks read without holdout_unlock"
$pyV6 = @'
import sys, traceback
from datetime import UTC, datetime
from pathlib import Path
sys.path.insert(0, ".")
from src.data.holdout import HoldoutGuard, XAUUSD_HOLDOUT_RANGE
from src.data.tick_store import HoldoutAccessDenied

probe = Path("V6_PROBE_MUST_NEVER_EXIST.jsonl")
print("probe log exists BEFORE :", probe.exists())
print("XAUUSD_HOLDOUT_RANGE    :", XAUUSD_HOLDOUT_RANGE.start, "..", XAUUSD_HOLDOUT_RANGE.end)
guard = HoldoutGuard(Path("data/holdout"), probe)
try:
    guard.load("XAUUSD",
               datetime(2025, 8, 1, tzinfo=UTC),
               datetime(2025, 9, 1, tzinfo=UTC),
               XAUUSD_HOLDOUT_RANGE)
    print("V6_RESULT=FAIL  (guard.load returned WITHOUT raising)")
except HoldoutAccessDenied as e:
    print("V6_RESULT=PASS  HoldoutAccessDenied:", e)
except Exception as e:
    print("V6_RESULT=NEEDSREVIEW  unexpected", type(e).__name__, ":", e)
    traceback.print_exc()
print("probe log exists AFTER  :", probe.exists())
'@
$outV6 = ($pyV6 | uv run python - 2>&1 | Out-String)
Write-Host "EVIDENCE (raw python output):"
Write-Host $outV6
if     ($outV6 -match 'V6_RESULT=PASS')        { Write-Host "STATUS: PASS"; Set-Res 'V6' 'PASS' }
elseif ($outV6 -match 'V6_RESULT=FAIL')        { Write-Host "STATUS: FAIL"; Set-Res 'V6' 'FAIL' }
elseif ($outV6 -match 'V6_RESULT=NEEDSREVIEW') { Write-Host "STATUS: NEEDS REVIEW"; Set-Res 'V6' 'NEEDS REVIEW' }
else                                           { Write-Host "STATUS: N/A  (no result marker -- see raw output)"; Set-Res 'V6' 'N/A' }

# ---------------------------------------------------------------------
Hdr "V7  --  Track-A fail-closed enforcement still works on data\ticks"
$pyV7 = @'
import sys, traceback
from pathlib import Path
sys.path.insert(0, ".")
from src.data.holdout import XAUUSD_HOLDOUT_RANGE
from src.data.tick_store import HoldoutAccessDenied, TickParquetStore

checks = {}

store = TickParquetStore(Path("data/ticks"), holdout_range=XAUUSD_HOLDOUT_RANGE)
print("store.root           :", store.root)
print("store.holdout_range  :", store.holdout_range.start, "..", store.holdout_range.end)
print("store.holdout_unlock :", store.holdout_unlock)

# A) hold-out month must be DENIED
try:
    store.read_month("XAUUSD", 2025, 9)
    checks["A_holdout_denied"] = False
    print("A) read_month(2025,09) -> returned data  [UNEXPECTED]")
except HoldoutAccessDenied as e:
    checks["A_holdout_denied"] = True
    print("A) read_month(2025,09) -> HoldoutAccessDenied:", e)
except Exception as e:
    checks["A_holdout_denied"] = False
    print("A) read_month(2025,09) -> UNEXPECTED", type(e).__name__, ":", e)

# B) non-hold-out month must still be ALLOWED
try:
    df = store.read_month("XAUUSD", 2025, 6)
    checks["B_research_allowed"] = True
    print("B) read_month(2025,06) -> OK, rows =", df.height)
except Exception as e:
    checks["B_research_allowed"] = False
    print("B) read_month(2025,06) -> UNEXPECTED", type(e).__name__, ":", e)

# C) constructor without holdout_range must be impossible
try:
    TickParquetStore(Path("data/ticks"))
    checks["C_range_mandatory"] = False
    print("C) TickParquetStore(root) with no holdout_range -> CONSTRUCTED  [UNEXPECTED]")
except TypeError as e:
    checks["C_range_mandatory"] = True
    print("C) TickParquetStore(root) with no holdout_range -> TypeError:", e)

# D) unprotected() must require a reason
try:
    TickParquetStore.unprotected(Path("data/ticks"), reason="")
    checks["D_unprotected_needs_reason"] = False
    print("D) unprotected(reason='') -> CONSTRUCTED  [UNEXPECTED]")
except ValueError as e:
    checks["D_unprotected_needs_reason"] = True
    print("D) unprotected(reason='') -> ValueError:", e)

# E) holdout_unlock=True must require reason + usage_log_path
try:
    TickParquetStore(Path("data/ticks"), holdout_range=XAUUSD_HOLDOUT_RANGE, holdout_unlock=True)
    checks["E_unlock_needs_audit"] = False
    print("E) holdout_unlock=True with no reason/log -> CONSTRUCTED  [UNEXPECTED]")
except ValueError as e:
    checks["E_unlock_needs_audit"] = True
    print("E) holdout_unlock=True with no reason/log -> ValueError:", e)

print("CHECKS:", checks)
print("V7_RESULT=" + ("PASS" if all(checks.values()) else "FAIL"))
'@
$outV7 = ($pyV7 | uv run python - 2>&1 | Out-String)
Write-Host "EVIDENCE (raw python output):"
Write-Host $outV7
if     ($outV7 -match 'V7_RESULT=PASS') { Write-Host "STATUS: PASS"; Set-Res 'V7' 'PASS' }
elseif ($outV7 -match 'V7_RESULT=FAIL') { Write-Host "STATUS: FAIL"; Set-Res 'V7' 'FAIL' }
else                                    { Write-Host "STATUS: N/A  (no result marker -- see raw output)"; Set-Res 'V7' 'N/A' }

# ---------------------------------------------------------------------
Hdr "V8  --  explicit, independent 6/6 sidecar check under data\holdout"
$v8List = @()
if (Test-Path -LiteralPath 'data\holdout') {
  $v8List = Get-ChildItem -LiteralPath 'data\holdout' -Recurse -File |
    Where-Object { $_.Name -like '*.sha256' } | Sort-Object FullName
}
Write-Host "EVIDENCE  recursive scan of data\holdout for *.sha256 (count=$($v8List.Count)):"
foreach ($f in $v8List) { Write-Host ("          {0}   ({1} bytes)" -f $f.FullName, $f.Length) }
if (-not (Test-Path -LiteralPath 'data\holdout')) {
  Write-Host "STATUS: N/A  (data\holdout does not exist)"; Set-Res 'V8' 'N/A'
} elseif ($v8List.Count -eq 6) {
  Write-Host "STATUS: PASS  (exactly 6 sidecar files under data\holdout)"; Set-Res 'V8' 'PASS'
} else {
  Write-Host "STATUS: FAIL  (expected 6 sidecars, found $($v8List.Count))"; Set-Res 'V8' 'FAIL'
}

# ---------------------------------------------------------------------
Hdr "V9  --  explicit negation: ANY file for 2025/07..12 anywhere under data\ticks"
$v9Hits = @()
if (Test-Path -LiteralPath 'data\ticks') {
  $v9Hits = Get-ChildItem -LiteralPath 'data\ticks' -Recurse -File |
    Where-Object { $_.FullName -match '\\2025\\(07|08|09|10|11|12)\.parquet(\.sha256)?$' } |
    Sort-Object FullName
}
Write-Host "EVIDENCE  recursive scan of data\ticks for 2025\{07..12}.parquet[.sha256] :"
if ($v9Hits.Count -eq 0) { Write-Host "          (no matches -- 0 files)" }
else { foreach ($f in $v9Hits) { Write-Host ("          {0}" -f $f.FullName) } }
Write-Host "EVIDENCE  full recursive file count under data\ticks: $(@(Get-ChildItem -LiteralPath 'data\ticks' -Recurse -File -ErrorAction SilentlyContinue).Count)"
if (-not (Test-Path -LiteralPath 'data\ticks')) {
  Write-Host "STATUS: N/A  (data\ticks does not exist)"; Set-Res 'V9' 'N/A'
} elseif ($v9Hits.Count -eq 0) {
  Write-Host "STATUS: PASS  (0 hold-out-month artefacts remain under data\ticks)"; Set-Res 'V9' 'PASS'
} else {
  Write-Host "STATUS: FAIL  ($($v9Hits.Count) hold-out artefact(s) still under data\ticks)"; Set-Res 'V9' 'FAIL'
}

# ---------------------------------------------------------------------
Hdr "V10 --  counts: 33 Research parquet + 6 Hold-out parquet = 39, no holes, no duplicates"
$holdoutParquet = @()
if (Test-Path -LiteralPath 'data\holdout') {
  $holdoutParquet = Get-ChildItem -LiteralPath 'data\holdout' -Recurse -File |
    Where-Object { $_.Name -like '*.parquet' } |
    ForEach-Object { '{0}/{1}' -f $_.Directory.Name, $_.BaseName } | Sort-Object
}
Write-Host "EVIDENCE  Research parquet count (data\ticks)   : $($actualTicks.Count)"
Write-Host "EVIDENCE  Hold-out parquet count (data\holdout) : $($holdoutParquet.Count)"
Write-Host "EVIDENCE  Hold-out months: $($holdoutParquet -join ' ')"
$total = $actualTicks.Count + $holdoutParquet.Count
$overlap = @($actualTicks | Where-Object { $holdoutParquet -contains $_ })
$union = @(($actualTicks + $holdoutParquet) | Sort-Object -Unique)
Write-Host "EVIDENCE  33+6 arithmetic : $($actualTicks.Count) + $($holdoutParquet.Count) = $total"
Write-Host "EVIDENCE  duplicated months present in BOTH roots: $(if($overlap.Count){$overlap -join ' '}else{'(none)'})"
Write-Host "EVIDENCE  unique months across both roots        : $($union.Count)"
$expectedFull = @()
$y = 2022; $mm = 10
while ( ($y -lt 2025) -or (($y -eq 2025) -and ($mm -le 12)) ) {
  $expectedFull += ('{0:0000}/{1:00}' -f $y, $mm)
  $mm++; if ($mm -gt 12) { $mm = 1; $y++ }
}
$v10Missing = @($expectedFull | Where-Object { $union -notcontains $_ })
$v10Extra   = @($union | Where-Object { $expectedFull -notcontains $_ })
Write-Host "EVIDENCE  expected full span 2022/10..2025/12 count: $($expectedFull.Count)"
Write-Host "EVIDENCE  missing from union : $(if($v10Missing.Count){$v10Missing -join ' '}else{'(none)'})"
Write-Host "EVIDENCE  extra   in union   : $(if($v10Extra.Count){$v10Extra -join ' '}else{'(none)'})"
if ((-not (Test-Path -LiteralPath 'data\ticks')) -or (-not (Test-Path -LiteralPath 'data\holdout'))) {
  Write-Host "STATUS: N/A  (one of the two data roots is missing)"; Set-Res 'V10' 'N/A'
} elseif ($actualTicks.Count -eq 33 -and $holdoutParquet.Count -eq 6 -and $total -eq 39 -and
          $overlap.Count -eq 0 -and $union.Count -eq 39 -and $v10Missing.Count -eq 0 -and $v10Extra.Count -eq 0) {
  Write-Host "STATUS: PASS  (33 + 6 = 39, contiguous 2022/10..2025/12, no duplicates, no loss)"; Set-Res 'V10' 'PASS'
} else {
  Write-Host "STATUS: FAIL  (see counts above)"; Set-Res 'V10' 'FAIL'
}

# ---------------------------------------------------------------------
Hdr "V11 --  independent SHA256 recompute at destination vs KNOWN pre-move hashes"
$v11Bad = @(); $v11Skip = @()
foreach ($m in $HoldMonths) {
  $pq = Join-Path $HoldoutRoot "2025\$m.parquet"
  $known = $KnownHashes[$m]
  Write-Host "EVIDENCE  2025-$m"
  Write-Host ("          known(pre-move) = {0}   (len={1})" -f $known, $known.Length)
  if (-not (Test-Path -LiteralPath $pq)) {
    Write-Host "          computed        = (file not found: $pq)"
    Write-Host "          match           = N/A"
    $v11Skip += $m; continue
  }
  $computed = (Get-FileHash -LiteralPath $pq -Algorithm SHA256).Hash.ToLower()
  $ok = ($computed -eq $known)
  Write-Host ("          computed(dest)  = {0}   (len={1})" -f $computed, $computed.Length)
  Write-Host ("          match           = {0}" -f $ok)
  if (-not $ok) { $v11Bad += $m }
}
if ($v11Skip.Count -eq 6) {
  Write-Host "STATUS: N/A  (no destination parquet files found to recompute)"; Set-Res 'V11' 'N/A'
} elseif ($v11Bad.Count -eq 0 -and $v11Skip.Count -eq 0) {
  Write-Host "STATUS: PASS  (6/6 destination hashes byte-identical to known pre-move hashes)"; Set-Res 'V11' 'PASS'
} elseif ($v11Bad.Count -eq 0) {
  Write-Host "STATUS: NEEDS REVIEW  (matched where present; not evaluable: $($v11Skip -join ', '))"; Set-Res 'V11' 'NEEDS REVIEW'
} else {
  Write-Host "STATUS: FAIL  (hash mismatch: $($v11Bad -join ', '))"; Set-Res 'V11' 'FAIL'
}

# ---------------------------------------------------------------------
Hdr "V12 --  post-mutation: read_month(2025,07) and read_month(2025,12) must raise HoldoutAccessDenied"
$pyV12 = @'
import sys
from pathlib import Path
sys.path.insert(0, ".")
from src.data.holdout import XAUUSD_HOLDOUT_RANGE
from src.data.tick_store import HoldoutAccessDenied, TickParquetStore

store = TickParquetStore(Path("data/ticks"), holdout_range=XAUUSD_HOLDOUT_RANGE)
print("holdout_unlock (must be False):", store.holdout_unlock)

results = {}
for (y, m) in [(2025, 7), (2025, 12)]:
    try:
        df = store.read_month("XAUUSD", y, m)
        results[(y, m)] = False
        print(f"read_month({y},{m:02d}) -> RETURNED {df.height} rows  [UNEXPECTED]")
    except HoldoutAccessDenied as e:
        results[(y, m)] = True
        print(f"read_month({y},{m:02d}) -> HoldoutAccessDenied: {e}")
    except Exception as e:
        results[(y, m)] = False
        print(f"read_month({y},{m:02d}) -> UNEXPECTED {type(e).__name__}: {e}")

print("RESULTS:", results)
print("V12_RESULT=" + ("PASS" if all(results.values()) else "FAIL"))
'@
$outV12 = ($pyV12 | uv run python - 2>&1 | Out-String)
Write-Host "EVIDENCE (raw python output):"
Write-Host $outV12
if     ($outV12 -match 'V12_RESULT=PASS') { Write-Host "STATUS: PASS"; Set-Res 'V12' 'PASS' }
elseif ($outV12 -match 'V12_RESULT=FAIL') { Write-Host "STATUS: FAIL"; Set-Res 'V12' 'FAIL' }
else                                      { Write-Host "STATUS: N/A  (no result marker -- see raw output)"; Set-Res 'V12' 'N/A' }

# ---------------------------------------------------------------------
Hdr "V13 --  repeat DRY-RUN of run_separate_holdout.py (NO --confirm)"
Write-Host "COMMAND: uv run python scripts\tools\run_separate_holdout.py --ticks-dir data\ticks --holdout-dir data\holdout"
$outV13 = (uv run python scripts\tools\run_separate_holdout.py --ticks-dir data\ticks --holdout-dir data\holdout 2>&1 | Out-String)
$codeV13 = $LASTEXITCODE
Write-Host "EVIDENCE (raw output):"
Write-Host $outV13
Write-Host "EVIDENCE  exit code = $codeV13"
if ($outV13 -match 'already exists and is not empty') {
  Write-Host "STATUS: PASS  (Pre-Flight detected the already-separated destination and refused to move anything)"
  Set-Res 'V13' 'PASS'
} elseif ($outV13 -match 'expected exactly 39 months') {
  Write-Host "STATUS: NEEDS REVIEW  (runner still expects 39 months under data\ticks -- report to reviewer, NOT auto-PASS)"
  Set-Res 'V13' 'NEEDS REVIEW'
} elseif ($outV13 -match 'DRY-RUN') {
  Write-Host "STATUS: NEEDS REVIEW  (dry-run completed and would propose moving files again -- unexpected post-mutation)"
  Set-Res 'V13' 'NEEDS REVIEW'
} else {
  Write-Host "STATUS: NEEDS REVIEW  (unclassified output -- see raw output above)"
  Set-Res 'V13' 'NEEDS REVIEW'
}

# ---------------------------------------------------------------------
Hdr "RO-GUARD (AFTER)  --  proof nothing was written"
Write-Host "git status --short (AFTER):"
$RoAfter = (git status --short | Out-String)
Write-Host $RoAfter
Write-Host "V6 probe file must NOT exist: $(Test-Path -LiteralPath 'V6_PROBE_MUST_NEVER_EXIST.jsonl')"
if ($RoBefore -eq $RoAfter) { Write-Host "RO-GUARD: PASS  (git status identical before/after)" }
else { Write-Host "RO-GUARD: FAIL  (working tree changed during verification -- INVESTIGATE)" }

# ---------------------------------------------------------------------
Hdr "SUMMARY  --  B.2 POST-FLIGHT V1..V13"
foreach ($k in $Status.Keys) { Write-Host ("{0,-4} = {1}" -f $k, $Status[$k]) }
Write-Host ""
Write-Host ("PASS         : {0}" -f @($Status.Values | Where-Object { $_ -eq 'PASS' }).Count)
Write-Host ("FAIL         : {0}" -f @($Status.Values | Where-Object { $_ -eq 'FAIL' }).Count)
Write-Host ("NEEDS REVIEW : {0}" -f @($Status.Values | Where-Object { $_ -eq 'NEEDS REVIEW' }).Count)
Write-Host ("N/A          : {0}" -f @($Status.Values | Where-Object { $_ -eq 'N/A' }).Count)
Write-Host ""
Write-Host "END OF READ-ONLY POST-FLIGHT VERIFICATION"