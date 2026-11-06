from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response


def filing_extraction_router(store):
    router=APIRouter(prefix='/api/v1/filing-extraction',tags=['financial field extraction'])

    @router.get('')
    def latest():
        return JSONResponse(content=store.get(),headers={'Cache-Control':'no-store'})

    @router.get('/document')
    def document(doc_id: str):
        return Response(store.document(doc_id),media_type='application/pdf',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Disposition':'inline; filename="quarterly-report.pdf"'})

    return router
