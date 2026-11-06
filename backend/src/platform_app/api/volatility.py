from fastapi import APIRouter
from fastapi.responses import JSONResponse


def volatility_router(store, diagnostics_store=None):
    router = APIRouter(prefix='/api/v1/volatility', tags=['read-only volatility experiments'])

    @router.get('/runs')
    def runs():
        return JSONResponse(content=store.list(), headers={'Cache-Control': 'no-store'})

    @router.get('/runs/{run_id}')
    def run(run_id: str):
        return JSONResponse(content=store.get(run_id), headers={'Cache-Control': 'no-store'})

    @router.get('/runs/{run_id}/diagnostics')
    def diagnostics(run_id: str):
        if diagnostics_store is None:
            raise KeyError(run_id)
        return JSONResponse(content=diagnostics_store.get(run_id), headers={'Cache-Control': 'no-store'})

    return router
