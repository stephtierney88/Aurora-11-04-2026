import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReferenceRegenerationTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "PowerShell wrapper regression")
    def test_generator_failures_stop_before_mirror_sync(self):
        # Extract the real function without running either generator or writing maps.
        harness = r'''
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PWD 'regenerate_aurora_skill_refs.ps1'),
    [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Wrapper did not parse' }
$pythonAssignment = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
    $node.Left.VariablePath.UserPath -eq 'python'
}, $true)
if (-not $pythonAssignment) { throw 'Interpreter selection not found' }
$savedPython = $env:AURORA_PYTHON
try {
    foreach ($override in @('', 'C:\Aurora Test Runtime\python.exe')) {
        $env:AURORA_PYTHON = $override
        . ([scriptblock]::Create($pythonAssignment.Extent.Text))
        $expectedPython = if ($override) { $override } else { 'C:\Anaconda\envs\aurora\python.exe' }
        if ($python -ne $expectedPython) { throw 'Incorrect interpreter selection' }
    }
} finally { $env:AURORA_PYTHON = $savedPython }
$function = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Invoke-Regeneration'
}, $true)
if (-not $function) { throw 'Regeneration function not found' }
. ([scriptblock]::Create($function.Extent.Text))
$python = 'Test-Generator'
$generatorScript = 'references'
$Force = $true
$Check = $false
$SyncSkills = $true
function Test-Generator {
    param($Generator)
    $script:Calls += $Generator
    $global:LASTEXITCODE = if ($Generator -eq $script:FailAt) { 17 } else { 0 }
}
function Sync-InstalledSkillReferences { $script:Synced = $true }
foreach ($failure in @('references', 'none')) {
    $script:FailAt = $failure
    $script:Calls = @()
    $script:Synced = $false
    $caught = ''
    try { Invoke-Regeneration } catch { $caught = $_.Exception.Message }
    if ($failure -eq 'none') {
        if ($caught -or -not $script:Synced) { throw 'Successful generation did not sync' }
    } else {
        if ($script:Synced -or $caught -notlike '*exit 17*') {
            throw "Failure at $failure did not stop before mirror sync"
        }
    }
    $expected = 'references'
    if (($script:Calls -join ',') -ne $expected) { throw 'Incorrect generator call order' }
}
Write-Output 'regeneration-failure-paths-ok'
'''
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", harness],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("regeneration-failure-paths-ok", completed.stdout)


if __name__ == "__main__":
    unittest.main()
