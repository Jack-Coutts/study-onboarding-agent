import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from prepare import prepare


def factor(sample, factors, source='Plant'):
    return {'local_sample_id': sample, 'mb_sample_id': 'mb-' + sample,
            'sample_source': source, 'factors': factors}


def feature(analysis, name, values, ref=''):
    return {'analysis_id': analysis, 'metabolite_name': name,
            'refmet_name': ref, 'units': 'Peak height', 'DATA': values}


def inputs(tmp_path, factors, data, task):
    f, d, t = (tmp_path / name for name in ('factors.json', 'data.json', 'task.yaml'))
    f.write_text(json.dumps(factors), encoding='utf-8')
    d.write_text(json.dumps(data), encoding='utf-8')
    t.write_text(yaml.safe_dump(task), encoding='utf-8')
    return f, d, t, tmp_path / 'out'


def load(out):
    assert {p.name for p in out.iterdir() if p.is_file() and not p.is_symlink()} == {
        'prepared.csv', 'summary.json', 'config.yaml'}
    with (out / 'prepared.csv').open(newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    return rows, json.loads((out / 'summary.json').read_text()), yaml.safe_load((out / 'config.yaml').read_text())


def test_text_identifiers_labels_values_and_no_invented_technical(tmp_path):
    factors = [factor('1', 'Outcome:NA | Z:value:with:colon | A:x'),
               factor('01', 'Outcome:Control | Z:NA'),
               factor(' 1 ', 'Outcome:Control | A:001'),
               factor('missing', 'A:no outcome'),
               factor('empty', 'Outcome:   '),
               factor('lost', 'Outcome:Control')]
    data = [feature('AN2', 'm', {'1': 'NA', '01': '0007.00', ' 1 ': ' 4.00 ', 'missing': '1', 'empty': '2'})]
    paths = inputs(tmp_path, factors, data, {'phenotype_key': 'Outcome', 'map': {'Control': 'control'}})
    prepare(*paths)
    rows, summary, config = load(paths[-1])
    assert rows == [
        ['Samples', 'Phenotype', 'A', 'Z', 'Sample type', 'Batch', 'Injection order', 'm'],
        ['METHOD', '', '', '', '', '', '', 'AN2'],
        [' 1 ', 'control', '001', '', 'subject', '', '', ' 4.00 '],
        ['01', 'control', '', 'NA', 'subject', '', '', '0007.00'],
        ['1', 'NA', 'x', 'value:with:colon', 'subject', '', '', 'NA']]
    assert summary == {
        'n_samples': 3, 'n_features': 1, 'phenotype_counts': {'control': 2, 'NA': 1},
        'analyses': ['AN2'], 'extra_factor_keys': ['A', 'Z'],
        'excluded_samples': {'missing': 'no phenotype', 'empty': 'no phenotype', 'lost': 'not measured in AN2'},
        'duplicate_metabolites_dropped': [], 'technical_columns_from_factors': [],
        'blank_technical_columns': ['Batch', 'Injection order']}
    assert config == {'sample_metadata_header_row': 1, 'feature_names_row': 1, 'data_start_row': 3,
                      'feature_start_column': 8, 'feature_metadata_label_column': 1, 'sheet_name': None,
                      'target_column': 'Phenotype', 'sample_column': 'Samples', 'sample_type_column': 'Sample type',
                      'batch_column': 'Batch', 'position_column': 'Injection order', 'qc_sample_types': []}


def test_controls_keep_mapping_and_case_insensitive_technical(tmp_path):
    factors = [factor('01', 'Outcome:old | sample TYPE:QC | batch:B01 | injection ORDER:003'),
               factor('02', 'Sample type:pBqC'),
               factor('03', 'Outcome:not-kept | SAMPLE TYPE:pool | Batch:B02'),
               factor('04', 'Outcome: | Sample type:blank'),
               factor('05', 'Outcome:old | Sample type:specimen | Batch:007 | Injection order:0002'),
               factor('06', 'Outcome:old'),
               factor('07', 'Outcome:other | Sample type:Plant'),
               factor('08', 'Sample type:Plant'),
               factor('09', 'Outcome:other | Sample type:QC')]
    values = {str(i).zfill(2): str(i) for i in range(1, 9)}
    paths = inputs(tmp_path, factors, [feature('A', 'f', values)],
                   {'phenotype_key': 'Outcome', 'map': {'old': 'new'}, 'keep': ['new'],
                    'control_sample_types': ['qc', 'PBQC', 'POOL', 'blank']})
    prepare(*paths)
    rows, summary, config = load(paths[-1])
    assert rows[0] == ['Samples', 'Phenotype', 'Sample type', 'Batch', 'Injection order', 'f']
    assert rows[2:] == [
        ['01', '', 'QC', 'B01', '003', '1'], ['02', '', 'pBqC', '', '', '2'],
        ['03', '', 'pool', 'B02', '', '3'], ['04', '', 'blank', '', '', '4'],
        ['05', 'new', 'subject', '007', '0002', '5'], ['06', 'new', 'subject', '', '', '6']]
    assert summary['phenotype_counts'] == {'new': 2}
    assert summary['n_samples'] == 6
    assert summary['extra_factor_keys'] == []
    assert set(summary['technical_columns_from_factors']) == {'Sample type', 'Batch', 'Injection order'}
    assert summary['blank_technical_columns'] == []
    assert summary['excluded_samples'] == {'07': 'phenotype not in keep: other', '08': 'no phenotype', '09': 'not measured in A'}
    assert set(config['qc_sample_types']) == {'QC', 'pBqC', 'pool', 'blank'}


def test_analysis_priority_dedup_union_coverage_and_exclusion_order(tmp_path):
    factors = [factor(s, f'Outcome:{label}') for s, label in
               [('both', 'old'), ('one', 'old'), ('none', 'old'), ('blank', 'old'), ('no-pheno', ''), ('bad-label', 'bad')]]
    data = [feature('A', 'shared', {'both': 'A', 'one': '1', 'no-pheno': '0'}),
            feature('B', 'shared', {'both': 'B'}),
            feature('B', 'second', {'blank': '', 'bad-label': '1'}),
            feature('A', 'third', {'blank': ''}),
            feature('C', 'ignored', {})]
    paths = inputs(tmp_path, factors, data, {'phenotype_key': 'Outcome', 'analyses': ['B', 'A'],
                   'map': {'old': 'good'}, 'keep': ['good']})
    prepare(*paths)
    rows, summary, config = load(paths[-1])
    assert rows[0] == ['Samples', 'Phenotype', 'Sample type', 'Batch', 'Injection order', 'shared', 'second', 'third']
    assert rows[1] == ['METHOD', '', '', '', '', 'B', 'B', 'A']
    assert rows[2:] == [['blank', 'good', 'subject', '', '', '', '', ''],
                        ['both', 'good', 'subject', '', '', 'B', '', '']]
    assert summary['analyses'] == ['B', 'A']
    assert summary['duplicate_metabolites_dropped'] == [{'metabolite': 'shared', 'analysis_id': 'A', 'kept_from': 'B'}]
    assert summary['excluded_samples'] == {'one': 'not measured in B', 'none': 'not measured in B',
                                          'no-pheno': 'no phenotype', 'bad-label': 'phenotype not in keep: bad'}
    assert summary['n_features'] == 3
    assert summary['n_samples'] == 2
    assert config['feature_start_column'] == 6


def test_dropped_records_still_establish_measurement(tmp_path):
    paths = inputs(tmp_path, [factor('s', 'Outcome:NA')],
                   [feature('Z', 'm', {'s': ''}), feature('A', 'm', {'s': '001'}),
                    feature('Z', 'other', {})], {'phenotype_key': 'Outcome'})
    prepare(*paths)
    rows, summary, _ = load(paths[-1])
    assert summary['analyses'] == ['A', 'Z']
    assert rows[1] == ['METHOD', '', '', '', '', 'A', 'Z']
    assert rows[2] == ['s', 'NA', 'subject', '', '', '001', '']
    assert summary['excluded_samples'] == {}
    assert summary['duplicate_metabolites_dropped'] == [{'metabolite': 'm', 'analysis_id': 'Z', 'kept_from': 'A'}]


def test_repeated_feature_names_reserved_suffixes_and_metadata_collisions(tmp_path):
    names = [('x', ''), ('x', ''), ('x.1', ''), ('x', ''), ('Samples', ''),
             ('', 'fallback'), ('   ', ' '), ('', ''), ('', 'fallback')]
    data = [feature('A', name, {'s': str(i)}, ref) for i, (name, ref) in enumerate(names)]
    data += [feature('B', 'x', {'s': 'drop'}), feature('B', '', {'s': '9'})]
    paths = inputs(tmp_path, [factor('s', 'Outcome:yes')], data, {'phenotype_key': 'Outcome'})
    prepare(*paths)
    rows, summary, _ = load(paths[-1])
    assert rows[0] == ['Samples', 'Phenotype', 'Sample type', 'Batch', 'Injection order',
                       'x', 'x.2', 'x.1', 'x.3', 'Samples.1', 'fallback', 'unnamed', 'unnamed.1', 'fallback.1', 'unnamed.2']
    assert rows[1] == ['METHOD', '', '', '', ''] + ['A'] * 9 + ['B']
    assert rows[2][5:] == [str(i) for i in range(10)]
    assert summary['n_features'] == 10
    assert summary['duplicate_metabolites_dropped'] == [{'metabolite': 'x', 'analysis_id': 'B', 'kept_from': 'A'}]


@pytest.mark.parametrize('shape', ['list', 'object', 'bare'])
def test_input_record_shapes_and_identical_duplicates(tmp_path, shape):
    f = factor('0001', 'Outcome:NA | Batch:B | batch:B')
    d = feature('0002', 'm', {'0001': '0'})
    fs = [f, dict(f)] if shape == 'list' else ({'1': f, '2': dict(f)} if shape == 'object' else f)
    ds = [d] if shape == 'list' else ({'1': d} if shape == 'object' else d)
    paths = inputs(tmp_path, fs, ds, {'phenotype_key': 'Outcome'})
    prepare(*paths)
    rows, summary, _ = load(paths[-1])
    assert rows[2:] == [['0001', 'NA', 'subject', 'B', '', '0']]
    assert rows[1][-1] == '0002'
    assert summary['n_samples'] == 1
    assert summary['technical_columns_from_factors'] == ['Batch']
    assert summary['blank_technical_columns'] == ['Injection order']


@pytest.mark.parametrize('factor_strings', [
    ['Outcome:yes | Outcome:no'],
    ['Outcome:yes | Batch:a | batch:b'],
    ['Outcome:yes | Sample type:QC | SAMPLE TYPE:blank'],
    ['Outcome:yes | Injection order:01 | injection ORDER:1'],
    ['Outcome:yes', 'Outcome:no'],
    ['Outcome:yes | Extra:a', 'Outcome:yes | Extra:b'],
    ['Outcome:yes | Batch:a', 'Outcome:yes | batch:b'],
])
def test_conflicts_raise_name_and_write_nothing(tmp_path, factor_strings):
    paths = inputs(tmp_path, [factor('01 conflict', value) for value in factor_strings],
                   [feature('A', 'm', {'01 conflict': '1'})], {'phenotype_key': 'Outcome'})
    paths[-1].mkdir()
    with pytest.raises(Exception) as error:
        prepare(*paths)
    assert '01 conflict' in str(error.value)
    assert list(paths[-1].iterdir()) == []


def test_cli_conflict_stderr_and_no_output(tmp_path):
    paths = inputs(tmp_path, [factor('001', 'Outcome:yes | Outcome:no')],
                   [feature('A', 'm', {'001': '1'})], {'phenotype_key': 'Outcome'})
    script = Path(prepare.__code__.co_filename).resolve()
    result = subprocess.run([sys.executable, str(script), '--factors', str(paths[0]), '--data', str(paths[1]),
                             '--task', str(paths[2]), '--output', str(paths[3])], capture_output=True, text=True)
    assert result.returncode != 0
    assert '001' in result.stderr
    assert not paths[-1].exists() or list(paths[-1].iterdir()) == []


def test_cli_success(tmp_path):
    paths = inputs(tmp_path, factor('01', 'Outcome:NA'), feature('A', 'm', {'01': '2'}), {'phenotype_key': 'Outcome'})
    script = Path(prepare.__code__.co_filename).resolve()
    result = subprocess.run([sys.executable, str(script), '--factors', str(paths[0]), '--data', str(paths[1]),
                             '--task', str(paths[2]), '--output', str(paths[3])], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    rows, summary, _ = load(paths[-1])
    assert rows[2] == ['01', 'NA', 'subject', '', '', '2']
    assert summary['phenotype_counts'] == {'NA': 1}
