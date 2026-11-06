// Only presentation numbering and explicit loss-sign boilerplate are removed.
// Distinct accounting metrics (e.g. 营业收入/营业总收入) remain distinct.
export function stripNote(label:string){
  return label.replace(/[\s|]+\d+[（(][\da-zA-Z]+[）)]\s*$/,'').replace(/(?:[一二三四五六七八九十]+[、]\s*\d+(?:[（(]\d+[）)])?|[一二三四五六七八九十]+[（(]\d+[）)]\d*|[（(][一二三四五六七八九十]+[）)]\d+(?:,[（(][一二三四五六七八九十]+[）)]\d+)*|\d+(?:\.\d+)?)\s*$/,'').trim().replace(/[|\s]+$/,'');
}
export function metricLabel(label:string){
  return label.replace(/\s/g,'').replace(/^(?:[一二三四五六七八九十]+[、.．]|[（(][一二三四五六七八九十]+[）)]|\d+[、.．])/,'')
    .replace(/所有者权益[（(]或股东权益[）)]合计/g,'所有者权益合计')
    .replace(/^其中\s*[:：]\s*/,'')
    .replace(/^(?:加|减)[:：]/,'')
    .replace(/[（(](?:净)?(?:亏损|损失|减少|收益)(?:总额)?以[“"‘']?[－\-−][”"’']?号填列[）)]/g,'')
    .replace(/[\s|：:、，,（）()]/g,'');
}
export function financialSection(name:string,label:string):number|null{
  const s=metricLabel(stripNote(label));
  if(/资产负债表$/.test(name)){
    // A lease liability can be current or non-current; the label alone
    // cannot prove a section reversal at a page boundary.
    if(s==='租赁负债')return null;
    if(/负债和.*权益总计/.test(s))return 7;
    if(/权益|股本|实收资本|资本公积|盈余公积|未分配利润|其他综合收益/.test(s))return 6;
    if(s==='负债合计'||s==='负债总额')return 5;
    if(/非流动负债|长期借款|应付债券|长期应付|递延收益|递延所得税负债/.test(s))return 4;
    if(/流动负债|短期借款|应付|预收|合同负债|租赁负债/.test(s))return 3;
    if(s==='资产总计'||s==='资产总额')return 2;
    if(/非流动资产|固定资产|在建工程|无形资产|商誉|长期待摊|长期股权|使用权资产|递延所得税资产/.test(s))return 1;
    if(/流动资产|货币资金|存货|应收|预付|交易性金融资产/.test(s))return 0;
  }
  if(/利润表|损益表/.test(name)){
    if(/每股收益/.test(s))return 8;
    if(/综合收益|外币.*折算|重分类|债权投资.*变动/.test(s))return 7;
    if(/持续经营|终止经营|归属于|少数股东损益/.test(s))return 6;
    if(s==='净利润')return 5;
    if(/所得税/.test(s))return 4;
    if(/利润总额|营业外/.test(s))return 3;
    if(/营业利润/.test(s))return 2;
    if(/收益|损失|减值|处置|净敞口/.test(s)&&!/利息/.test(s))return 1;
    if(/营业收入|营业总收入|成本|费用|税金|利息收入|利息费用/.test(s))return 0;
  }
  if(/现金流量表/.test(name)){
    if(/现金及现金等价物|汇率变动|现金净增加/.test(s))return 3;
    if(/筹资|吸收投资|分配股利|发行债券|偿还债务/.test(s))return 2;
    if(/投资活动|收回投资|取得投资收益|处置.*现金|购建|投资支付/.test(s))return 1;
    if(/经营活动|销售商品|税费返还|购买商品|支付.*税费|支付给.*职工/.test(s))return 0;
  }
  return null;
}
