from platform_app.contracts.market_experiments import MarketSnapshot
from platform_app.contracts.models import stable_hash

def snapshot_hash(snapshot:MarketSnapshot)->str:
    return stable_hash(snapshot.model_dump(mode='json'))
