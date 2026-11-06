from pathlib import Path
import sqlite3
from fastapi import APIRouter,Response
from fastapi.responses import JSONResponse
from platform_app.adapters.public_market import IDS,load_dataset
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.public_backtests import BacktestRequest
from platform_app.experiments.backtest import compare,default_config


def backtest_router(store,root:Path,provider=None):
    router=APIRouter(prefix='/api/v1/backtests',tags=['public market backtests'])

    def catalog():
        if provider:return provider(),[]
        result={};unavailable=[]
        for key in IDS:
            try:result[key]=load_dataset(root,key)
            except (OSError,ValueError,KeyError):unavailable.append({'dataset_id':key,'message':'未登记公开快照，或原始文件/规范数据校验失败。请在本地运行数据接入脚本后重试。'})
        return result,unavailable

    def storage(fn):
        try:return fn()
        except sqlite3.Error:return JSONResponse(status_code=500,content={'code':'backtest_storage_error','message':'回测记录读写失败，请保留配置后重试。'})

    @router.get('/datasets')
    def datasets():
        items,unavailable=catalog()
        return {'datasets':[{'dataset_id':key,'dataset_sha256':stable_hash(data.model_dump(mode='json')),'market':data.snapshot.market,
            'instrument':data.snapshot.instrument,'currency':data.snapshot.currency,'start':str(data.snapshot.sessions[0]),'end':str(data.snapshot.sessions[-1]),
            'row_count':len(data.snapshot.bars),'quality':data.quality,'limitations':data.snapshot.limitations,'default_config':default_config(data).model_dump(mode='json')}
            for key,data in items.items()],'unavailable':unavailable}

    @router.post('/compare',status_code=201)
    def comparison(body:BacktestRequest,response:Response):
        items,_=catalog()
        if body.dataset_id not in items:raise DomainConflict('dataset_unavailable','公开数据未就绪或校验失败，未启动回测。请重新加载数据目录。')
        data=items[body.dataset_id]
        if stable_hash(data.model_dump(mode='json'))!=body.expected_dataset_sha256:raise DomainConflict('dataset_changed','公开快照版本已变化，请重新加载目录。')
        result=compare(data,body.config)
        def save():
            record,replayed=store.save(data.model_dump(mode='json'),result)
            if replayed:response.status_code=200
            return record
        return storage(save)

    @router.get('/runs')
    def runs():return storage(store.list)

    @router.get('/runs/{run_id}')
    def run(run_id:str):return storage(lambda:store.get(run_id))
    return router
