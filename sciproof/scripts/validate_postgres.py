"""Run tests against a temporary loopback-only portable PostgreSQL server.

No system service is installed. Test data remains in ignored .runtime/.
"""
import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bin-dir',required=True)
    args=parser.parse_args();binary=Path(args.bin_dir).resolve()
    runtime=Path('.runtime').resolve();runtime.mkdir(exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='pg-test-',dir=runtime))
    password=secrets.token_hex(24);pwfile=folder/'password';pwfile.write_text(password);pwfile.chmod(0o600)
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    def run(name,*args): return subprocess.run([str(binary/name),*map(str,args)],check=True,**flags)
    suffix='.exe' if os.name=='nt' else ''
    run('initdb'+suffix,'-D',folder/'data','-U','sciproof','--pwfile',pwfile,'--auth-host=scram-sha-256','--auth-local=trust','--encoding=UTF8')
    pwfile.unlink()
    with socket.socket() as sock: sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    logfile=(folder/'postgres.log').open('w')
    process=subprocess.Popen([str(binary/('postgres'+suffix)),'-D',str(folder/'data'),'-h','127.0.0.1','-p',str(port)],stdout=logfile,stderr=subprocess.STDOUT,**flags)
    try:
        import psycopg
        for _ in range(60):
            try:
                with psycopg.connect(host='127.0.0.1',port=port,user='sciproof',password=password,dbname='postgres',autocommit=True) as db:
                    db.execute('CREATE DATABASE sciproof_test')
                break
            except psycopg.OperationalError:
                if process.poll() is not None: raise RuntimeError('PostgreSQL startup failed; inspect runtime log')
                time.sleep(.5)
        else: raise RuntimeError('PostgreSQL startup timed out')
        env=os.environ.copy();env['TEST_POSTGRES_URL']=f'postgresql+psycopg://sciproof:{password}@127.0.0.1:{port}/sciproof_test'
        env['DATABASE_URL']=env['TEST_POSTGRES_URL']
        result=subprocess.run([sys.executable,'-m','pytest','tests/test_postgres.py','-q'],env=env)
        if result.returncode==0:
            for command in ('heads','current','history'):
                subprocess.run([sys.executable,'-m','alembic',command],env=env,check=True)
        return result.returncode
    finally:
        try: run('pg_ctl'+suffix,'-D',folder/'data','stop','-m','fast','-w')
        finally: logfile.close()

if __name__=='__main__': raise SystemExit(main())
