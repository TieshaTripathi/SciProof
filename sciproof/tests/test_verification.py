import pandas as pd
import pytest
from packages.verification.engine import verify, calculate, canonical_hash

def claim(value=2): return {'claim_id':'1','metric':'mean','columns':['x'],'reported_value':value,'tolerance':.001}
def test_mean(): assert verify(pd.DataFrame({'x':[1,2,3]}),[claim()])['checks'][0]['outcome']=='SUPPORTED'
def test_conflict(): assert verify(pd.DataFrame({'x':[1,2,3]}),[claim(5)])['status']=='FAILED_VERIFICATION'
def test_missing_column(): assert verify(pd.DataFrame({'y':[1]}),[claim()])['status']=='INSUFFICIENT_EVIDENCE'
def test_no_claims(): assert verify(pd.DataFrame({'x':[1]}),[])['status']=='INSUFFICIENT_EVIDENCE'
def test_variance(): assert calculate(pd.DataFrame({'x':[1,2,3]}),'variance',['x'])==1
def test_undefined():
    with pytest.raises(ValueError): calculate(pd.DataFrame({'x':[1]}),'std',['x'])
def test_hash(): assert canonical_hash({'a':1,'b':2})==canonical_hash({'b':2,'a':1})
def test_nan():
    with pytest.raises(ValueError): canonical_hash({'x':float('nan')})
def test_correlation():
    assert calculate(pd.DataFrame({'x':[1,2,3],'y':[2,4,6]}),'correlation',['x','y'])==pytest.approx(1)
def test_mode_ties():
    with pytest.raises(ValueError): calculate(pd.DataFrame({'x':[1,2]}),'mode',['x'])
def test_binary_percentage():
    assert calculate(pd.DataFrame({'x':[1,1,0,0]}),'percentage',['x'])==50
    with pytest.raises(ValueError): calculate(pd.DataFrame({'x':[0,2]}),'proportion',['x'])
def test_invalid_tolerance_never_passes():
    c=claim();c['tolerance']=-1
    assert verify(pd.DataFrame({'x':[1,2,3]}),[c])['checks'][0]['outcome']=='UNVERIFIABLE'
def test_weights_validation(monkeypatch):
    monkeypatch.setenv('SCORING_WEIGHTS','{"dataset_quality":1}')
    with pytest.raises(ValueError): verify(pd.DataFrame({'x':[1]}),[])
def test_integrity_requires_hash_evidence():
    assert verify(pd.DataFrame({'x':[1]}),[])['scores']['data_integrity']==0
    assert verify(pd.DataFrame({'x':[1]}),[],artifact_hashes_verified=True)['scores']['data_integrity']==100
