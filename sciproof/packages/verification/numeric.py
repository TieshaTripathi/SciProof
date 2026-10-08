"""One auditable comparison policy; calculations are never rounded to pass."""
from dataclasses import dataclass, asdict
import math

DEFAULT_ABSOLUTE_TOLERANCE=.001
DEFAULT_RELATIVE_TOLERANCE=0.0
@dataclass(frozen=True)
class NumericPolicy:
    absolute_tolerance:float=DEFAULT_ABSOLUTE_TOLERANCE
    relative_tolerance:float=DEFAULT_RELATIVE_TOLERANCE
    method:str='absolute_plus_reported_relative_v1'
    def compare(self,reported,calculated):
        numbers=(reported,calculated,self.absolute_tolerance,self.relative_tolerance)
        if any(isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) for n in numbers):
            raise ValueError('Comparison requires finite scalar values and tolerances')
        if self.absolute_tolerance<0 or self.relative_tolerance<0: raise ValueError('Tolerances must be nonnegative')
        difference=abs(calculated-reported)
        if not math.isfinite(difference): raise ValueError('Comparison difference overflowed')
        limit=self.absolute_tolerance+self.relative_tolerance*abs(reported)
        if not math.isfinite(limit): raise ValueError('Comparison tolerance overflowed')
        relative=difference/abs(reported) if reported!=0 else None
        if relative is not None and not math.isfinite(relative): relative=None
        return {'absolute_difference':difference,'relative_difference':relative,
                'tolerance':self.absolute_tolerance,'relative_tolerance':self.relative_tolerance,
                'effective_tolerance':limit,'comparison_method':self.method,
                'rounding_policy':'No rounding before comparison; display formatting only',
                'result':difference<=limit}

NUMERICAL_CONVENTIONS={
    'floating_point':'IEEE-754 float64; nonfinite calculated/reported values are unverifiable',
    'missing_values':'Exclude missing observations; paired checks use complete pairs',
    'undefined_values':'UNVERIFIABLE; never substitute zero',
    'sample_statistics':'ddof=1; population statistics require explicit population rule',
    'proportion':'Binary 0/1 observations, calculated value in [0,1]',
    'percentage':'100 times binary proportion, calculated value in [0,100]',
    'rounding':'No rounding before comparison',
}
