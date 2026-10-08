"""Startup validation without network calls or secret-bearing diagnostics."""
import os
from urllib.parse import urlparse
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url
from apps.api.database import DEFAULT_URL
from packages.verification.engine import scoring_weights

def validate_configuration(database_url=None,execution_mode=None,storage=None):
    environment=os.getenv('APP_ENV','development')
    if environment not in ('development','test','production'): raise ValueError('Invalid APP_ENV')
    production=environment=='production'
    try: database=make_url(database_url or os.getenv('DATABASE_URL',DEFAULT_URL))
    except Exception: raise ValueError('Invalid DATABASE_URL') from None
    if production and database.get_backend_name()!='postgresql': raise ValueError('Production DATABASE_URL requires PostgreSQL')
    mode=execution_mode or os.getenv('VERIFICATION_MODE','celery')
    if mode not in ('celery','inline','manual') or production and mode!='celery': raise ValueError('Invalid VERIFICATION_MODE for environment')
    origin=urlparse(os.getenv('WEB_ORIGIN','http://localhost:3000'))
    if origin.scheme not in ('http','https') or not origin.netloc or origin.username or origin.password or origin.path not in ('','/') or origin.query or origin.fragment:
        raise ValueError('WEB_ORIGIN must be an explicit HTTP(S) origin')
    if production and (origin.scheme!='https' or os.getenv('SECURE_COOKIES','false')!='true'): raise ValueError('Production requires HTTPS WEB_ORIGIN and SECURE_COOKIES=true')
    for flag in ('SECURE_COOKIES','AI_ENABLED','AI_ALLOW_PRIVATE','IPFS_ENABLED','BLOCKCHAIN_ENABLED'):
        if os.getenv(flag,'false') not in ('true','false'): raise ValueError('Invalid boolean flag: '+flag)
    key=os.getenv('STORAGE_ENCRYPTION_KEY')
    if key:
        try: Fernet(key)
        except Exception: raise ValueError('Invalid STORAGE_ENCRYPTION_KEY') from None
    elif production and storage is None: raise ValueError('STORAGE_ENCRYPTION_KEY required in production')
    backend=os.getenv('STORAGE_BACKEND','local_encrypted')
    if backend not in ('local_encrypted','s3_encrypted'): raise ValueError('Invalid STORAGE_BACKEND')
    if backend=='s3_encrypted':
        if not key or not os.getenv('S3_BUCKET'): raise ValueError('S3 requires S3_BUCKET and STORAGE_ENCRYPTION_KEY')
        endpoint=os.getenv('S3_ENDPOINT_URL')
        if endpoint:
            parsed=urlparse(endpoint)
            if parsed.scheme!='https' and not (not production and parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):
                raise ValueError('S3 endpoint requires HTTPS or local development HTTP')
    if mode=='celery':
        redis=urlparse(os.getenv('REDIS_URL','redis://localhost:6379/0'))
        if redis.scheme not in ('redis','rediss') or not redis.hostname: raise ValueError('Invalid REDIS_URL')
        if production and not redis.password: raise ValueError('Production Redis requires authentication')
    task_key=os.getenv('TASK_SIGNING_KEY')
    if task_key and len(task_key)<32: raise ValueError('TASK_SIGNING_KEY must have at least 32 characters')
    scoring_weights()
    return mode
