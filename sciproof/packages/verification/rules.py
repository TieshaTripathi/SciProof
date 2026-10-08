"""Implemented scientific rules only; explicit binary classification semantics."""
from dataclasses import dataclass
from typing import Protocol
import numpy as np
import pandas as pd
from scipy import stats

@dataclass(frozen=True)
class RuleResult:
    value:float
    context:dict
class VerificationRule(Protocol):
    name:str
    method:str
    version:str
    def execute(self,df:pd.DataFrame,columns:list[str])->RuleResult: ...

def numeric_fields(df,columns,arity):
    if len(columns)!=arity or len(set(columns))!=arity or any(c not in df.columns for c in columns):
        raise ValueError(f'{arity} distinct existing column(s) required; names are case-sensitive')
    try: values=df[columns].apply(pd.to_numeric,errors='raise')
    except (ValueError,TypeError): raise ValueError('Requested column contains nonnumeric observations') from None
    pair=values.dropna()
    if not len(pair) or not np.isfinite(pair.to_numpy(dtype=float)).all(): raise ValueError('No finite complete numeric observations')
    return pair,{'input_fields':columns,'input_rows':len(df),'observations_used':len(pair),
                 'missing_rows_excluded':len(df)-len(pair),'missing_policy':'complete observations'}

class RowCountRule:
    name='row_count';method='DataFrame row count';version='1'
    def execute(self,df,columns):
        if columns: raise ValueError('Row count does not take dataset columns')
        return RuleResult(float(len(df)),{'input_rows':len(df),'unit':'rows'})
class NumericColumnRule:
    version='1'
    def execute(self,df,columns):
        values,context=numeric_fields(df,columns,1)
        with np.errstate(over='ignore',invalid='ignore'):
            result=float(self.compute(values.iloc[:,0]))
        if not np.isfinite(result): raise ValueError('Statistic undefined or overflowed for available sample')
        return RuleResult(result,{**context,**getattr(self,'conventions',{})})
class MeanRule(NumericColumnRule):
    name='mean';method='Arithmetic mean'
    def compute(self,v): return v.mean()
class MedianRule(NumericColumnRule):
    name='median';method='Median'
    def compute(self,v): return v.median()
class MinimumRule(NumericColumnRule):
    name='minimum';method='Minimum'
    def compute(self,v): return v.min()
class MaximumRule(NumericColumnRule):
    name='maximum';method='Maximum'
    def compute(self,v): return v.max()
class VarianceRule(NumericColumnRule):
    name='variance';method='Sample variance';conventions={'ddof':1}
    def compute(self,v): return v.var(ddof=1)
class PopulationVarianceRule(NumericColumnRule):
    name='population_variance';method='Population variance';conventions={'ddof':0}
    def compute(self,v): return v.var(ddof=0)
class StandardDeviationRule(NumericColumnRule):
    name='std';method='Sample standard deviation';conventions={'ddof':1}
    def compute(self,v): return v.std(ddof=1)
class SampleSizeRule(NumericColumnRule):
    name='sample_size';method='Nonmissing numeric observation count'
    def compute(self,v): return len(v)
class ModeRule(NumericColumnRule):
    name='mode';method='Unique numeric mode'
    def compute(self,v):
        modes=v.mode()
        if len(modes)!=1: raise ValueError('Mode has multiple equally frequent values')
        return modes.iloc[0]
class ProportionRule(NumericColumnRule):
    name='proportion';method='Binary 0/1 proportion';conventions={'unit':'proportion','representation':'0/1'}
    def compute(self,v):
        if not v.isin([0,1]).all(): raise ValueError('Proportion requires explicitly binary 0/1 observations')
        return v.mean()
class PercentageRule(ProportionRule):
    name='percentage';method='100 times binary 0/1 proportion';conventions={'unit':'percent','representation':'0/1'}
    def compute(self,v): return 100*super().compute(v)
class CorrelationRule:
    name='correlation';method='Pearson correlation';version='1'
    def execute(self,df,columns):
        pair,context=numeric_fields(df,columns,2)
        if len(pair)<3 or (pair.nunique()<2).any(): raise ValueError('Correlation requires three or more nonconstant complete pairs')
        result=float(stats.pearsonr(pair.iloc[:,0],pair.iloc[:,1]).statistic)
        if not np.isfinite(result): raise ValueError('Correlation is undefined')
        return RuleResult(result,context)
class BinaryClassificationRule:
    version='1'
    def execute(self,df,columns):
        pair,context=numeric_fields(df,columns,2)
        if not pair.isin([0,1]).all().all(): raise ValueError('Classification rules require binary 0/1 truth and prediction')
        truth,pred=pair.iloc[:,0],pair.iloc[:,1]
        tp=int(((truth==1)&(pred==1)).sum());fp=int(((truth==0)&(pred==1)).sum())
        fn=int(((truth==1)&(pred==0)).sum());tn=int(((truth==0)&(pred==0)).sum())
        numerator,denominator=self.fraction(tp,fp,fn,tn)
        if denominator==0: raise ValueError('Classification statistic has an undefined zero denominator')
        return RuleResult(numerator/denominator,{**context,'positive_class':1,'truth_column':columns[0],
             'prediction_column':columns[1],'confusion_matrix':{'tp':tp,'fp':fp,'fn':fn,'tn':tn},'unit':'proportion'})
class AccuracyRule(BinaryClassificationRule):
    name='accuracy';method='Binary classification accuracy'
    def fraction(self,tp,fp,fn,tn): return tp+tn,tp+fp+fn+tn
class PrecisionRule(BinaryClassificationRule):
    name='precision';method='Binary positive-class precision'
    def fraction(self,tp,fp,fn,tn): return tp,tp+fp
class RecallRule(BinaryClassificationRule):
    name='recall';method='Binary positive-class recall'
    def fraction(self,tp,fp,fn,tn): return tp,tp+fn
class F1Rule(BinaryClassificationRule):
    name='f1';method='Binary positive-class F1'
    def fraction(self,tp,fp,fn,tn): return 2*tp,2*tp+fp+fn

RULES={rule.name:rule for rule in (RowCountRule(),MeanRule(),MedianRule(),MinimumRule(),MaximumRule(),
       VarianceRule(),PopulationVarianceRule(),StandardDeviationRule(),SampleSizeRule(),ModeRule(),
       ProportionRule(),PercentageRule(),CorrelationRule(),AccuracyRule(),PrecisionRule(),RecallRule(),F1Rule())}
def execute_rule(df,metric,columns):
    if metric not in RULES: raise ValueError('Unsupported rule; explicit methodology required')
    return RULES[metric].execute(df,columns)
