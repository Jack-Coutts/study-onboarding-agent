import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from prepare import prepare


def factor(sample, values):
    return {'local_sample_id': sample, 'mb_sample_id': 'mb_' + sample,
            'sample_source': 'pool', 'factors': values}


def feature(analysis, name, values, ref=''):
    return {'analysis_id': analysis, 'metabolite_name': name,
            'refmet_name': ref, 'units': 'area', 'DATA': values}


def inputs(tmp_path, factors, data, task=None):
    f = tmp_path / 'factors.json'
    d = tmp_path / 'data.json'
    t = tmp_path / 'task.yaml'
    o = tmp_path / 'out'
    f.write_text(json.dumps(factors), encoding='utf-8')
    d.write_text(json.dumps(data), encoding='utf-8')
    t.write_text(yaml.safe_dump(task or {'phenotype_key': 'Group',
                                       'control_sample_types': ['QC', 'PBQC', 'pool', 'blank']}),
                 encoding='utf-8')
    return f, d, t, o


def run(tmp_path, factors, data, task=None):
    paths = inputs(tmp_path, factors, data, task)
    prepare(*paths)
    o = paths[-1]
    assert {p.name for p in o.iterdir()} == {'prepared.csv', 'summary.json', 'config.yaml'}
    assert all(p.is_file() and not p.is_symlink() for p in o.iterdir())
    with (o / 'prepared.csv').open(encoding='utf-8', newline='') as handle:
        table = list(csv.reader(handle))
    summary = json.loads((o / 'summary.json').read_text(encoding='utf-8'))
    config = yaml.safe_load((o / 'config.yaml').read_text(encoding='utf-8'))
    return table, summary, config


def test_ids_labels_controls_coverage_and_blank_technical(tmp_path):
    factors = [factor('01', 'Group:NA | Z: a:b | A:first'),
               factor('1', 'Group:old | A:second'),
               factor(' a b ', 'Group:old'),
               factor('qc', 'Sample TYPE:qC | Group:excluded'),
               factor('pool', 'sample type:pool'),
               factor('pb', 'Sample type:PBQC | Group:'),
               factor('blank', 'Sample type:Blank | Group:no'),
               factor('only-first', 'Group:NA'),
               factor('only-second', 'Group:NA'),
               factor('neither', 'Group:NA'),
               factor('bad', 'Group:bad'),
               factor('missing', 'Z:a'), factor('empty', 'Group: ')]
    kept = ['01', '1', ' a b ', 'qc', 'pool', 'pb', 'blank']
    first = {s: '001.2300' for s in kept + ['only-first']}
    second = {s: '2' for s in kept + ['only-second']}
    first['01'] = ''
    data = [feature('B', 'second', second), feature('A', 'first', first),
            feature('A', 'sparse', {'1': 'NA'})]
    task = {'phenotype_key': 'Group', 'analyses': ['A', 'B'],
            'map': {'old': 'case'}, 'keep': ['NA', 'case'],
            'control_sample_types': ['QC', 'PBQC', 'pool', 'blank']}
    table, summary, config = run(tmp_path, factors, data, task)
    assert table[0] == ['Samples', 'Phenotype', 'A', 'Z', 'Sample type', 'Batch',
                        'Injection order', 'first', 'sparse', 'second']
    assert table[1] == ['METHOD', '', '', '', '', '', '', 'A', 'A', 'B']
    assert [r[0] for r in table[2:]] == sorted(kept)
    by_id = {r[0]: r for r in table[2:]}
    assert by_id['01'] == ['01', 'NA', 'first', 'a:b', 'subject', '', '', '', '', '2']
    assert by_id['1'] == ['1', 'case', 'second', '', 'subject', '', '', '001.2300', 'NA', '2']
    assert by_id[' a b '][1:7] == ['case', '', '', 'subject', '', '']
    for sample, sample_type in [('qc', 'qC'), ('pool', 'pool'), ('pb', 'PBQC'), ('blank', 'Blank')]:
        assert by_id[sample][1] == ''
        assert by_id[sample][4] == sample_type
    assert all(r[5:7] == ['', ''] for r in table[2:])
    assert summary == {
        'n_samples': 7, 'n_features': 3, 'phenotype_counts': {'NA': 1, 'case': 2},
        'analyses': ['A', 'B'], 'extra_factor_keys': ['A', 'Z'],
        'excluded_samples': {'only-first': 'not measured in B',
                             'only-second': 'not measured in A',
                             'neither': 'not measured in A',
                             'bad': 'phenotype not in keep: bad',
                             'missing': 'no phenotype', 'empty': 'no phenotype'},
        'duplicate_metabolites_dropped': [],
        'technical_columns_from_factors': ['Sample type'],
        'blank_technical_columns': ['Batch', 'Injection order']}
    assert config == {
        'sample_metadata_header_row': 1, 'feature_names_row': 1, 'data_start_row': 3,
        'feature_start_column': 8, 'feature_metadata_label_column': 1, 'sheet_name': None,
        'target_column': 'Phenotype', 'sample_column': 'Samples',
        'sample_type_column': 'Sample type', 'batch_column': 'Batch',
        'position_column': 'Injection order', 'qc_sample_types': sorted(['qC', 'pool', 'PBQC', 'Blank'])}


def test_priority_repeated_names_fallbacks_and_header_reservations(tmp_path):
    factors = [factor('s', 'Group:yes | Samples:extra')]
    data = [feature('A', 'dup', {'s': 'later1'}),
            feature('B', 'dup', {'s': 'first'}),
            feature('A', 'dup', {'s': 'later2'}),
            feature('B', 'dup', {'s': 'repeat'}),
            feature('B', 'dup.1', {'s': 'literal'}),
            feature('B', 'Samples', {'s': 'reserved'}),
            feature('B', 'Phenotype', {'s': 'reserved2'}),
            feature('B', '   ', {'s': 'ref'}, ref='fallback'),
            feature('B', '', {'s': 'u1'}),
            feature('A', 'fallback', {'s': 'drop'}),
            feature('A', '', {'s': 'u2'}),
            feature('A', 'unique', {'s': 'last'}),
            feature('C', 'ignored', {'s': 'ignored'})]
    task = {'phenotype_key': 'Group', 'analyses': ['B', 'A'], 'control_sample_types': []}
    table, summary, config = run(tmp_path, factors, data, task)
    assert table[0] == ['Samples', 'Phenotype', 'Samples.1', 'Sample type', 'Batch',
                        'Injection order', 'dup', 'dup.2', 'dup.1', 'Samples.2',
                        'Phenotype.1', 'fallback', 'unnamed', 'unnamed.1', 'unique']
    assert len(set(table[0])) == len(table[0])
    assert table[1] == ['METHOD'] + [''] * 5 + ['B'] * 7 + ['A'] * 2
    assert table[2] == ['s', 'yes', 'extra', 'subject', '', '', 'first', 'repeat',
                        'literal', 'reserved', 'reserved2', 'ref', 'u1', 'u2', 'last']
    assert summary['n_features'] == 9
    assert summary['analyses'] == ['B', 'A']
    assert summary['duplicate_metabolites_dropped'] == [
        {'metabolite': 'dup', 'analysis_id': 'A', 'kept_from': 'B'},
        {'metabolite': 'dup', 'analysis_id': 'A', 'kept_from': 'B'},
        {'metabolite': 'fallback', 'analysis_id': 'A', 'kept_from': 'B'}]
    assert config['feature_start_column'] == 7


def test_technical_factor_case_and_identical_duplicates(tmp_path):
    factors = [factor('01', 'Group:NA | batch:01 | injection ORDER:002 | SAMPLE TYPE:QC | Z:z'),
               factor('01', 'Z:z | Sample type:QC | Group:NA | Batch:01 | Injection order:002'),
               factor('1', 'Group:case | Batch:1 | injection order:01 | sample type:tissue | A:a'),
               factor('2', 'Group:case | A:a')]
    table, summary, config = run(tmp_path, factors, [feature('X', 'f', {'01': '', '1': '03', '2': '4'})])
    assert table[0] == ['Samples', 'Phenotype', 'A', 'Z', 'Sample type', 'Batch', 'Injection order', 'f']
    assert table[2] == ['01', '', '', 'z', 'QC', '01', '002', '']
    assert table[3] == ['1', 'case', 'a', '', 'subject', '1', '01', '03']
    assert table[4] == ['2', 'case', 'a', '', 'subject', '', '', '4']
    assert summary['n_samples'] == 3
    assert summary['technical_columns_from_factors'] == ['Sample type', 'Batch', 'Injection order']
    assert summary['blank_technical_columns'] == []
    assert config['qc_sample_types'] == ['QC']


@pytest.mark.parametrize('factors', [
    [factor('conflict-01', 'Group:a'), factor('conflict-01', 'Group:b')],
    [factor('conflict-01', 'Group:a | Batch:1'), factor('conflict-01', 'Group:a | batch:2')],
    [factor('conflict-01', 'Group:a | Z:1'), factor('conflict-01', 'Group:a | Z:2')],
    [factor('conflict-01', 'Group:a | Group:b')],
    [factor('conflict-01', 'Group:a | Batch:1 | bAtCh:2')],
    [factor('conflict-01', 'Group:a | Sample type:QC | SAMPLE TYPE:blank')],
    [factor('conflict-01', 'Group:a | Injection order:1 | INJECTION ORDER:2')],
])
def test_conflicts_raise_without_outputs_and_cli_reports_sample(tmp_path, factors):
    paths = inputs(tmp_path, factors, [feature('A', 'f', {'conflict-01': '1'})])
    with pytest.raises(Exception, match='conflict-01'):
        prepare(*paths)
    assert not paths[-1].exists() or not list(paths[-1].iterdir())
    proc = subprocess.run([sys.executable, str(Path(__file__).with_name('prepare.py')),
                           '--factors', str(paths[0]), '--data', str(paths[1]),
                           '--task', str(paths[2]), '--output', str(paths[3])],
                          capture_output=True, text=True)
    assert proc.returncode != 0
    assert 'conflict-01' in proc.stderr
    assert not paths[-1].exists() or not list(paths[-1].iterdir())


@pytest.mark.parametrize('shape', ['list', 'mapping', 'bare'])
def test_input_shapes_and_sorted_default_analyses(tmp_path, shape):
    f = [factor('001', ' Group : NA | Note : first:second ')]
    d = [feature('Z', 'z', {'001': '1e-03'})]
    if shape != 'bare':
        d.append(feature('A', 'a', {'001': ''}))
    if shape == 'mapping':
        f = {'1': f[0]}
        d = {str(i + 1): r for i, r in enumerate(d)}
    elif shape == 'bare':
        f, d = f[0], d[0]
    table, summary, config = run(tmp_path, f, d)
    assert table[0][:6] == ['Samples', 'Phenotype', 'Note', 'Sample type', 'Batch', 'Injection order']
    assert table[2][:6] == ['001', 'NA', 'first:second', 'subject', '', '']
    assert summary['phenotype_counts'] == {'NA': 1}
    assert summary['analyses'] == (['Z'] if shape == 'bare' else ['A', 'Z'])
    assert table[2][6:] == (['1e-03'] if shape == 'bare' else ['', '1e-03'])
    assert config['feature_start_column'] == 7
    assert config['qc_sample_types'] == []


def test_controls_still_require_all_analyses_including_dropped_records(tmp_path):
    factors = [factor('q', 'Sample type:QC'), factor('s', 'Group:yes'),
               factor('q2', 'Sample type:pool')]
    data = [feature('A', 'same', {'q': '', 's': '1', 'q2': '1'}),
            feature('B', 'same', {'q': '', 's': '2'})]
    table, summary, config = run(tmp_path, factors, data,
        {'phenotype_key': 'Group', 'analyses': ['A', 'B'], 'keep': ['yes'],
         'control_sample_types': ['QC', 'pool']})
    assert [r[0] for r in table[2:]] == ['q', 's']
    assert table[2] == ['q', '', 'QC', '', '', '']
    assert summary['excluded_samples'] == {'q2': 'not measured in B'}
    assert summary['n_features'] == 1
    assert config['qc_sample_types'] == ['QC']


def test_no_kept_samples_is_valid(tmp_path):
    table, summary, config = run(tmp_path, [factor('s', 'Group: ')],
                                 [feature('A', 'f', {'s': '1'})])
    assert len(table) == 2
    assert summary['n_samples'] == 0
    assert summary['phenotype_counts'] == {}
    assert summary['excluded_samples'] == {'s': 'no phenotype'}
    assert config['qc_sample_types'] == []


def test_absent_phenotype_requires_review_before_writing(tmp_path):
    paths = inputs(tmp_path, [factor('s', 'Other:a')], [feature('A', 'f', {'s': '1'})])
    with pytest.raises(Exception, match='Group'):
        prepare(*paths)
    assert not paths[-1].exists() or not list(paths[-1].iterdir())
