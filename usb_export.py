"""Stage a complete design locally, then replace the destination as a recoverable batch."""
from pathlib import Path
import os,tempfile,shutil,uuid,re
import core

def safe_name(name):
    name=name.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',name):raise ValueError('Gebruik 1–40 letters, cijfers, streepjes of underscores voor de USB-bestandsnaam.')
    if name.upper() in {'CON','PRN','AUX','NUL'} or re.fullmatch(r'(COM|LPT)[1-9]',name.upper()):raise ValueError('Deze naam is gereserveerd door Windows.')
    return name

def save_bundle(pattern,directory,name,hoop_width,hoop_height,oval=False,margin=2,fmt='exp',image=None,palette=None,settings=None,overwrite=False):
    directory=Path(directory);name=safe_name(name)
    if not directory.is_dir():raise ValueError('De USB-map is niet beschikbaar. Sluit de stick opnieuw aan en kies de map.')
    with tempfile.TemporaryDirectory() as temporary:
        staging=Path(temporary);core.export_bundle(pattern,staging/(name+'.'+fmt),hoop_width,hoop_height,oval,margin,fmt)
        core.save_project(staging/(name+'.bst'),image,palette or [],pattern,settings or {})
        files=sorted(staging.iterdir());targets=[directory/f.name for f in files]
        if not overwrite and any(p.exists() for p in targets):raise FileExistsError('Er bestaat al een ontwerp met deze naam op de stick.')
        if shutil.disk_usage(directory).free<sum(p.stat().st_size for p in files)*2+65536:raise OSError('Er is onvoldoende vrije ruimte op de USB-stick.')
        token=uuid.uuid4().hex;pending=[];backups=[];installed=[]
        try:
            for source,target in zip(files,targets):
                if target.is_dir():raise IsADirectoryError(str(target))
                part=directory/('.'+target.name+'.'+token+'.tmp');pending.append(part)
                with source.open('rb') as src,part.open('wb') as dst:shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
            for part,target in zip(pending,targets):
                if target.exists():
                    backup=directory/('.'+target.name+'.'+token+'.bak');os.replace(target,backup);backups.append((backup,target))
                os.replace(part,target);installed.append(target)
        except Exception:
            for target in installed:target.unlink(missing_ok=True)
            for backup,target in reversed(backups):os.replace(backup,target)
            raise
        finally:
            for part in pending:part.unlink(missing_ok=True)
        for backup,target in backups:backup.unlink(missing_ok=True)
        return targets
