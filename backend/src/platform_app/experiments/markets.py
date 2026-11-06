from datetime import date
from decimal import Decimal,localcontext,ROUND_HALF_UP
from typing import Literal
from platform_app.contracts.market_experiments import MarketSnapshot,CostAssumptions
from platform_app.contracts.models import decimal_string

def number(value:Decimal)->str:
    if value==0:return '0'
    return format(value,'f').rstrip('0').rstrip('.') if '.' in format(value,'f') else format(value,'f')

def valid_buy_quantity(snapshot:MarketSnapshot,quantity:str)->bool:
    try:
        value=Decimal(decimal_string(quantity,places=8,significant=20))
        return value>0 and value% (Decimal('100') if snapshot.market=='ashare' else Decimal(snapshot.quantity_step))==0
    except (ValueError,ArithmeticError):return False

def earliest_sell_session(snapshot:MarketSnapshot,acquired:date)->date|None:
    index=snapshot.sessions.index(acquired)
    if snapshot.market=='btc':return acquired
    return snapshot.sessions[index+1] if index+1<len(snapshot.sessions) else None

def market_rules(snapshot:MarketSnapshot)->dict:
    return {'profile':'ordinary-mainboard-research-subset' if snapshot.market=='ashare' else 'configured-spot-research-subset',
            'timezone':'Asia/Shanghai' if snapshot.market=='ashare' else 'UTC','currency':snapshot.currency,
            'buy_quantity_step':'100' if snapshot.market=='ashare' else snapshot.quantity_step,
            'sell_delay_sessions':1 if snapshot.market=='ashare' else 0,
            'scope':'仅日历和买入数量/最早可售日规则；不等于成交模拟，不保证价格/流动性/涨跌停可成交。'}

def estimate_costs(notional:str,side:Literal['buy','sell'],costs:CostAssumptions)->dict:
    if side not in ('buy','sell'):raise ValueError('不支持的买卖方向')
    amount=Decimal(decimal_string(notional,places=8,significant=20))
    with localcontext() as context:
        context.prec=40
        raw={'commission':max(amount*Decimal(costs.commission_bps)/10000,Decimal(costs.minimum_commission)) if amount else Decimal(0),
             'tax':amount*Decimal(costs.sell_tax_bps)/10000 if side=='sell' else Decimal(0),
             'transfer':amount*Decimal(costs.transfer_bps)/10000,'slippage':amount*Decimal(costs.slippage_bps)/10000}
        amounts={key:value.quantize(Decimal('.00000001'),rounding=ROUND_HALF_UP) for key,value in raw.items()}
        return {**{key:number(value) for key,value in amounts.items()},'total':number(sum(amounts.values()))}
