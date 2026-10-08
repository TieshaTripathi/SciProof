"""Place test Python dependencies on WSL's native temporary filesystem."""
from pathlib import Path
import subprocess
import tempfile
import sys
root=Path(__file__).resolve().parents[1]
venv=Path(tempfile.mkdtemp(prefix='sciproof-python-'))
subprocess.run(['python3','-m','venv','--without-pip',str(venv)],check=True)
python=venv/'bin/python'
subprocess.run([str(python),str(root/'.runtime/linux/pip.pyz'),'install','-r',str(root/'requirements.lock.txt')],check=True)
(root/'.runtime/linux/python-path.txt').write_text(str(python),encoding='utf-8')
print('Isolated Linux Python ready')

if '--validate-async' in sys.argv:
    subprocess.run([str(python),'-m','scripts.validate_async'],cwd=root,check=True)

if '--serve-e2e' in sys.argv:
    subprocess.run([str(python),'-m','scripts.serve_e2e'],cwd=root,check=True)
