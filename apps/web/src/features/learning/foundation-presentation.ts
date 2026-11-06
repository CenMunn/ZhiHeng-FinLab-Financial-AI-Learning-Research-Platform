export function splitPreview(total:number,train:number,validation:number):{valid:true;counts:number[];fractions:number[]}|{valid:false}{
  if(![total,train,validation].every(Number.isInteger)||total<1||train<3||validation<1||train+validation>=total)return {valid:false};
  const counts=[train,validation,total-train-validation];
  return {valid:true,counts,fractions:counts.map(value=>value/total)};
}
