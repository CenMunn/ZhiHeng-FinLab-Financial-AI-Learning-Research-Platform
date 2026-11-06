from fastapi import APIRouter
from fastapi.responses import JSONResponse

def five_asset_router(store):
    router=APIRouter(prefix='/api/v1/five-asset',tags=['read-only five-asset experiments'])
    @router.get('/runs')
    def runs():return JSONResponse(content=store.list(),headers={'Cache-Control':'no-store'})
    @router.get('/runs/{run_id}')
    def run(run_id:str):return JSONResponse(content=store.get(run_id),headers={'Cache-Control':'no-store'})
    return router
