"""Immutable input and completed-fold boundaries; never re-bless a resumed file."""
import json
from research.volatility.common import file_sha,write_json,verify

def seal_inputs(root):
    path=root/'inputs.json'
    if path.exists():return check_inputs(root)
    files={p.relative_to(root).as_posix():file_sha(p) for p in root.rglob('*.json')}
    write_json(path,{'files':files});return files

def check_inputs(root):
    body=json.loads((root/'inputs.json').read_text('utf8'));verify(root,body['files']);return body['files']

def seal_fold(root,folder):
    check_inputs(root)
    receipt=json.loads((folder/'training.json').read_text('utf8'))
    if receipt['preparation_sha256']!=file_sha(folder/'preparation.json'):raise ValueError('折准备身份变化')
    verify(folder,receipt['artifacts'])
    files={**receipt['artifacts'],**{n:file_sha(folder/n) for n in ('training.json','predictions.json','preparation.json')}}
    write_json(folder/'completed.json',{'inputs_sha256':file_sha(root/'inputs.json'),'files':files})

def check_fold(root,folder):
    path=folder/'completed.json'
    if not path.is_file():raise ValueError('折未完整冻结；保留原目录，使用新的 --attempt 标识重新运行')
    body=json.loads(path.read_text('utf8'))
    if body['inputs_sha256']!=file_sha(root/'inputs.json'):raise ValueError('准备清单变化')
    verify(folder,body['files']);return body

def reject_partial(folder):
    if (folder/'training.json').exists() or (folder/'predictions.json').exists() or ((folder/'models').exists() and any((folder/'models').iterdir())):
        raise ValueError('发现未完成的折产物；保留现场，使用新的 --attempt 标识重新运行，不覆盖旧模型')
