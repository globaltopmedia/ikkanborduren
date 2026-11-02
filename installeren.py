"""Run on Windows: py installeren.py. Keeps version 1 and existing projects."""
from pathlib import Path
import os,sys,shutil,subprocess

def install():
    if os.name!='nt':raise RuntimeError('Dit installatieprogramma is voor Windows.')
    if not (3,11)<=sys.version_info[:2]<(3,15):raise RuntimeError('Gebruik Python 3.11, 3.12, 3.13 of 3.14 (64-bit).')
    source=Path(__file__).resolve().parent;home=Path(os.environ['USERPROFILE']);target=home/'Ikkanborduren';venv=home/'bsenv'
    print('Ikkanborduren wordt geplaatst in '+str(target),flush=True)
    print('Je eerdere versie en opgeslagen projecten blijven behouden.',flush=True)
    if source!=target:
        shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.venv','__pycache__','.pytest_cache','*.pyc','foutmelding.txt'))
    python_exe=venv/'Scripts'/'python.exe'
    if not python_exe.exists():subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
    result=subprocess.run([str(python_exe),'-c','import PySide6,PIL,numpy,scipy,contourpy,pyembroidery'],capture_output=True)
    if result.returncode:
        subprocess.run([str(python_exe),'-m','pip','install','-r',str(target/'requirements.txt')],check=True)
    sys.path.insert(0,str(target));from windows_setup import make_shortcut
    try:print('Snelkoppeling gemaakt: '+make_shortcut(python_exe,target/'launch.py'),flush=True)
    except Exception as e:
        print('De snelkoppeling kon niet worden gemaakt: '+str(e),flush=True)
        print('Start handmatig met deze opdracht:\n"'+str(python_exe)+'" "'+str(target/'main.py')+'"',flush=True)
    print('Ikkanborduren starten...',flush=True)
    subprocess.Popen([str(python_exe.with_name('pythonw.exe')),str(target/'launch.py')],cwd=target)

if __name__=='__main__':
    try:install()
    except Exception as e:
        print('Installatie niet voltooid: '+str(e),flush=True);sys.exit(1)
