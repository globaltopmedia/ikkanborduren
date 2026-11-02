$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
& py -3.13 installeren.py
if ($LASTEXITCODE -ne 0) { throw 'Installatie niet voltooid. Zie de melding hierboven.' }
