"""Fixed pre-2025 public checkpoint, safe files and upstream LFS verification."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import time
import requests
from research.market.common import PROJECT,write_json,file_sha

REPO='amazon/chronos-t5-tiny'
REVISION='129a2d204d6ab4205a0049a160402deefaf161b2'
PUBLIC_AT='2024-03-27T19:14:02Z'
MODEL=PROJECT/'research/artifacts/rolling-model/chronos-t5-tiny-20240327'


def verify_model_files(receipt,root=MODEL):
    if receipt['revision']!=REVISION or set(receipt['files'])!={'README.md','config.json','generation_config.json','model.safetensors'}:raise ValueError('模型来源清单不完整')
    for name,item in receipt['files'].items():
        file=Path(root)/name
        if not file.is_file() or file_sha(file)!=item['sha256']:raise ValueError('固定模型文件缺失或变化：'+name)


def get(url):
    last=None
    for attempt in range(3):
        try:
            response=requests.get(url,timeout=40);response.raise_for_status();return response
        except requests.RequestException as exc:last=exc;time.sleep(attempt+1)
    raise RuntimeError('固定公开模型获取失败：'+url) from last


def acquire():
    manifest=MODEL/'acquisition.json'
    if manifest.exists():
        receipt=json.loads(manifest.read_text('utf8'))
        verify_model_files(receipt)
        return receipt
    metadata=get(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true').json()
    if metadata['sha']!=REVISION:raise ValueError('模型revision未解析到固定提交')
    siblings={x['rfilename']:x for x in metadata['siblings']};MODEL.mkdir(parents=True,exist_ok=True);files={}
    for name in ('README.md','config.json','generation_config.json','model.safetensors'):
        url=f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}'
        raw=get(url).content;sha=hashlib.sha256(raw).hexdigest();upstream=siblings[name].get('lfs',{}).get('sha256')
        if upstream and sha!=upstream:raise ValueError('模型LFS SHA256未匹配')
        if name=='model.safetensors' and not upstream:raise ValueError('权重缺上游LFS校验')
        target=MODEL/name
        if target.exists() and target.read_bytes()!=raw:raise ValueError('拒绝覆盖不同模型文件')
        if not target.exists():target.write_bytes(raw)
        files[name]={'url':url,'sha256':sha,'upstream_lfs_sha256':upstream,'bytes':len(raw),'retrieved_at':datetime.now(timezone.utc).isoformat()}
    config=json.loads((MODEL/'config.json').read_text('utf8'))
    if config['model_type']!='t5':raise ValueError('仅允许本地标准T5配置')
    card=(MODEL/'README.md').read_text('utf8')
    if 'apache-2.0' not in card.lower():raise ValueError('固定模型卡许可未确认')
    receipt={'repo':REPO,'revision':REVISION,'public_at':PUBLIC_AT,'license':'apache-2.0','files':files,
        'training_cutoff':'not fully established; original dataset overlap unknown','eligible_evaluation':'2025 only; public checkpoint existed in 2024',
        'mode':'frozen encoder + supervised train-only ridge readout; no zero-shot return claim'}
    write_json(manifest,receipt);print(json.dumps({'acquired':REPO,'revision':REVISION,'weight_sha256':files['model.safetensors']['sha256']},ensure_ascii=False),flush=True)
    return receipt


if __name__=='__main__':acquire()
