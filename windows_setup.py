"""User-level Windows installer and desktop shortcut. No security settings changed."""
from pathlib import Path
import os,subprocess,sys

def ps_literal(value):return "'"+str(value).replace("'","''")+"'"

def make_shortcut(python_exe,entry):
    python_exe=Path(python_exe);pythonw=python_exe.with_name('pythonw.exe')
    if not pythonw.exists():pythonw=python_exe
    # Use the Windows Desktop known folder, including OneDrive redirection.
    script="$desktop=[Environment]::GetFolderPath('Desktop'); $shell=New-Object -ComObject WScript.Shell; $link=$shell.CreateShortcut((Join-Path $desktop 'BorduurStudio 2.lnk')); "
    script+="$link.TargetPath="+ps_literal(pythonw)+"; $link.Arguments="+ps_literal('"'+str(entry)+'"')+"; "
    script+="$link.WorkingDirectory="+ps_literal(Path(entry).parent)+"; $link.Description='BorduurStudio 2 - tekenen en borduren'; $link.Save(); Write-Output (Join-Path $desktop 'BorduurStudio 2.lnk')"
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,check=True)
    return result.stdout.strip()
