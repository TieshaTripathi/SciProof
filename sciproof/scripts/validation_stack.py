"""Isolated Linux services for actual broker and browser validation.

All binaries, state and logs live under ignored .runtime/. No system service.
"""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import psycopg
import redis
from cryptography.fernet import Fernet

def available_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

class ValidationStack:
    def __init__(self,api_port=None):
        self.project=Path(__file__).resolve().parents[1]
        self.binary_root=self.project/'.runtime/linux/root'
        # Native temporary filesystem is required for PostgreSQL permissions on WSL.
        self.folder=Path(tempfile.mkdtemp(prefix='sciproof-stack-'))
        (self.project/'.runtime/linux/last-stack.txt').write_text(str(self.folder),encoding='utf-8')
        self.pg_port=available_port();self.redis_port=available_port();self.api_port=api_port or available_port()
        self.pg_password=secrets.token_hex(24);self.redis_password=secrets.token_hex(24)
        self.env=os.environ.copy()
        self.env.update(DATABASE_URL=f'postgresql+psycopg://sciproof:{self.pg_password}@127.0.0.1:{self.pg_port}/sciproof_test',
            REDIS_URL=f'redis://:{self.redis_password}@127.0.0.1:{self.redis_port}/0',
            STORAGE_ROOT=str(self.folder/'artifacts'),STORAGE_ENCRYPTION_KEY=Fernet.generate_key().decode(),
            VERIFICATION_MODE='celery',APP_ENV='development',WEB_ORIGIN='http://localhost:3000',
            LD_LIBRARY_PATH=str(self.binary_root/'usr/lib/x86_64-linux-gnu'))
        self.processes={};self.logs=[]
    def start(self,name,args):
        stream=(self.folder/(name+'.log')).open('a');self.logs.append(stream)
        process=subprocess.Popen(list(map(str,args)),cwd=self.project,env=self.env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        self.processes[name]=process;return process
    def stop(self,name):
        process=self.processes.pop(name,None)
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)
    def wait(self,check,seconds=60):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:
                if check(): return
            except Exception: pass
            time.sleep(.1)
        raise TimeoutError('Service did not become ready; inspect isolated runtime logs')
    def start_redis(self):
        config=self.folder/'redis.conf'
        config.write_text(f'bind 127.0.0.1\nprotected-mode yes\nport {self.redis_port}\nrequirepass {self.redis_password}\ndir {self.folder}\nappendonly yes\n')
        config.chmod(0o600)
        self.start('redis',[self.binary_root/'usr/bin/redis-server',config])
        self.wait(lambda:self.redis_client().ping())
    def redis_client(self): return redis.Redis.from_url(self.env['REDIS_URL'],socket_timeout=1)
    def start_worker(self):
        self.start('worker',[sys.executable,'-m','celery','-A','apps.api.tasks:celery','worker','--loglevel=INFO','--concurrency=2','--hostname=validation@%h'])
    def start_beat(self):
        self.start('beat',[sys.executable,'-m','celery','-A','apps.api.tasks:celery','beat','--loglevel=INFO','--schedule',self.folder/'beat'])
    def __enter__(self):
        try: return self.start_services()
        except Exception:
            self.__exit__();raise
    def start_services(self):
        pg_bin=self.binary_root/'usr/lib/postgresql/16/bin'
        pwfile=self.folder/'pg-password';pwfile.write_text(self.pg_password);pwfile.chmod(0o600)
        init=subprocess.run([str(pg_bin/'initdb'),'-D',str(self.folder/'pgdata'),'-U','sciproof','--pwfile',str(pwfile),
            '--auth-host=scram-sha-256','--auth-local=trust','--encoding=UTF8'],env=self.env,capture_output=True,text=True)
        pwfile.unlink()
        if init.returncode: raise RuntimeError('initdb failed: '+init.stderr)
        self.start('postgres',[pg_bin/'postgres','-D',self.folder/'pgdata','-h','127.0.0.1','-p',self.pg_port,'-k',self.folder])
        def create_db():
            with psycopg.connect(host='127.0.0.1',port=self.pg_port,user='sciproof',password=self.pg_password,dbname='postgres',autocommit=True) as db: db.execute('CREATE DATABASE sciproof_test')
            return True
        self.wait(create_db)
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=self.env,cwd=self.project,check=True)
        self.start_redis()
        self.start('api',[sys.executable,'-m','uvicorn','apps.api.main:app','--host','127.0.0.1','--port',self.api_port])
        import httpx
        self.wait(lambda:httpx.get(self.api_url+'/health/ready').status_code==200)
        return self
    @property
    def api_url(self): return f'http://127.0.0.1:{self.api_port}'
    def __exit__(self,*args):
        for name in ('beat','worker','api','redis','postgres'): self.stop(name)
        for stream in self.logs: stream.close()
