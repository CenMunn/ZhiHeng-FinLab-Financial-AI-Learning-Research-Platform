from datetime import timedelta
from decimal import Decimal,localcontext
from platform_app.contracts.market_experiments import MarketBar
from platform_app.experiments.markets import number

def historical_features(bars:tuple[MarketBar,...],window:int)->list[dict]:
    rows=[]
    with localcontext() as context:
        context.prec=28
        for index,bar in enumerate(bars):
            decision=bar.close_at+timedelta(minutes=1)
            def price(position):
                if position<0:return None
                candidate=bars[position]
                return Decimal(candidate.close) if candidate.close is not None and candidate.available_at<=decision else None
            def change(position):
                current,previous=price(position),price(position-1)
                return current/previous-1 if current is not None and previous is not None else None
            current=price(index)
            prices=[price(i) for i in range(index-window+1,index+1)] if index>=window-1 else []
            returns=[change(i) for i in range(index-window+1,index+1)] if index>=window else []
            sma=sum(prices)/window if len(prices)==window and all(p is not None for p in prices) else None
            volatility=None
            if len(returns)==window and all(r is not None for r in returns):
                mean=sum(returns)/window
                volatility=(sum((r-mean)**2 for r in returns)/(window-1)).sqrt()
            value=change(index)
            rows.append({'session':str(bar.session),'decision_at':decision.isoformat(),'close':number(current) if current is not None else None,
                         'return_1d':number(value) if value is not None else None,'sma':number(sma) if sma is not None else None,
                         'volatility':number(volatility) if volatility is not None else None})
    return rows
