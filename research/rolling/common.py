from importlib.metadata import version
import platform
from research.market.common import PROJECT,file_sha,digest,write_json,read_checked,load_split


def sources():
    from research.market.common import code_manifest
    return {**code_manifest(),**{p.relative_to(PROJECT).as_posix():file_sha(p) for p in sorted((PROJECT/'research/rolling').glob('*.py'))}}


def environment():
    return {'python':platform.python_version(),**{name:version(name) for name in ('numpy','torch','lightgbm','scipy','pydantic','safetensors','transformers','chronos-forecasting','accelerate')}}


def verify_files(root,files):
    from pathlib import Path
    root=Path(root).resolve()
    for name,sha in files.items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_sha(path)!=sha:raise ValueError('冻结来源文件缺失、变化或越界：'+name)
