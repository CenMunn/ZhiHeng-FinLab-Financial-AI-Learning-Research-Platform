from fastapi import APIRouter
from fastapi.responses import JSONResponse


def forecast_router(store):
    router=APIRouter(prefix='/api/v1/forecasts',tags=['offline prediction experiments'])

    @router.get('/runs')
    def runs():return JSONResponse(content=store.list(),headers={'Cache-Control':'no-store'})

    @router.get('/runs/{run_id}')
    def run(run_id:str):return JSONResponse(content=store.get(run_id),headers={'Cache-Control':'no-store'})
    return router
