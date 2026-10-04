import csv
import json
from pathlib import Path
import subprocess
import sys
import yaml
import pytest
from prepare import prepare


def factor(sample, factors, **extra):
    return dict(local_sample_id=sample, mb_sample_id='MB' + sample,
                sample_source='not a technical factor', factors=factors, **extra)


def feature(analysis, name, values, refmet=''):
    return dict(analysis_id=analysis, metabolite_name=name, refmet_name=refmet,
                units='a.u.', DATA=values)


def paths(tmp_path, factors, data, task=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    f, d, t, out = [tmp_path / name for name in ('f.json', 'd.json', 'task.yaml', 'out')]
    f.write_text(json.dumps(factors), encoding='utf-8')
    d.write_text(json.dumps(data), encoding='utf-8')
    t.write_text(yaml.safe_dump(task or {'phenotype_key': 'Diet',
                                        'control_sample_types': ['QC', 'PBQC', 'pool', 'blank']}), encoding='utf-8')
    return f, d, t, out


def run(tmp_path, factors, data, task=None):
    args = paths(tmp_path, factors, data, task)
    prepare(*args)
    out = args[-1]
    assert {p.name for p in out.iterdir() if p.is_file()} == {'prepared.csv', 'summary.json', 'config.yaml'}
    with (out / 'prepared.csv').open(newline='', encoding='utf-8') as handle:
        table = list(csv.reader(handle))
    summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    config = yaml.safe_load((out / 'config.yaml').read_text(encoding='utf-8'))
    return table, summary, config


def test_text_identifiers_values_and_no_invented_metadata(tmp_path):
    ids = ['1', '01', '10', '2', ' 1 ', 'A B']
    factors = [factor(s, ' Diet : NA | Zeta : x:y | Alpha: 001 ') for s in ids]
    values = dict(zip(ids, ['0001', '1.00', 'NA', '', ' 3 ', '1e-04']))
    table, summary, config = run(tmp_path, factors, [feature('AN01', 'met', values)])
    assert table[0] == ['Samples', 'Phenotype', 'Alpha', 'Zeta', 'Sample type', 'Batch', 'Injection order', 'met']
    assert table[1] == ['METHOD', '', '', '', '', '', '', 'AN01']
    assert table[2:] == [[s, 'NA', '001', 'x:y', 'subject', '', '', values[s]] for s in sorted(ids)]
    assert summary == {'n_samples': 6, 'n_features': 1, 'phenotype_counts': {'NA': 6},
                       'analyses': ['AN01'], 'extra_factor_keys': ['Alpha', 'Zeta'],
                       'excluded_samples': {}, 'duplicate_metabolites_dropped': [],
                       'technical_columns_from_factors': [],
                       'blank_technical_columns': ['Batch', 'Injection order']}
    assert config == {'sample_metadata_header_row': 1, 'feature_names_row': 1,
                      'data_start_row': 3, 'feature_start_column': 8,
                      'feature_metadata_label_column': 1, 'sheet_name': None,
                      'target_column': 'Phenotype', 'sample_column': 'Samples',
                      'sample_type_column': 'Sample type', 'batch_column': 'Batch',
                      'position_column': 'Injection order', 'qc_sample_types': []}


def test_controls_mapping_keep_and_exclusion_precedence(tmp_path):
    factors = [factor('ok', 'Diet:old | Sample type:patient | Batch:007 | Injection order:009'),
               factor('na', 'Diet:NA'), factor('qc', 'Diet:reject | sample TYPE:qC'),
               factor('pool', 'Sample type:pool'), factor('blank', 'Diet: | Sample type:Blank'),
               factor('pb', 'Diet:other | Sample type:PBQC'),
               factor('nometa', 'Other:z'), factor('empty', 'Diet: '),
               factor('reject', 'Diet:bad'), factor('missingA', 'Diet:old'),
               factor('missingB', 'Diet:old'), factor('missingqc', 'Sample type:QC')]
    all_ids = [f['local_sample_id'] for f in factors]
    a = {s: '' for s in all_ids if s not in ['missingA', 'missingqc']}
    b = {s: '02' for s in all_ids if s not in ['missingA', 'missingB', 'missingqc']}
    task = {'phenotype_key': 'Diet', 'map': {'old': 'new'}, 'keep': ['new', 'NA'],
            'control_sample_types': ['qc', 'pbqc', 'pool', 'blank']}
    table, summary, config = run(tmp_path, factors, [feature('B', 'b', b), feature('A', 'a', a)], task)
    assert summary['analyses'] == ['A', 'B']
    assert summary['excluded_samples'] == {'nometa': 'no phenotype', 'empty': 'no phenotype',
        'reject': 'phenotype not in keep: bad', 'missingA': 'not measured in A',
        'missingB': 'not measured in B', 'missingqc': 'not measured in A'}
    assert summary['phenotype_counts'] == {'new': 1, 'NA': 1}
    assert summary['n_samples'] == 6
    by_id = {r[0]: dict(zip(table[0], r)) for r in table[2:]}
    assert sorted(by_id) == ['blank', 'na', 'ok', 'pb', 'pool', 'qc']
    for sample, stype in [('qc', 'qC'), ('pool', 'pool'), ('blank', 'Blank'), ('pb', 'PBQC')]:
        assert by_id[sample]['Sample type'] == stype
        assert by_id[sample]['Phenotype'] == ''
    assert by_id['ok']['Phenotype'] == 'new'
    assert by_id['na']['Phenotype'] == 'NA'
    assert by_id['ok']['Sample type'] == 'subject'
    assert by_id['ok']['Batch'] == '007'
    assert by_id['ok']['Injection order'] == '009'
    assert by_id['qc']['Batch'] == by_id['qc']['Injection order'] == ''
    assert by_id['ok']['a'] == ''
    assert summary['extra_factor_keys'] == ['Other']
    assert set(summary['technical_columns_from_factors']) == {'Sample type', 'Batch', 'Injection order'}
    assert summary['blank_technical_columns'] == []
    assert set(config['qc_sample_types']) == {'qC', 'pool', 'Blank', 'PBQC'}
    assert {r[0] for r in table[2:]} | set(summary['excluded_samples']) == set(all_ids)


def test_measurement_union_includes_dropped_records_and_sparse_cells(tmp_path):
    factors = [factor(s, 'Diet:X') for s in ['s', 't', 'u', 'v']]
    data = [feature('A', 'shared', {'s': '001', 't': '', 'u': '03', 'v': '4'}),
            feature('B', 'unique', {'t': '005'}),
            feature('B', 'shared', {'s': ''})]
    table, summary, _ = run(tmp_path, factors, data)
    assert table[0][-2:] == ['shared', 'unique']
    assert table[1][-2:] == ['A', 'B']
    assert table[2:] == [['s', 'X', 'subject', '', '', '001', ''],
                         ['t', 'X', 'subject', '', '', '', '005']]
    assert summary['excluded_samples'] == {'u': 'not measured in B', 'v': 'not measured in B'}
    assert summary['duplicate_metabolites_dropped'] == [
        {'metabolite': 'shared', 'analysis_id': 'B', 'kept_from': 'A'}]


def test_priority_repeated_features_fallbacks_and_header_collisions(tmp_path):
    factors = [factor('01', 'Diet:X')]
    data = [feature('A', 'shared', {'01': 'later1'}),
            feature('B', 'shared', {'01': 'first1'}),
            feature('B', 'shared', {'01': 'first2'}),
            feature('B', 'shared.1', {'01': 'reserved'}),
            feature('B', 'Samples', {'01': 'collision'}),
            feature('B', ' ', {'01': 'fallback'}, 'ref:name'),
            feature('B', '', {'01': 'anon1'}),
            feature('B', '', {'01': 'anon2'}, ' '),
            feature('A', 'shared', {'01': 'later2'}),
            feature('A', '', {'01': 'anon3'}),
            feature('C', 'unselected', {'01': 'bad'})]
    task = {'phenotype_key': 'Diet', 'analyses': ['B', 'A'], 'control_sample_types': []}
    table, summary, config = run(tmp_path, factors, data, task)
    assert table[0] == ['Samples', 'Phenotype', 'Sample type', 'Batch', 'Injection order',
        'shared', 'shared.2', 'shared.1', 'Samples.1', 'ref:name', 'unnamed', 'unnamed.1', 'unnamed.2']
    assert len(set(table[0])) == len(table[0])
    assert table[1] == ['METHOD', '', '', '', '', 'B', 'B', 'B', 'B', 'B', 'B', 'B', 'A']
    assert table[2] == ['01', 'X', 'subject', '', '', 'first1', 'first2', 'reserved',
                        'collision', 'fallback', 'anon1', 'anon2', 'anon3']
    assert summary['analyses'] == ['B', 'A']
    assert summary['n_features'] == 8
    assert summary['duplicate_metabolites_dropped'] == [
        {'metabolite': 'shared', 'analysis_id': 'A', 'kept_from': 'B'},
        {'metabolite': 'shared', 'analysis_id': 'A', 'kept_from': 'B'}]
    assert config['feature_start_column'] == 6


@pytest.mark.parametrize('kind', ['phenotype', 'extra', 'technical', 'within', 'within_technical', 'missing'])
def test_conflicts_raise_name_and_write_nothing(tmp_path, kind):
    base = factor('01', 'Diet:X | Batch:001 | Age:10')
    if kind == 'phenotype':
        factors = [base, factor('01', 'Diet:Y | Batch:001 | Age:10')]
    elif kind == 'extra':
        factors = [base, factor('01', 'Diet:X | Batch:001 | Age:11')]
    elif kind == 'technical':
        factors = [base, factor('01', 'Diet:X | batch:002 | Age:10')]
    elif kind == 'within':
        factors = [factor('01', 'Diet:X | Diet:Y')]
    elif kind == 'within_technical':
        factors = [factor('01', 'Diet:X | Batch:001 | BATCH:002')]
    else:
        factors = [base, factor('01', 'Diet:X | Batch:001')]
    args = paths(tmp_path, factors, [feature('A', 'm', {'01': '1'})])
    with pytest.raises(Exception) as error:
        prepare(*args)
    assert '01' in str(error.value)
    assert not args[-1].exists() or not list(args[-1].iterdir())


def test_identical_duplicates_and_technical_aliases(tmp_path):
    factors = [factor('s', 'Diet:X | batch:001 | injection ORDER:04 | sample TYPE:QC | Age:10'),
               factor('s', 'Age:10 | Sample type:QC | Injection order:04 | Batch:001 | Diet:X'),
               factor('t', 'Diet:Y | BATCH:002 | Batch:002 | Injection Order:05 | Sample type:patient'),
               factor('t', 'Diet:Y | Batch:002 | Injection order:05 | sample type:patient')]
    table, summary, config = run(tmp_path, factors, [feature('A', 'm', {'s': '', 't': '9'})])
    assert table[0] == ['Samples', 'Phenotype', 'Age', 'Sample type', 'Batch', 'Injection order', 'm']
    assert table[2:] == [['s', '', '10', 'QC', '001', '04', ''],
                         ['t', 'Y', '', 'subject', '002', '05', '9']]
    assert summary['n_samples'] == 2
    assert summary['extra_factor_keys'] == ['Age']
    assert summary['phenotype_counts'] == {'Y': 1}
    assert config['qc_sample_types'] == ['QC']


@pytest.mark.parametrize('shape', ['list', 'mapping', 'bare'])
def test_record_container_formats(tmp_path, shape):
    f = factor('01', 'Diet:NA')
    d = feature('A', 'm', {'01': '0007'})
    if shape == 'list':
        f, d = [f], [d]
    elif shape == 'mapping':
        f, d = {'1': f}, {'1': d}
    table, summary, _ = run(tmp_path, f, d)
    assert table[2] == ['01', 'NA', 'subject', '', '', '0007']
    assert summary['phenotype_counts'] == {'NA': 1}


def test_cli_and_error(tmp_path):
    import prepare as module
    script = Path(module.__file__)
    args = paths(tmp_path / 'good', factor('01', 'Diet:NA'), feature('A', 'm', {'01': '1'}))
    command = [sys.executable, str(script), '--factors', str(args[0]), '--data', str(args[1]),
               '--task', str(args[2]), '--output', str(args[3])]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (args[-1] / 'prepared.csv').is_file()
    bad = paths(tmp_path / 'bad', [factor('broken-id', 'Diet:X'), factor('broken-id', 'Diet:Y')],
                feature('A', 'm', {'broken-id': '1'}))
    command = [sys.executable, str(script), '--factors', str(bad[0]), '--data', str(bad[1]),
               '--task', str(bad[2]), '--output', str(bad[3])]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'broken-id' in result.stderr
    assert not bad[-1].exists() or not list(bad[-1].iterdir())
