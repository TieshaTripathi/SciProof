import hashlib
import json
import os
from importlib.metadata import version
import numpy as np
import pandas as pd
from scipy import stats

WEIGHTS = dict(statistical_reproducibility=.25, claim_evidence_alignment=.25,
               data_integrity=.20, dataset_quality=.15, method_transparency=.15)
from packages.verification.rules import RULES, execute_rule
from packages.verification.numeric import NumericPolicy, NUMERICAL_CONVENTIONS, DEFAULT_ABSOLUTE_TOLERANCE
METHODS={name:rule.method for name,rule in RULES.items()}

def scoring_weights():
    weights=json.loads(os.getenv('SCORING_WEIGHTS','null')) or WEIGHTS
    if set(weights)!=set(WEIGHTS) or any(not isinstance(v,(int,float)) or not np.isfinite(v) or v<0 for v in weights.values()) or abs(sum(weights.values())-1)>1e-9:
        raise ValueError('Scoring weights must cover the five dimensions and sum to 1')
    return weights

def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()

def calculate(df, metric, columns):
    return execute_rule(df, metric, columns).value

def verify(df, claims, artifact_hashes_verified=False):
    weights=scoring_weights()
    checks = []
    for claim in claims:
        check = {**claim, 'check_type':claim['metric'],'input_fields':claim['columns'],
                 'method': METHODS.get(claim['metric'],'Unsupported method'),
                 'software_versions': {p: version(p) for p in ['pandas', 'numpy','scipy']}}
        check.update(absolute_difference=None,relative_difference=None,comparison_method=NumericPolicy().method,
                     relative_tolerance=claim.get('relative_tolerance',0),rule_version=RULES[claim['metric']].version if claim['metric'] in RULES else None,
                     result=None,rule_context={})
        try:
            computation=execute_rule(df,claim['metric'],claim['columns'])
            comparison=NumericPolicy(claim.get('tolerance',DEFAULT_ABSOLUTE_TOLERANCE),claim.get('relative_tolerance',0)).compare(claim['reported_value'],computation.value)
            check.update(**comparison,calculated_value=computation.value,rule_context=computation.context,
                         outcome='SUPPORTED' if comparison['result'] else 'CONFLICTING',
                         explanation='Compared without rounding using absolute tolerance plus relative tolerance times absolute reported value; see rule context for excluded observations')
        except (ValueError, TypeError, OverflowError) as e:
            check.update(calculated_value=None, outcome='UNVERIFIABLE', explanation=str(e))
        checks.append(check)
    missing = int(df.isna().sum().sum())
    duplicates = int(df.duplicated().sum())
    alignment = 100*sum(c['outcome']=='SUPPORTED' for c in checks)/len(checks) if checks else 0
    scores = dict(statistical_reproducibility=alignment, claim_evidence_alignment=alignment,
                  data_integrity=100 if artifact_hashes_verified else 0,
                  dataset_quality=max(0,100*(1-missing/max(1,df.size)-duplicates/max(1,len(df)))),
                  method_transparency=0)
    scores['overall_verification_confidence'] = round(sum(scores[k]*v for k,v in weights.items()),2)
    status = 'FAILED_VERIFICATION' if any(c['outcome']=='CONFLICTING' for c in checks) else 'INSUFFICIENT_EVIDENCE' if not len(df) or not checks or any(c['outcome']=='UNVERIFIABLE' for c in checks) else 'VERIFIED_WITH_WARNINGS'
    overall=scores['overall_verification_confidence']
    grade='E' if status=='INSUFFICIENT_EVIDENCE' else 'A' if overall>=90 else 'B' if overall>=75 else 'C' if overall>=60 else 'D' if overall>=40 else 'E'
    if status=='FAILED_VERIFICATION' and grade in ('A','B','C'): grade='D'
    outliers={}
    for column in df.select_dtypes(include='number').columns:
        values=df[column].dropna(); values=values[np.isfinite(values)]; q1,q3=values.quantile([.25,.75]);iqr=q3-q1
        outliers[str(column)]=int(((values<q1-1.5*iqr)|(values>q3+1.5*iqr)).sum()) if len(values) else 0
    return dict(checks=checks, scores=scores, weights=weights, status=status,
                classification=grade, numerical_conventions=NUMERICAL_CONVENTIONS,
                profile=dict(rows=len(df),columns=list(df.columns),missing_cells=missing,duplicate_rows=duplicates,outliers_iqr=outliers),
                findings=['Methodology is not established. Uploaded code is not executed.',
                          'Scores describe performed checks, not scientific validity.',
                          f'{missing} missing cells and {duplicates} duplicate rows.',
                          'Data integrity reflects authenticated artifact hashes only; it does not detect fraud.'])
