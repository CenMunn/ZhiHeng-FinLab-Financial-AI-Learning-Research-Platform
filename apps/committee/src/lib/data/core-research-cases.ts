/** Development cases only; never count these as a held-out evaluation set. */
export const CORE_RESEARCH_CASES = [
  {code:'600519',name:'贵州茅台',industry:'白酒',query:'核对贵州茅台2025年营业收入、归母净利润与经营现金流，列出原文位置和单位，不推断股价涨跌。'},
  {code:'000858',name:'五粮液',industry:'白酒',query:'核对五粮液2025年盈利质量；缺少同口径原始资料时列出待补清单。'},
  {code:'000568',name:'泸州老窖',industry:'白酒',query:'核对泸州老窖经营现金流与归母净利润，注明报告期和数据来源。'},
  {code:'300750',name:'宁德时代',industry:'新能源',query:'核对宁德时代营收与利润变化，区分原始数据与研究推断。'},
  {code:'002594',name:'比亚迪',industry:'新能源',query:'核对比亚迪收入、归母净利润与现金流，注明单位和报告期。'},
  {code:'601012',name:'隆基绿能',industry:'新能源',query:'分析隆基绿能盈利与估值，资料不足时不要用默认中性分代替。'},
  {code:'300274',name:'阳光电源',industry:'新能源',query:'核对阳光电源盈利质量，指出当前缺少哪些原始依据。'},
  {code:'688981',name:'中芯国际',industry:'半导体',query:'核对中芯国际财务数据的报告期和币种，不混用人民币与美元。'},
  {code:'002371',name:'北方华创',industry:'半导体',query:'核对北方华创增长数据并定位原始披露，无来源的数字不作事实。'},
  {code:'688256',name:'寒武纪',industry:'半导体',query:'梳理寒武纪财务资料缺口，区分已经核对的数据与尚待验证的判断。'},
] as const
