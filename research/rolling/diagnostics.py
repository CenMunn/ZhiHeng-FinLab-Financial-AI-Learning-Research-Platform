import numpy as np


def psi(train,current):
    train=np.asarray(train,dtype=float);current=np.asarray(current,dtype=float)
    if not len(train) or not len(current) or not np.isfinite(train).all() or not np.isfinite(current).all():raise ValueError('PSI需要非空有限观测')
    boundaries=np.unique(np.quantile(train,np.linspace(0,1,11)))
    if len(boundaries)<2:return {'status':'constant_train','psi':None,'train_mean':float(train.mean()),'current_mean':float(current.mean())}
    bins=np.r_[-np.inf,boundaries[1:-1],np.inf];p=np.histogram(train,bins)[0].astype(float)+1e-6;q=np.histogram(current,bins)[0].astype(float)+1e-6;p/=p.sum();q/=q.sum()
    return {'status':'measured','psi':float(np.sum((q-p)*np.log(q/p))),'bins':len(p),'train_mean':float(train.mean()),'current_mean':float(current.mean())}


def block_permute(x,columns,seed=42,block=20):
    x=np.asarray(x);result=x.copy();chunks=[np.arange(start,min(start+block,len(x))) for start in range(0,len(x),block)]
    order=np.random.default_rng(seed).permutation(len(chunks));index=np.concatenate([chunks[i] for i in order])
    result[:,columns]=x[index][:,columns]
    return result
