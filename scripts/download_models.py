"""Download immutable public model snapshots and validate their LFS hashes."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

root=Path(sys.argv[1]).resolve()
os.environ['HF_HUB_DISABLE_XET']='1'
os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='180'
os.environ['HF_HOME']=str(root/'hf-cache')
from huggingface_hub import HfApi, snapshot_download
from timing import atomic_json

models={'align':'Qwen3-ForcedAligner-0.6B-8bit','asr':'Qwen3-ASR-0.6B-8bit'}
manifest=json.loads((root/'models.json').read_text()) if (root/'models.json').exists() else {}
manifest={kind:entry for kind,entry in manifest.items() if kind in models}
for kind,name in models.items():
    prior=manifest.get(kind)
    if prior and all((Path(prior['path'])/f).exists() for f in prior['sha256']):
        print('Reuse pinned '+kind,flush=True)
        continue
    repo='mlx-community/'+name
    for attempt in range(3):
        try:
            info=HfApi().model_info(repo,files_metadata=True,revision=prior['revision'] if prior else None)
            dest=root/'models'/name
            print(f'Download {repo}@{info.sha}',flush=True)
            snapshot_download(repo_id=repo,revision=info.sha,local_dir=dest,max_workers=2)
            hashes={}
            for f in info.siblings:
                p=dest/f.rfilename
                if p.is_file() and (p.suffix=='.safetensors' or p.name.endswith('.json')):
                    with p.open('rb') as stream:
                        h=hashlib.file_digest(stream,'sha256').hexdigest()
                    if f.lfs and f.lfs.sha256!=h:
                        raise RuntimeError('Hash mismatch: '+f.rfilename)
                    hashes[f.rfilename]=h
            manifest[kind]={'repository':repo,'revision':info.sha,'path':str(dest),'sha256':hashes}
            atomic_json(root/'models.json',manifest)
            break
        except Exception:
            if attempt==2:raise
            time.sleep(3*(attempt+1))

atomic_json(root/'models.json',manifest)
