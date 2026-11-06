import sqlite3
from fastapi import APIRouter,Response
from fastapi.responses import JSONResponse
from platform_app.adapters.experiment_store import ExperimentStore
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.market_experiments import FoundationRequest
from platform_app.experiments.samples import sample_snapshots,default_config
from platform_app.experiments.data import snapshot_hash
from platform_app.experiments.foundation import build_foundation

def experiment_router(store:ExperimentStore)->APIRouter:
    router=APIRouter(prefix='/api/v1/experiments',tags=['learning experiments'])
    registry={snapshot.snapshot_id:snapshot for snapshot in sample_snapshots()}

    def storage(operation):
        try:return operation()
        except sqlite3.Error:return JSONResponse(status_code=500,content={'code':'experiment_storage_error','message':'实验记录读写失败，请保留配置后重试。'})

    @router.get('/snapshots')
    def snapshots():
        return [{'snapshot_id':s.snapshot_id,'snapshot_sha256':snapshot_hash(s),'market':s.market,'instrument':s.instrument,'venue':s.venue,'currency':s.currency,
                 'source_kind':s.source_kind,'source_uri':s.source_uri,'calendar_source':s.calendar_source,'row_count':len(s.bars),'start':str(s.sessions[0]),'end':str(s.sessions[-1]),
                 'default_config':default_config(s).model_dump(mode='json'),'limitations':s.limitations} for s in registry.values()]

    @router.get('/snapshots/{snapshot_id}')
    def snapshot(snapshot_id:str):return registry[snapshot_id]

    @router.post('/foundation',status_code=201)
    def foundation(body:FoundationRequest,response:Response):
        snapshot=registry[body.snapshot_id]
        if snapshot_hash(snapshot)!=body.expected_snapshot_sha256:raise DomainConflict('snapshot_changed','数据快照版本已变化，请重新加载样例后检查。')
        result=build_foundation(snapshot,body.config)
        def save():
            record,replayed=store.save(snapshot.model_dump(mode='json'),result)
            if replayed:response.status_code=200
            return record
        return storage(save)

    @router.get('/runs')
    def runs():return storage(store.list)

    @router.get('/runs/{run_id}')
    def run(run_id:str):return storage(lambda:store.get(run_id))
    return router
