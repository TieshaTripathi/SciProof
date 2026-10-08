import math
import pandas as pd
import pytest
from packages.verification.engine import verify, calculate
from packages.verification.numeric import NumericPolicy
from packages.verification.rules import RULES
from apps.api.storage import validate, MAX_BYTES
from packages.ai.provider import LocalProvider

@pytest.mark.parametrize('values,metric,columns',[
    ([], 'mean',['x']),([None,None],'mean',['x']),([1],'std',['x']),
    ([1,'private-value'],'mean',['x']),([math.inf,1],'mean',['x']),
    ([1,2],'mean',['X']),([1,2],'mean',['missing']),
    ([1,1,1],'correlation',['x','y']),([1,2],'mode',['x']),
    ([0,2],'proportion',['x']),([1,2],'unsupported',['x'])])
def test_undefined_never_supported(values,metric,columns):
    df=pd.DataFrame({'x':values,'y':values})
    report=verify(df,[dict(metric=metric,columns=columns,reported_value=0,tolerance=.001)])
    assert report['checks'][0]['outcome']=='UNVERIFIABLE'
    assert 'private-value' not in report['checks'][0]['explanation']

@pytest.mark.parametrize('metric,expected',[
    ('row_count',3),('mean',2),('median',2),('minimum',1),('maximum',3),
    ('variance',1),('population_variance',2/3),('std',1),('sample_size',3)])
def test_column_rules(metric,expected):
    assert calculate(pd.DataFrame({'x':[1,2,3]}),metric,[] if metric=='row_count' else ['x'])==pytest.approx(expected)

def test_constant_and_missing():
    assert calculate(pd.DataFrame({'x':[2,2,None]}),'variance',['x'])==0
    assert calculate(pd.DataFrame({'x':[2]}),'population_variance',['x'])==0
    assert calculate(pd.DataFrame({'x':[2,2,1]}),'mode',['x'])==2
    assert calculate(pd.DataFrame({'x':[1,0,None]}),'proportion',['x'])==.5

@pytest.mark.parametrize('direction',[1,-1])
def test_correlation(direction):
    assert calculate(pd.DataFrame({'x':[1,2,3,None],'y':[direction,2*direction,3*direction,5]}),'correlation',['x','y'])==pytest.approx(direction)

@pytest.mark.parametrize('metric,expected',[('accuracy',.5),('precision',.5),('recall',.5),('f1',.5)])
def test_binary_classification(metric,expected):
    assert calculate(pd.DataFrame({'truth':[1,1,0,0],'prediction':[1,0,1,0]}),metric,['truth','prediction'])==expected
    with pytest.raises(ValueError): calculate(pd.DataFrame({'truth':[0,0],'prediction':[0,0]}),'precision',['truth','prediction'])

def test_numeric_policy_reproduction():
    comparison=NumericPolicy(.01,.02).compare(100,102)
    assert comparison['effective_tolerance']==2.01
    assert comparison['relative_difference']==.02
    assert comparison['result']
    assert NumericPolicy().compare(0,0)['relative_difference'] is None
    for value in (float('nan'),float('inf'),True):
        with pytest.raises(ValueError): NumericPolicy().compare(value,0)
    assert not NumericPolicy(0,0).compare(1,1.000000000001)['result']

def test_names_and_profile():
    for name in ['測定値','x'*190]:
        assert calculate(pd.DataFrame({name:[1,2,3]}),'mean',[name])==2
    assert LocalProvider().extract(['mean of 測定値 = 2'],['測定値'])[0].columns==['測定値']
    report=verify(pd.DataFrame({'x':[1,1,1,1,1000000]}),[])
    assert report['profile']['duplicate_rows']==3
    assert report['profile']['outliers_iqr']['x']==1
    assert len(RULES)==17

@pytest.mark.parametrize('filename,raw',[('data.json',b'{broken'),('data.parquet',b'PAR1badPAR1'),('data.csv',b'x'*(MAX_BYTES+1))],ids=['malformed-json','corrupt-parquet','oversized'])
def test_invalid_artifacts(filename,raw):
    with pytest.raises(Exception): validate(filename,'DATASET',raw)
