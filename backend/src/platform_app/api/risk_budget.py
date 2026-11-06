from decimal import Decimal,InvalidOperation
from typing import Literal
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,StrictStr,field_validator
class PreviewRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 target_volatility:StrictStr
 cost_multiplier:Literal[0,1,2]
 @field_validator('target_volatility')
 @classmethod
 def target(cls,value):
  try:valid=Decimal(value).is_finite() and Decimal('.05')<=Decimal(value)<=Decimal('.30')
  except InvalidOperation:valid=False
  if not valid:raise ValueError('目标年化风险须在 5%–30% 之间。')
  return value
 @field_validator('cost_multiplier',mode='before')
 @classmethod
 def cost(cls,value):
  if type(value) is not int:raise ValueError('费用倍数须为 0、1 或 2。')
  return value

def risk_budget_router(store):
 router=APIRouter(prefix='/api/v1/risk-budget',tags=['risk budget'])
 def response(body):return JSONResponse(content=body,headers={'Cache-Control':'no-store'})
 @router.get('/runs')
 def runs():return response(store.list())
 @router.get('/runs/{run_id}')
 def run(run_id:str):return response(store.get(run_id))
 @router.post('/runs/{run_id}/preview')
 def preview(run_id:str,body:PreviewRequest):return response(store.preview(run_id,body.target_volatility,body.cost_multiplier))
 return router
