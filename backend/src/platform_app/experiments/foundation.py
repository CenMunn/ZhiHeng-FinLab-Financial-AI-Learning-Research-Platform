from decimal import Decimal,localcontext
from datetime import timedelta
from pathlib import Path
import hashlib
import platform
import decimal
import pydantic
from platform_app.contracts.market_experiments import MarketSnapshot,FoundationConfig
from platform_app.contracts.models import stable_hash
from platform_app.experiments.data import snapshot_hash
from platform_app.experiments.features import historical_features
from platform_app.experiments.markets import estimate_costs,market_rules,number

ENGINE_VERSION='market-foundation-v1'
ENGINE_SOURCES={path.relative_to(Path(__file__).parents[1]).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in (
    Path(__file__),Path(__file__).with_name('features.py'),Path(__file__).with_name('markets.py'),
    Path(__file__).with_name('data.py'),Path(__file__).parents[1]/'contracts'/'market_experiments.py',
    Path(__file__).parents[1]/'contracts'/'models.py')}
ENGINE_SHA256=stable_hash(ENGINE_SOURCES)
ENGINE_RUNTIME={'python':platform.python_version(),'pydantic':pydantic.__version__,'libmpdec':decimal.__libmpdec_version__}

def build_foundation(snapshot:MarketSnapshot,config:FoundationConfig)->dict:
    # Do not drop unpublished sessions out of the middle: this would change lag semantics.
    count=sum(bar.close_at+timedelta(minutes=1)<=config.as_of for bar in snapshot.bars)
    bars=snapshot.bars[:count]
    if config.train_count+config.validation_count>=count:raise ValueError('训练、验证之后至少保留一个测试观测')
    features=historical_features(bars,config.window)
    # As-of and historical decision eligibility are separate gates.
    for index,bar in enumerate(bars):
        if bar.available_at>config.as_of:
            for key in ('close','return_1d','sma','volatility'):features[index][key]=None
    splits=[];labels={};start=0
    with localcontext() as context:
        context.prec=28
        for name,end in [('train',config.train_count),('validation',config.train_count+config.validation_count),('test',count)]:
            retained=[]
            for index in range(start,end):
                target=index+config.horizon
                if target<end and bars[index].close is not None and bars[target].close is not None and bars[target].available_at<=config.as_of and features[index]['close'] is not None:
                    retained.append({'session':str(bars[index].session),'target_session':str(bars[target].session),'forward_return':number(Decimal(bars[target].close)/Decimal(bars[index].close)-1)})
            labels[name]=retained
            splits.append({'name':name,'start':str(bars[start].session),'end':str(bars[end-1].session),'rows':end-start,'label_count':len(retained),'purged_count':end-start-len(retained)})
            start=end
        fitted=[Decimal(row['return_1d']) for row in features[:config.train_count] if row['return_1d'] is not None]
        mean=sum(fitted)/len(fitted) if fitted else None
        std=(sum((value-mean)**2 for value in fitted)/len(fitted)).sqrt() if fitted else None
        scaler={'feature':'return_1d','fit_start':str(bars[0].session),'fit_end':str(bars[config.train_count-1].session),'fit_count':len(fitted),'mean':number(mean) if mean is not None else None,'std':number(std) if std is not None else None,'ddof':0}
        for row in features:
            value=row['return_1d']
            row['standardized_return']=number((Decimal(value)-mean)/std) if value is not None and std is not None and std>0 else None
    identity={'engine_version':ENGINE_VERSION,'engine_sha256':ENGINE_SHA256,'engine_runtime':ENGINE_RUNTIME,'snapshot_sha256':snapshot_hash(snapshot),'config':config.model_dump(mode='json')}
    return {'schema_version':'foundation-result-v1','engine_version':ENGINE_VERSION,'engine_sha256':ENGINE_SHA256,'engine_sources':ENGINE_SOURCES,'engine_runtime':ENGINE_RUNTIME,'input_hash':stable_hash(identity),'snapshot_sha256':identity['snapshot_sha256'],
            'snapshot_id':snapshot.snapshot_id,'market':snapshot.market,'source_kind':snapshot.source_kind,'config':config.model_dump(mode='json'),
            'quality':{'total_rows':len(snapshot.bars),'eligible_rows':count,'excluded_as_of':len(snapshot.bars)-count,'unavailable_rows':sum(b.available_at>config.as_of for b in bars),'halted_rows':sum(b.status=='halted' for b in bars),'complete_feature_rows':sum(all(row[key] is not None for key in ('return_1d','sma','volatility')) for row in features),'calendar_match':True,'assessment':'声明字段结构检查，不认证真实历史可用性'},
            'splits':splits,'scaler':scaler,'features':features,'labels':labels,'market_rules':market_rules(snapshot),
            'cost_example':{'notional':'10000','currency':snapshot.currency,'kind':'teaching_assumption','buy':estimate_costs('10000','buy',config.costs),'sell':estimate_costs('10000','sell',config.costs)},
            'limitations':list(snapshot.limitations)+['本记录是数据管线检查，不是策略回测或模型成绩。','日线决策时间为收盘后1分钟；晚于该时间的数据不作为当期特征。','收益率标准化只拟合训练段；零方差时不生成标准化值。','费用为教学假设；买卖示例不代表实际成交。']}
