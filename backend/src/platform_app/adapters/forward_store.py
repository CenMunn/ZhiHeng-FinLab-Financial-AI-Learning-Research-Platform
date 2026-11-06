"""Read-only forward observation publication. Never obtains quotes or runs models."""
import hashlib
import json
import math
import re
from datetime import date, datetime
from pathlib import Path, PurePosixPath

from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash

FROZEN_ROOT = 'research/artifacts/risk-budget/6280750f22c41b4f7100f4d9ec7f439da022a6aa92917e6d1fb5b8a1aad62cf7'
SYMBOLS = {'600519', '600036', '600585', 'BTCUSDT', 'ETHUSDT'}


def require(value):
    if not value:
        raise ValueError('Invalid forward record')


def stamp(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None)
    return result


def number(value, *, positive=False):
    require(type(value) in (int, float) and math.isfinite(value))
    require(not positive or value > 0)


def validate_record(record):
    require(record['schema'] == 'forward-market-status-v1')
    stamp(record['updated_at'])
    require(record['status'] in {'waiting', 'active', 'blocked'})
    require(isinstance(record['limitations'], list) and all(isinstance(s, str) for s in record['limitations']))
    require(isinstance(record['items'], list) and isinstance(record['artifacts'], dict) and record['artifacts'])
    symbols = set()
    for item in record['items']:
        symbol = item['symbol']
        require(symbol in SYMBOLS and symbol not in symbols)
        symbols.add(symbol)
        require(item['market'] == ('crypto' if symbol.endswith('USDT') else 'ashare'))
        require(isinstance(item['name'], str) and isinstance(item['reason'], str))
        require(item['state'] in {'waiting_signal', 'waiting_outcome', 'blocked', 'scored'})
        if item['latest_session'] is not None:
            date.fromisoformat(item['latest_session'])
        if item['source_retrieved_at'] is not None:
            stamp(item['source_retrieved_at'])
        rows = item['predictions']
        require(isinstance(rows, list))
        require(type(item['forecast_count']) is int and item['forecast_count'] == len(rows))
        require(type(item['scored_count']) is int and item['scored_count'] == sum(p.get('outcome') is not None for p in rows))
        ids = set()
        for row in rows:
            require(isinstance(row['forecast_id'], str) and row['forecast_id'] and row['forecast_id'] not in ids)
            ids.add(row['forecast_id'])
            require(date.fromisoformat(row['signal_session']) >= date(2026, 11, 6))
            created, decision, entry, exit_at = [stamp(row[k]) for k in ('created_at', 'decision_at', 'entry_at', 'exit_at')]
            require(decision <= created < entry < exit_at)
            require(isinstance(row['predictions'], dict) and row['predictions'])
            for values in row['predictions'].values():
                for mode in ('raw', 'calibrated'):
                    number(values[mode], positive=True)
            outcome = row['outcome']
            if outcome is not None:
                require(stamp(outcome['scored_at']) >= exit_at)
                number(outcome['realized_variance']);require(outcome['realized_variance'] >= 0)
                number(outcome['log_return'])
                require(set(outcome['errors']) == set(row['predictions']))
                for errors in outcome['errors'].values():
                    number(errors['raw_qlike']);number(errors['calibrated_qlike'])


class ForwardStore:
    def __init__(self, folder, project):
        self.folder, self.project = Path(folder), Path(project)

    def get(self):
        path = self.folder / 'status.json'
        if not path.exists():
            return {'record': None, 'record_sha256': None, 'artifact_status': 'empty', 'missing_artifacts': []}
        try:
            require(path.resolve().is_relative_to(self.folder.resolve()))
            body = json.loads(path.read_text('utf8'));record = body['record']
            require(body['sha256'] == stable_hash(record))
            validate_record(record)
            allowed = [(self.project / p).resolve() for p in ('research/artifacts/forward-market', FROZEN_ROOT)]
            missing = []
            for name, expected in record['artifacts'].items():
                relative = PurePosixPath(name)
                require(not relative.is_absolute() and '..' not in relative.parts and '\\' not in name and ':' not in name)
                require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected))
                artifact = (self.project / name).resolve()
                require(any(artifact != root and artifact.is_relative_to(root) for root in allowed))
                if not artifact.exists():
                    missing.append(name);continue
                require(artifact.is_file())
                with artifact.open('rb') as source:
                    require(hashlib.file_digest(source, 'sha256').hexdigest() == expected)
            return {'record': record, 'record_sha256': body['sha256'], 'artifact_status': 'missing' if missing else 'verified', 'missing_artifacts': sorted(missing)}
        except (ValueError, KeyError, TypeError, AttributeError, OSError, ArithmeticError):
            raise DomainConflict('forward_market_corrupt', '前向观察记录或来源校验失败，未作为有效预测或成绩展示。') from None
