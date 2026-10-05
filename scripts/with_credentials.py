"""Launch a command with credentials from an explicitly selected private local file."""
import json
import os
import stat
import sys
from pathlib import Path
from voice import KEY_ENV


def environment(path):
    # Explicit opt-in only; never search the filesystem for credentials.
    with Path(path).open() as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise ValueError('Credential file must be owned by this user and have mode 0600')
        values=json.load(stream)
    if not isinstance(values,dict) or set(values)!={KEY_ENV}:
        raise ValueError('Credential file must contain only DOUBAO_API_KEY')
    value=values.get(KEY_ENV)
    if not isinstance(value,str) or not value.strip() or '\n' in value:
        raise ValueError('Credential file requires DOUBAO_API_KEY')
    env=dict(os.environ)
    env.setdefault(KEY_ENV,value.strip())
    return env


if __name__=='__main__':
    if len(sys.argv)<3:
        sys.exit('Usage: with_credentials.py /private/credentials.json command [arguments...]')
    try:
        env=environment(sys.argv[1])
        os.execvpe(sys.argv[2],sys.argv[2:],env)
    except (OSError,ValueError):
        sys.exit('Cannot load private credentials or launch command; verify file ownership, mode 0600 and documented JSON format')
