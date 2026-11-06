"""Export an inspectable development comparison, preserving all three seed results."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT=Path(__file__).resolve().parents[2]


def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def plot():
    run=PROJECT/'research/artifacts/b012-20261030'; output=PROJECT/'docs/research/figures'
    results=json.loads((run/'results.json').read_text(encoding='utf8')); seeds=results['config']['seeds']
    scores=results['methods']; values=[scores['b0']['coverage_at_5']*100,scores['b1']['coverage_at_5']*100,results['b2_seed_variation']['mean']*100]
    raw_seed=[scores[f'b2-seed-{s}']['coverage_at_5']*100 for s in seeds]
    output.mkdir(parents=True,exist_ok=True)
    with (output/'b012-summary.csv').open('w',newline='',encoding='utf8') as stream:
        writer=csv.writer(stream); writer.writerow(['method','questions','coverage_at_5','recall_at_5','ndcg_at_5'])
        for name,item in scores.items(): writer.writerow([name,item['questions'],item['coverage_at_5'],item['recall_at_5'],item['ndcg_at_5']])
    palette=['#0072B2','#D55E00','#009E73']; styles=['-','--',':']; sources={}
    with plt.rc_context({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'}):
        fig,axes=plt.subplots(1,2,figsize=(11.8,4.7),gridspec_kw={'width_ratios':[1,1.45]})
        ax=axes[0]; ax.bar([0,1,2],values,color=palette,width=.59)
        ax.errorbar(2,values[2],yerr=statistics.stdev(raw_seed),color='#202020',capsize=5,fmt='none',lw=1.3)
        ax.scatter([1.94,2,2.06],raw_seed,color='#202020',marker='o',s=15,zorder=5)
        for i,value in enumerate(values): ax.text(i,value+2.2,f'{value:.2f}%',ha='center',fontweight='bold')
        ax.set(ylim=(0,100),ylabel='Complete annotated evidence Coverage@5 (%)',xticks=[0,1,2],xticklabels=['B0\nBM25','B1\nPretrained','B2\nFinQA-tuned'])
        ax.set_title('A  Official development set (883 questions)',loc='left',fontweight='bold',fontsize=11)
        ax.yaxis.grid(True,alpha=.18); ax.set_axisbelow(True)
        ax.text(.5,-.22,'B2: mean ± sample SD, 3 seeds; dots = each seed.\nSeed variation is not a sampling confidence interval.',transform=ax.transAxes,ha='center',fontsize=8)
        ax=axes[1]
        for seed,color,style in zip(seeds,palette,styles):
            source=run/f'b2-seed-{seed}'/'training.jsonl'; sources[f'seed_{seed}_log_sha256']=sha(source)
            rows=[json.loads(line) for line in source.read_text(encoding='utf8').splitlines()]
            if len(rows)!=2647 or [r['step'] for r in rows]!=list(range(1,2648)): raise ValueError('Incomplete training curve')
            losses=[r['mean_bce'] for r in rows]; window=50
            smooth=[statistics.fmean(losses[i-window+1:i+1]) for i in range(window-1,len(losses))]
            ax.plot(list(range(window,len(losses)+1)),smooth,label=f'Seed {seed}',color=color,linestyle=style,lw=1.6)
        ax.set(xlabel='Optimizer update (one epoch per seed)',ylabel='Mean binary cross-entropy',ylim=(0,None))
        ax.set_title('B  Training loss, 50-update trailing mean',loc='left',fontweight='bold',fontsize=11)
        ax.grid(True,alpha=.18); ax.legend(frameon=False,fontsize=9)
        fig.subplots_adjust(left=.07,right=.985,bottom=.26,top=.87,wspace=.31)
        fig.text(.5,.035,'Same BM25 top-20 and 256-token cap. B2 uses unannotated weak negatives. Development results; no final test.',ha='center',fontsize=8,color='#454545')
        for suffix in ('png','svg'): fig.savefig(output/f'b012-comparison.{suffix}',dpi=200,facecolor='white')
        plt.close(fig)
    manifest={'results_sha256':sha(run/'results.json'),'plot_script_sha256':sha(Path(__file__)),**sources,
        'matplotlib':matplotlib.__version__,'size_inches':[11.8,4.7],'png_dpi':200,'seeds':seeds,
        'transformations':'Coverage percent; B2 mean/sample SD over three seeds. Loss: trailing arithmetic mean of 50 optimizer-window BCE means, begins at update 50; raw logs preserved.',
        'audience':'Local research/portfolio, no journal-specific compliance claim',
        'alt_text':'BM25, pretrained and three-seed FinQA-tuned complete evidence coverage on the same 883 development questions, alongside the three smoothed training loss curves.',
        'outputs_sha256':{name:sha(output/name) for name in ['b012-summary.csv','b012-comparison.png','b012-comparison.svg']}}
    (output/'b012-figure-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'figure':str(output/'b012-comparison.png'),'coverage_percent':values},indent=2))


if __name__=='__main__': plot()
