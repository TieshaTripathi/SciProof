# Deterministic numerical policy

Only implementations in `packages/verification/rules.py` are available. Each check carries its rule version and installed pandas/NumPy/SciPy versions. `numeric.py` owns comparison policy; calculated values are never rounded before comparison.

The pass condition is `abs(calculated - reported) <= absolute_tolerance + relative_tolerance * abs(reported)`. Defaults are absolute 0.001 and relative 0. Relative difference uses the absolute reported value as denominator and is null when that value is zero. Nonfinite values, overflow and negative tolerances are unverifiable. Display rounding does not affect the decision.

Column names are exact and case-sensitive. Numeric conversion is strict. Missing observations are excluded and the check context records counts; paired rules exclude rows missing either value. Invalid nonmissing observations invalidate the check. Undefined statistics never substitute zero. Duplicate rows and outliers are profiled without dropping or rewriting observations.

Sample variance and standard deviation use ddof=1. Population variance requires `population_variance`. Pearson correlation requires at least three nonconstant complete pairs. Mode requires a unique most frequent value. Binary proportions use 0/1 observations and return [0,1]; percentages multiply by 100. Classification rules use columns in truth, prediction order with positive class 1; accuracy, precision, recall and F1 return proportions, with confusion counts preserved. Zero denominators are unverifiable.

Explicit manuscript syntax retains `mean of x = 2`, `median x: 2`, `row count = 3`, `correlation of x and y = 1`, and `percentage of success = 50`. Additional metrics include `minimum`, `maximum`, `population_variance` and `accuracy/precision/recall/f1 of truth and prediction = 0.5`. Unicode identifier columns are supported. Direct rule calls accept arbitrary exact dataset field names, including long names; ambiguous natural-language descriptions remain outside explicit extraction coverage.

Checks persist reported/calculated values, differences, tolerances, comparison method, outcome, explanation, input fields, source page, evidence/artifact relations and execution context. Immutable report snapshots also include artifact/evidence IDs and numerical conventions. Historical checks migrated to 0002 have null new fields; their original reports are preserved.

These operations reproduce explicitly stated statistics. They do not establish causal validity, study design quality, representativeness, fraud absence, or independent scientific truth. Method transparency stays zero until independently supported. Empty evidence or unverifiable checks yield insufficient evidence; conflicts take precedence and cap the grade at D.
