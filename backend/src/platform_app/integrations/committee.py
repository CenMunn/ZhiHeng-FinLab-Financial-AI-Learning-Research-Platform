from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, Request


def probe_json(url: str) -> dict:
    with build_opener(ProxyHandler({})).open(Request(url, headers={'Accept':'application/json'}), timeout=2) as response:
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise ValueError('Invalid integration response')
        return json.loads(raw)


def get_committee_status(origin: str, build_id: str, probe=probe_json) -> dict:
    url = urlsplit(origin)
    if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost'} or url.username or url.password
            or url.path not in {'', '/'} or url.query or url.fragment or not url.port):
        raise ValueError('Committee origin must be a fixed loopback origin')
    origin = origin.rstrip('/')
    result = {'available':False, 'state':'offline', 'origin':origin, 'build_id':build_id,
              'message':'智投委服务未连接，请启动平台服务后重试。'}
    if not build_id:
        return {**result,'state':'not_configured','message':'智投委运行包尚未登记。'}
    try:
        value = probe(origin + '/__committee/health')
        if not isinstance(value, dict) or value.get('module') != 'committee':
            return result
        if value.get('buildId') != build_id:
            return {**result,'state':'version_mismatch','message':'当前智投委服务与已接入版本不同，请检查启动配置。'}
        if value.get('ready') is not True:
            return result
        return {**result,'available':True,'state':'ready','message':'智投委已连接。'}
    except (OSError, TimeoutError, ValueError, TypeError):
        return result


def integration_status(project: Path) -> dict:
    try:
        manifest = json.loads((project / 'integrations/committee-manifest.json').read_text(encoding='utf-8'))
        config = json.loads((project / '.local/committee/config.json').read_text(encoding='utf-8'))
        port = config['port']
        if not isinstance(port, int) or not 1024 <= port <= 65535:
            raise ValueError('Invalid committee port')
        return get_committee_status(f'http://127.0.0.1:{port}', manifest['build_id'])
    except (OSError, KeyError, ValueError, TypeError):
        return {'available':False,'state':'not_configured','origin':'http://127.0.0.1:3155',
                'build_id':'','message':'智投委尚未配置，请按部署说明配置运行包。'}
