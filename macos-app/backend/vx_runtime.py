"""Relocatable runtime locations, separate bundled tools from writable user data."""
import os
import sys
from pathlib import Path

def configure(resources=None):
    if resources is None:
        resources = Path(__file__).resolve().parents[1]
    resources = Path(resources)
    bundled = resources / 'runtime'
    if not bundled.is_dir():
        return False
    data = (Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Shiying' if os.name == 'nt'
            else Path.home() / 'Library/Application Support/拾影')
    data.mkdir(parents=True, exist_ok=True)
    os.environ['VX_HOME'] = str(data)
    os.environ['VX_BIN'] = str(resources / 'tools')
    os.environ['PATH'] = os.pathsep.join([str(resources/'tools'), str(bundled/'Scripts'), str(bundled/'bin'), str(bundled), os.environ.get('PATH','')])
    os.environ.setdefault('HF_HOME', str(data/'models/huggingface'))
    os.environ.setdefault('MODELSCOPE_CACHE', str(data/'models/modelscope'))
    import truststore
    truststore.inject_into_ssl()
    os.environ['PYTHONNOUSERSITE'] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    return True
