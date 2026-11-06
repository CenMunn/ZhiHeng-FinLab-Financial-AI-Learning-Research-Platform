export interface ForecastMetric {samples:number;maePercentagePoints:number;rmsePercentagePoints:number;directionAccuracy:number|null;directionalForecastCoverage:number}
export interface ForecastSummary {
  version:string;trainedAt:string;target:string;modelSha256:string;featureNames:string[];numBoostRound:number;
  dataManifest:{code:string;name:string;url:string;barsSha256:string;rows:number;firstDate:string;lastDate:string;adjustment:string}[];
  segments:Record<string,{samples:number;firstFeatureDate:string;lastFeatureDate:string;lastLabelDate:string}>;
  comparisons:Record<string,ForecastMetric>;perStock:Record<string,Record<string,ForecastMetric>>;
  errorBand:{radiusFraction:number;calibration:string;testCoverage:number};benchmarkConclusion:string;
  costs:{trainingSeconds:number;testAndValidationInferenceSeconds:number;modelJsonBytes:number;paidModelAPIRequests:number;computeCost:string};
  limitations:string[];selfDeveloped:string;externalComponents:string;
}
export interface PriceForecastResult {
  stockCode:string;stockName:string;modelVersion:string;mode:'snapshot'|'live';inputDate:string;inputSource:string;observedClose:number;
  predictedChangePct:number;predictedClose:number;errorBandPct:number[];predictionPeriod:string;inferenceMs:number;
  history:{date:string;close:number}[];scope:'experimental_price_change';investmentDecisionEligible:false;
}
