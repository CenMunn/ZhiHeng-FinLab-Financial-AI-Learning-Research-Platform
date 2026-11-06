export interface PriceBar {date:string;open:number;close:number;high:number;low:number;volume:number}
export const PRICE_FEATURES=['return1','return5','return10','return20','closeMa5','closeMa10','closeMa20','volatility5','volatility20','intraday','range','openGap','volumeRatio5','volumeRatio20']
const validDate=(v:string)=>/^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0,10)===v
export function buildPriceFeatures(bars:PriceBar[],at=bars.length-1):number[] {
  if(!Array.isArray(bars)||at<30||at>=bars.length||!Number.isInteger(at))throw Error('需要至少31个有序交易日')
  for(let i=0;i<bars.length;i++){
    const b=bars[i]
    if(!b||!validDate(b.date)||i>0&&bars[i-1].date>=b.date||![b.open,b.close,b.high,b.low,b.volume].every(Number.isFinite)
      ||b.open<=0||b.close<=0||b.low<=0||b.high<Math.max(b.open,b.close,b.low)||b.low>Math.min(b.open,b.close)||b.volume<0)
      throw Error('日线日期、顺序或OHLCV值无效')
  }
  const mean=(xs:number[])=>xs.reduce((a,b)=>a+b,0)/xs.length
  const b=bars[at],returns=(n:number)=>Array.from({length:n},(_,i)=>bars[at-i].close/bars[at-i-1].close-1)
  const volatility=(n:number)=>{const rs=returns(n),m=mean(rs);return Math.sqrt(mean(rs.map(x=>(x-m)**2)))}
  const avg=(n:number,key:'close'|'volume')=>mean(bars.slice(at-n+1,at+1).map(x=>x[key]))
  const features=[...[1,5,10,20].map(n=>b.close/bars[at-n].close-1),...[5,10,20].map(n=>b.close/avg(n,'close')),
    volatility(5),volatility(20),b.close/b.open-1,(b.high-b.low)/b.close,b.open/bars[at-1].close-1,
    b.volume/avg(5,'volume'),b.volume/avg(20,'volume')]
  if(!features.every(Number.isFinite))throw Error('成交量窗口或特征不可用，不能推理')
  return features
}
export function classifyPriceSample(featureDate:string,labelDate:string,validStart:string,testStart:string):'train'|'valid'|'test'|null {
  if(![featureDate,labelDate,validStart,testStart].every(validDate)||labelDate<=featureDate||validStart>=testStart)throw Error('时间切分无效')
  if(featureDate<validStart)return labelDate<validStart?'train':null
  if(featureDate<testStart)return labelDate<testStart?'valid':null
  return 'test'
}
interface TreeNode {leaf_value?:number;split_feature?:number;threshold?:number|string;decision_type?:string;left_child?:TreeNode;right_child?:TreeNode}
export interface PriceTreeModel {feature_names:string[];tree_info:{tree_structure:TreeNode}[];average_output?:boolean;num_class?:number}
export function predictTreeModel(model:PriceTreeModel,features:number[]):number {
  if(!model||!Array.isArray(model.feature_names)||features.length!==model.feature_names.length||!features.every(Number.isFinite)
    ||model.average_output||model.num_class!==undefined&&model.num_class!==1||!Array.isArray(model.tree_info)||!model.tree_info.length||model.tree_info.length>300)
    throw Error('模型或特征格式无效')
  const walk=(node:TreeNode,depth=0):number=>{
    if(!node||depth>20)throw Error('模型树无效')
    if(typeof node.leaf_value==='number'&&Number.isFinite(node.leaf_value))return node.leaf_value
    if(node.decision_type!=='<='||typeof node.threshold!=='number'||!Number.isFinite(node.threshold)
      ||!Number.isInteger(node.split_feature)||node.split_feature!<0||node.split_feature!>=features.length||!node.left_child||!node.right_child)
      throw Error('模型含不支持的分裂或缺失子节点')
    return walk(features[node.split_feature!]<=node.threshold?node.left_child:node.right_child,depth+1)
  }
  const prediction=model.tree_info.reduce((n,t)=>n+walk(t.tree_structure),0)
  if(!Number.isFinite(prediction))throw Error('模型结果无效')
  return prediction
}
