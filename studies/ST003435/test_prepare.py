import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from prepare import prepare


def factor(sample, values, **fields):
    return dict(local_sample_id=sample, mb_sample_id='MB_' + sample,
                sample_source=fields.pop('sample_source', 'biological source'),
                factors=values, **fields)


def feature(analysis, name, values, refmet_name=''):
    return dict(analysis_id=analysis, metabolite_name=name, refmet_name=refmet_name,
                units='arbitrary', DATA=values)


def write_case(tmp_path, factors, data, task=None):
    f, d, t = [tmp_path / name for name in ('factors.json', 'data.json', 'task.yaml')]
    f.write_text(json.dumps(factors), encoding='utf-8')
    d.write_text(json.dumps(data), encoding='utf-8')
    t.write_text(yaml.safe_dump(task if task is not None else {
        'phenotype_key': 'Drug Treatment',
        'control_sample_types': ['QC', 'PBQC', 'pool', 'blank'],
    }), encoding='utf-8')
    return f, d, t, tmp_path / 'out'


def run_case(tmp_path, factors, data, task=None):
    args = write_case(tmp_path, factors, data, task)
    prepare(*args)
    out = args[3]
    assert {p.name for p in out.iterdir()} == {'prepared.csv', 'summary.json', 'config.yaml'}
    assert all(p.is_file() and not p.is_symlink() for p in out.iterdir())
    with (out / 'prepared.csv').open(newline='', encoding='utf-8') as handle:
        table = list(csv.reader(handle))
    summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    config = yaml.safe_load((out / 'config.yaml').read_text(encoding='utf-8'))
    assert all(len(row) == len(table[0]) for row in table)
    assert summary['n_samples'] == len(table) - 2
    assert summary['n_features'] == len(table[0]) - config['feature_start_column'] + 1
    assert config['sample_metadata_header_row'] == 1
    assert config['feature_names_row'] == 1
    assert config['data_start_row'] == 3
    assert config['feature_metadata_label_column'] == 1
    assert config['sheet_name'] is None
    assert config['target_column'] == 'Phenotype'
    assert config['sample_column'] == 'Samples'
    assert config['sample_type_column'] == 'Sample type'
    assert config['batch_column'] == 'Batch'
    assert config['position_column'] == 'Injection order'
    return table, summary, config


def test_identifiers_text_na_labels_and_cells(tmp_path):
    ids = ['2', '01', '1', '10', ' A  B ']
    factors = [factor(s, ' Drug Treatment : NA | Zeta : end | Alpha : x:y ') for s in ids]
    values = {'2': '', '01': '0001.2300', '1': 'NA', '10': '1e-09', ' A  B ': ' 7.50 '}
    values['not a factor sample'] = '99'
    table, summary, config = run_case(tmp_path, factors, [feature('AN01', 'm', values)])
    assert table[0] == ['Samples', 'Phenotype', 'Alpha', 'Zeta', 'Sample type', 'Batch', 'Injection order', 'm']
    assert table[1] == ['METHOD', '', '', '', '', '', '', 'AN01']
    assert [r[0] for r in table[2:]] == sorted(ids)
    for row in table[2:]:
        assert row[1:7] == ['NA', 'x:y', 'end', 'subject', '', '']
        assert row[7] == values[row[0]]
    assert summary['phenotype_counts'] == {'NA': 5}
    assert summary['excluded_samples'] == {}
    assert summary['extra_factor_keys'] == ['Alpha', 'Zeta']
    assert summary['technical_columns_from_factors'] == []
    assert set(summary['blank_technical_columns']) == {'Batch', 'Injection order'}
    assert config['feature_start_column'] == 8
    assert config['qc_sample_types'] == []


@pytest.mark.parametrize('shape', ['list', 'object', 'bare'])
def test_input_wrappers_and_no_invented_technical_metadata(tmp_path, shape):
    f = factor('007', 'Drug Treatment:A', sample_source='_QC_',
               raw_data='batch9/run_002.wiff', batch='fake', injection_order='002')
    d = feature('AN1', 'm', {'007': None})
    if shape == 'list':
        f, d = [f], [d]
    elif shape == 'object':
        f, d = {'1': f}, {'1': d}
    table, summary, config = run_case(tmp_path, f, d)
    assert table == [
        ['Samples', 'Phenotype', 'Sample type', 'Batch', 'Injection order', 'm'],
        ['METHOD', '', '', '', '', 'AN1'],
        ['007', 'A', 'subject', '', '', ''],
    ]
    assert summary['technical_columns_from_factors'] == []
    assert set(summary['blank_technical_columns']) == {'Batch', 'Injection order'}
    assert config['qc_sample_types'] == []


def test_controls_mapping_keep_and_exclusion_precedence(tmp_path):
    fs = [
        factor('blank', 'Sample Type:bLaNk | Drug Treatment:bad'),
        factor('pool', 'sample type:pool'),
        factor('qc', 'SAMPLE TYPE:qC | Drug Treatment:'),
        factor('pb', 'Sample type:PBQC | Drug Treatment:NA'),
        factor('missing_control', 'Sample type:QC | Drug Treatment:bad'),
        factor('mapped', 'Drug Treatment:old | Sample type:ordinary'),
        factor('na', 'Drug Treatment:NA'),
        factor('no', 'Other:present'),
        factor('empty', 'Drug Treatment:   '),
        factor('bad', 'Drug Treatment:bad'),
        factor('unmeasured', 'Drug Treatment:old'),
        factor('sourceonly', 'Drug Treatment:bad', sample_source='_QC_'),
    ]
    vals = {s: '1' for s in ['blank', 'pool', 'qc', 'pb', 'mapped', 'na']}
    table, summary, config = run_case(tmp_path, fs, [feature('AN1', 'm', vals)], {
        'phenotype_key': 'Drug Treatment', 'map': {'old': 'renamed', 'bad': 'rejected'},
        'keep': ['renamed', 'NA'], 'control_sample_types': ['QC', 'PBQC', 'pool', 'blank'],
    })
    rows = {row[0]: row for row in table[2:]}
    assert set(rows) == {'blank', 'pool', 'qc', 'pb', 'mapped', 'na'}
    for sample, typ in [('blank', 'bLaNk'), ('pool', 'pool'), ('qc', 'qC'), ('pb', 'PBQC')]:
        assert rows[sample][1] == ''
        assert rows[sample][3] == typ  # Other is the extra factor, index 2.
    assert rows['mapped'][1] == 'renamed'
    assert rows['mapped'][3] == 'subject'
    assert rows['na'][1] == 'NA'
    assert summary['phenotype_counts'] == {'renamed': 1, 'NA': 1}
    assert summary['excluded_samples'] == {
        'missing_control': 'not measured in AN1', 'no': 'no phenotype', 'empty': 'no phenotype',
        'bad': 'phenotype not in keep: rejected', 'unmeasured': 'not measured in AN1',
        'sourceonly': 'phenotype not in keep: rejected',
    }
    assert set(config['qc_sample_types']) == {'bLaNk', 'pool', 'qC', 'PBQC'}
    assert summary['extra_factor_keys'] == ['Other']
    assert summary['technical_columns_from_factors'] == ['Sample type']
    assert set(summary['blank_technical_columns']) == {'Batch', 'Injection order'}
    assert {r[0] for r in table[2:]} | set(summary['excluded_samples']) == {f['local_sample_id'] for f in fs}


def test_technical_case_insensitive_factors_and_duplicate_collapse(tmp_path):
    fs = [factor('01', 'Drug Treatment:X | sample TYPE:QC | batch:001 | INJECTION ORDER:02 | Note:n'),
          factor('01', 'Note:n | Drug Treatment:X | Sample type:QC | Batch:001 | Injection order:02'),
          factor('1', 'Drug Treatment:Y | Sample Type:tissue | BATCH:NA | injection order:0007'),
          factor('2', 'Drug Treatment:Y')]
    table, summary, config = run_case(tmp_path, fs, [feature('AN1', 'm', {'01': '0', '1': '', '2': '2'})])
    assert table[0] == ['Samples', 'Phenotype', 'Note', 'Sample type', 'Batch', 'Injection order', 'm']
    assert table[2:] == [
        ['01', '', 'n', 'QC', '001', '02', '0'],
        ['1', 'Y', '', 'subject', 'NA', '0007', ''],
        ['2', 'Y', '', 'subject', '', '', '2'],
    ]
    assert set(summary['technical_columns_from_factors']) == {'Sample type', 'Batch', 'Injection order'}
    assert summary['blank_technical_columns'] == []
    assert summary['phenotype_counts'] == {'Y': 2}
    assert config['qc_sample_types'] == ['QC']


@pytest.mark.parametrize('first,second', [
    ('Drug Treatment:A', 'Drug Treatment:B'),
    ('Drug Treatment:A | Extra:x', 'Drug Treatment:A | Extra:y'),
    ('Drug Treatment:A | Batch:1', 'Drug Treatment:A | batch:2'),
    ('Drug Treatment:A | Sample type:QC', 'Drug Treatment:A | SAMPLE TYPE:blank'),
    ('Drug Treatment:A | Injection order:01', 'Drug Treatment:A | injection ORDER:1'),
    ('Drug Treatment:A | Extra:x', 'Drug Treatment:A'),
])
def test_conflicting_records_raise_and_write_nothing(tmp_path, first, second):
    fs = [factor('bad sample 01', first), factor('bad sample 01', second)]
    args = write_case(tmp_path, fs, [feature('AN1', 'm', {'bad sample 01': '1'})], {
        'phenotype_key': 'Drug Treatment', 'keep': ['not present'], 'control_sample_types': ['QC'],
    })
    args[3].mkdir()
    with pytest.raises(Exception) as exc:
        prepare(*args)
    assert 'bad sample 01' in str(exc.value)
    assert list(args[3].iterdir()) == []


@pytest.mark.parametrize('factors', [
    'Drug Treatment:A | Drug Treatment:B',
    'Drug Treatment:A | Batch:1 | batch:2',
    'Drug Treatment:A | Sample type:QC | sample TYPE:PBQC',
    'Drug Treatment:A | Injection order:2 | injection ORDER:3',
    'Drug Treatment:A | Extra:x | Extra:y',
])
def test_conflicts_inside_record(tmp_path, factors):
    args = write_case(tmp_path, [factor('01 conflict', factors)], [feature('AN1', 'm', {})])
    with pytest.raises(Exception) as exc:
        prepare(*args)
    assert '01 conflict' in str(exc.value)
    assert not args[3].exists() or not list(args[3].iterdir())


def test_identical_repeated_factor_values_allowed(tmp_path):
    fs = [factor('s', 'Drug Treatment:A | Drug Treatment:A | batch:1 | Batch:1 | Extra:x | Extra:x')]
    table, summary, _ = run_case(tmp_path, fs, [feature('AN1', 'm', {'s': '1'})])
    assert table[2] == ['s', 'A', 'x', 'subject', '1', '', '1']
    assert summary['n_samples'] == 1


def test_measurement_intersection_includes_dropped_records(tmp_path):
    ids = ['all', 'in dropped', 'blank', 'only A', 'only Z', 'none']
    fs = [factor(s, 'Drug Treatment:A') for s in ids]
    ds = [
        feature('A', 'shared', {'all': 'a', 'in dropped': 'a2', 'blank': '', 'only A': '3'}),
        feature('Z', 'kept', {'all': 'z', 'blank': None, 'only Z': '4'}),
        feature('Z', 'shared', {'in dropped': 'membership here'}),
        feature('A', 'sparse', {'all': '000.10'}),
    ]
    table, summary, _ = run_case(tmp_path, fs, ds)
    assert summary['analyses'] == ['A', 'Z']
    assert table[0] == ['Samples', 'Phenotype', 'Sample type', 'Batch', 'Injection order', 'shared', 'sparse', 'kept']
    assert table[1] == ['METHOD', '', '', '', '', 'A', 'A', 'Z']
    assert table[2:] == [
        ['all', 'A', 'subject', '', '', 'a', '000.10', 'z'],
        ['blank', 'A', 'subject', '', '', '', '', ''],
        ['in dropped', 'A', 'subject', '', '', 'a2', '', ''],
    ]
    assert summary['excluded_samples'] == {'only A': 'not measured in Z', 'only Z': 'not measured in A', 'none': 'not measured in A'}
    assert summary['duplicate_metabolites_dropped'] == [{'metabolite': 'shared', 'analysis_id': 'Z', 'kept_from': 'A'}]


def test_analysis_priority_deduplication_names_and_header_collisions(tmp_path):
    fs = [factor('s', 'Drug Treatment:A')]
    # Interleaved records: priority, not input order, chooses the source.
    ds = [feature('A', 'x', {'s': 'a1'}),
          feature('Z', 'x', {'s': 'z1'}),
          feature('A', 'x', {'s': 'a2'}),
          feature('Z', 'x', {'s': 'z2'}),
          feature('Z', 'x.1', {'s': 'explicit'}),
          feature('Z', 'Samples', {'s': 'collision'}),
          feature('Z', ' ', {'s': 'fallback'}, 'ref'),
          feature('Z', '', {'s': 'u1'}, ' '),
          feature('Z', None, {'s': 'u2'}, None),
          feature('A', '', {'s': 'u3'}),
          feature('A', 'ref', {'s': 'refcopy'}),
          feature('A', 'other', {'s': 'other'}),
          feature('IGNORED', 'ignore', {}),
          feature('Z', 'Batch', {'s': 'batchcollision'}),
          feature('Z', 'Phenotype', {'s': 'phenocollision'})]
    table, summary, config = run_case(tmp_path, fs, ds, {
        'phenotype_key': 'Drug Treatment', 'analyses': ['Z', 'A'], 'control_sample_types': ['QC'],
    })
    assert summary['analyses'] == ['Z', 'A']
    assert table[0] == ['Samples', 'Phenotype', 'Sample type', 'Batch', 'Injection order',
                        'x', 'x.2', 'x.1', 'Samples.1', 'ref', 'unnamed', 'unnamed.1',
                        'Batch.1', 'Phenotype.1', 'unnamed.2', 'other']
    assert len(set(table[0])) == len(table[0])
    assert table[1] == ['METHOD', '', '', '', ''] + ['Z'] * 9 + ['A'] * 2
    assert table[2] == ['s', 'A', 'subject', '', '', 'z1', 'z2', 'explicit', 'collision',
                         'fallback', 'u1', 'u2', 'batchcollision', 'phenocollision', 'u3', 'other']
    assert summary['duplicate_metabolites_dropped'] == [
        {'metabolite': 'x', 'analysis_id': 'A', 'kept_from': 'Z'},
        {'metabolite': 'x', 'analysis_id': 'A', 'kept_from': 'Z'},
        {'metabolite': 'ref', 'analysis_id': 'A', 'kept_from': 'Z'},
    ]
    assert config['feature_start_column'] == 6


def test_metadata_header_collision_and_reserved_suffixes(tmp_path):
    fs = [factor('s', 'Drug Treatment:A | Samples:metadata | Samples.1:reserved | Z:z')]
    ds = [feature('A', n, {'s': str(i)}) for i, n in enumerate(['Samples', 'Samples', 'Samples.2', 'Z', 'Z.1', 'Z'])]
    table, summary, config = run_case(tmp_path, fs, ds)
    assert table[0] == ['Samples', 'Phenotype', 'Samples.3', 'Samples.1', 'Z', 'Sample type', 'Batch', 'Injection order',
                        'Samples.4', 'Samples.5', 'Samples.2', 'Z.2', 'Z.1', 'Z.3']
    assert table[2] == ['s', 'A', 'metadata', 'reserved', 'z', 'subject', '', '', '0', '1', '2', '3', '4', '5']
    assert summary['extra_factor_keys'] == ['Samples', 'Samples.1', 'Z']
    assert config['feature_start_column'] == 9


def test_all_excluded_still_writes_headers_and_summary(tmp_path):
    fs = [factor('a', 'Drug Treatment:'), factor('b', 'Drug Treatment:X')]
    table, summary, config = run_case(tmp_path, fs, [feature('A', 'm', {})], {
        'phenotype_key': 'Drug Treatment', 'keep': [],
    })
    assert len(table) == 2
    assert summary['n_samples'] == 0
    assert summary['phenotype_counts'] == {}
    assert summary['excluded_samples'] == {'a': 'no phenotype', 'b': 'phenotype not in keep: X'}
    assert config['qc_sample_types'] == []


def test_cli_success_and_conflict_diagnostic(tmp_path):
    script = Path(__file__).with_name('prepare.py')
    args = write_case(tmp_path, [factor('01', 'Drug Treatment:NA')], [feature('A', 'm', {'01': '2.00'})])
    command = [sys.executable, str(script), '--factors', str(args[0]), '--data', str(args[1]),
               '--task', str(args[2]), '--output', str(args[3])]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with (args[3] / 'prepared.csv').open(newline='') as handle:
        assert list(csv.reader(handle))[2] == ['01', 'NA', 'subject', '', '', '2.00']
    for p in args[3].iterdir():
        p.unlink()
    args[0].write_text(json.dumps([factor('01', 'Drug Treatment:A'), factor('01', 'Drug Treatment:B')]))
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert '01' in result.stderr
    assert not list(args[3].iterdir())
