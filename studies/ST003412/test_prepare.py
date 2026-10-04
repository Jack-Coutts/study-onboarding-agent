import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from prepare import prepare


def factor(sample, factors, source='QC'):
    return {'local_sample_id': sample, 'mb_sample_id': 'MB_' + sample,
            'sample_source': source, 'factors': factors}


def feature(analysis, name, values, ref=''):
    return {'analysis_id': analysis, 'metabolite_name': name, 'refmet_name': ref,
            'units': 'counts', 'DATA': values}


def inputs(tmp_path, factors, data, task=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    f, d, t, out = [tmp_path / n for n in ('factors.json', 'data.json', 'task.yaml', 'out')]
    f.write_text(json.dumps(factors), encoding='utf-8')
    d.write_text(json.dumps(data), encoding='utf-8')
    t.write_text(yaml.safe_dump(task if task is not None else {
        'phenotype_key': 'Drug', 'control_sample_types': ['QC', 'PBQC', 'pool', 'blank']
    }), encoding='utf-8')
    return f, d, t, out


def run(tmp_path, factors, data, task=None):
    paths = inputs(tmp_path, factors, data, task)
    prepare(*paths)
    out = paths[-1]
    assert {p.name for p in out.iterdir() if p.is_file()} == {
        'prepared.csv', 'summary.json', 'config.yaml'}
    assert not any(p.is_symlink() or p.is_dir() for p in out.iterdir())
    with (out / 'prepared.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.reader(stream))
    summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    config = yaml.safe_load((out / 'config.yaml').read_text(encoding='utf-8'))
    return rows, summary, config


def test_text_ids_labels_and_no_invented_technical_metadata(tmp_path):
    factors = [factor(s, 'Drug: NA | Z: v:a | Alpha: text')
               for s in ['1', '01', '10', '2', ' A  B ']]
    vals = {'1': '001.2300', '01': '0', '10': 'NA', '2': '1e-05', ' A  B ': ' 5 '}
    rows, summary, config = run(tmp_path, factors, [feature('AN01', 'm', vals)])
    assert rows[0] == ['Samples', 'Phenotype', 'Alpha', 'Z', 'Sample type', 'Batch', 'Injection order', 'm']
    assert rows[1] == ['METHOD', '', '', '', '', '', '', 'AN01']
    assert rows[2:] == [[s, 'NA', 'text', 'v:a', 'subject', '', '', vals[s]] for s in sorted(vals)]
    assert summary == {
        'n_samples': 5, 'n_features': 1, 'phenotype_counts': {'NA': 5},
        'analyses': ['AN01'], 'extra_factor_keys': ['Alpha', 'Z'],
        'excluded_samples': {}, 'duplicate_metabolites_dropped': [],
        'technical_columns_from_factors': [], 'blank_technical_columns': ['Batch', 'Injection order']}
    assert config == {
        'sample_metadata_header_row': 1, 'feature_names_row': 1, 'data_start_row': 3,
        'feature_start_column': 8, 'feature_metadata_label_column': 1, 'sheet_name': None,
        'target_column': 'Phenotype', 'sample_column': 'Samples', 'sample_type_column': 'Sample type',
        'batch_column': 'Batch', 'position_column': 'Injection order', 'qc_sample_types': []}


def test_measurement_union_including_blank_and_exclusion_precedence(tmp_path):
    fs = [factor('both', 'Drug:A'), factor('onlyA', 'Drug:A'), factor('onlyB', 'Drug:A'),
          factor('absent', 'Drug:A'), factor('no', 'Drug: '), factor('missing', 'Other:X'),
          factor('filtered', 'Drug:B'), factor('qcAbsent', 'Sample type:QC')]
    data = [feature('B', 'b', {'both': '', 'onlyB': '5'}),
            feature('A', 'a', {'onlyA': '3'}),
            feature('A', 'a2', {'both': None})]
    task = {'phenotype_key': 'Drug', 'keep': ['yes'], 'map': {'A': 'yes', 'B': 'no'},
            'control_sample_types': ['QC']}
    rows, summary, _ = run(tmp_path, fs, data, task)
    assert rows[0] == ['Samples', 'Phenotype', 'Other', 'Sample type', 'Batch', 'Injection order', 'a', 'a2', 'b']
    assert rows[1][-3:] == ['A', 'A', 'B']
    assert rows[2:] == [['both', 'yes', '', 'subject', '', '', '', '', '']]
    assert summary['excluded_samples'] == {
        'onlyA': 'not measured in B', 'onlyB': 'not measured in A', 'absent': 'not measured in A',
        'no': 'no phenotype', 'missing': 'no phenotype', 'filtered': 'phenotype not in keep: no',
        'qcAbsent': 'not measured in A'}
    assert summary['n_samples'] == 1
    assert summary['phenotype_counts'] == {'yes': 1}
    assert summary['analyses'] == ['A', 'B']


def test_controls_keep_override_and_case_insensitive_technical_keys(tmp_path):
    fs = [factor('p', 'Drug:old | sample TYPE: tissue | batch: 007 | injection ORDER: 02 | Note:one'),
          factor('q', 'Drug:excluded | SAMPLE TYPE:qC | BATCH:009 | Injection order:01'),
          factor('b', 'Sample type:Blank'), factor('pool', 'Drug: | Sample Type:pool'),
          factor('pb', 'Drug:NA | Sample type:PBQC'), factor('r', 'Drug:drop | Sample type:unknown'),
          factor('n', 'Drug:old')]
    data = [feature('AN', 'm', {r['local_sample_id']: str(i) for i, r in enumerate(fs)})]
    task = {'phenotype_key': 'Drug', 'map': {'old': 'case'}, 'keep': ['case'],
            'control_sample_types': ['QC', 'pbqc', 'POOL', 'blank']}
    rows, summary, config = run(tmp_path, fs, data, task)
    assert rows[0] == ['Samples', 'Phenotype', 'Note', 'Sample type', 'Batch', 'Injection order', 'm']
    by_id = {r[0]: r for r in rows[2:]}
    assert list(by_id) == ['b', 'n', 'p', 'pb', 'pool', 'q']
    assert by_id['p'][1:6] == ['case', 'one', 'subject', '007', '02']
    assert by_id['q'][1:6] == ['', '', 'qC', '009', '01']
    assert by_id['n'][1:6] == ['case', '', 'subject', '', '']
    for sid, st in [('b', 'Blank'), ('pb', 'PBQC'), ('pool', 'pool')]:
        assert by_id[sid][1:6] == ['', '', st, '', '']
    assert summary['phenotype_counts'] == {'case': 2}
    assert summary['excluded_samples'] == {'r': 'phenotype not in keep: drop'}
    assert summary['extra_factor_keys'] == ['Note']
    assert set(summary['technical_columns_from_factors']) == {'Sample type', 'Batch', 'Injection order'}
    assert summary['blank_technical_columns'] == []
    assert set(config['qc_sample_types']) == {'qC', 'Blank', 'PBQC', 'pool'}


@pytest.mark.parametrize('first,second', [
    ('Drug:A', 'Drug:B'),
    ('Drug:A | X:v', 'Drug:A | X:w'),
    ('Drug:A | X:v', 'Drug:A'),
    ('Drug:A | Batch:1', 'Drug:A | batch:2'),
    ('Drug:A | Injection order:1', 'Drug:A | INJECTION ORDER:2'),
    ('Drug:A | Sample type:QC', 'Drug:A | SAMPLE TYPE:blank'),
])
def test_conflicting_duplicate_records_raise_before_writing(tmp_path, first, second):
    paths = inputs(tmp_path, [factor('01 conflict', first), factor('01 conflict', second)],
                   [feature('A', 'm', {'01 conflict': '1'})])
    paths[-1].mkdir()
    with pytest.raises(Exception) as exc:
        prepare(*paths)
    assert '01 conflict' in str(exc.value)
    assert list(paths[-1].iterdir()) == []


@pytest.mark.parametrize('bad', [
    'Drug:A | Drug:B', 'Drug:A | X:1 | X:2', 'Drug:A | Batch:1 | bAtCh:2',
    'Drug:A | Injection order:1 | INJECTION ORDER:2',
    'Drug:A | Sample Type:QC | SAMPLE TYPE:blank',
])
def test_conflicts_within_one_record(tmp_path, bad):
    paths = inputs(tmp_path, [factor('sample conflict', bad)], [feature('A', 'm', {'sample conflict': '3'})])
    with pytest.raises(Exception) as exc:
        prepare(*paths)
    assert 'sample conflict' in str(exc.value)
    assert not paths[-1].exists() or not list(paths[-1].iterdir())


def test_identical_duplicates_collapse_and_repeated_equal_factors_are_valid(tmp_path):
    fs = [factor('s', 'Drug:A | Batch:01 | batch:01 | X:a:b | X:a:b'),
          factor('s', 'X:a:b | Drug:A | BATCH:01')]
    rows, summary, _ = run(tmp_path, fs, [feature('A', 'm', {'s': '7'})])
    assert rows[2:] == [['s', 'A', 'a:b', 'subject', '01', '', '7']]
    assert summary['n_samples'] == 1
    assert summary['phenotype_counts'] == {'A': 1}
    assert summary['excluded_samples'] == {}


def test_priority_dedup_anonymous_and_header_collisions(tmp_path):
    fs = [factor('s', 'Drug:A | Extra:E')]
    data = [feature('A', 'dup', {'s': 'A_drop'}),
            feature('Z', 'dup', {'s': 'z1'}),
            feature('Z', 'dup', {'s': 'z2'}),
            feature('Z', 'dup.1', {'s': 'reserved'}),
            feature('Z', 'Samples', {'s': 's1'}),
            feature('Z', 'Samples.1', {'s': 's_reserved'}),
            feature('Z', 'Phenotype', {'s': 'ph'}),
            feature('Z', 'Extra', {'s': 'ex'}),
            feature('Z', 'Batch', {'s': 'ba'}),
            feature('Z', ' ', {'s': 'anon1'}, ' '),
            feature('Z', '', {'s': 'fallback'}, 'ref'),
            feature('A', 'dup', {'s': 'A_drop2'}),
            feature('A', None, {'s': 'anon2'}, None),
            feature('A', 'new', {'s': 'new'})]
    rows, summary, config = run(tmp_path, fs, data, {'phenotype_key': 'Drug', 'analyses': ['Z', 'A']})
    assert rows[0] == ['Samples', 'Phenotype', 'Extra', 'Sample type', 'Batch', 'Injection order',
                       'dup', 'dup.2', 'dup.1', 'Samples.2', 'Samples.1', 'Phenotype.1',
                       'Extra.1', 'Batch.1', 'unnamed', 'ref', 'unnamed.1', 'new']
    assert rows[1] == ['METHOD'] + [''] * 5 + ['Z'] * 10 + ['A'] * 2
    assert rows[2] == ['s', 'A', 'E', 'subject', '', '', 'z1', 'z2', 'reserved', 's1',
                       's_reserved', 'ph', 'ex', 'ba', 'anon1', 'fallback', 'anon2', 'new']
    assert summary['analyses'] == ['Z', 'A']
    assert summary['n_features'] == 12
    assert summary['duplicate_metabolites_dropped'] == [
        {'metabolite': 'dup', 'analysis_id': 'A', 'kept_from': 'Z'},
        {'metabolite': 'dup', 'analysis_id': 'A', 'kept_from': 'Z'}]
    assert config['feature_start_column'] == 7


def test_selected_subset_ignores_unselected_measurement(tmp_path):
    fs = [factor('s', 'Drug:A'), factor('t', 'Drug:A')]
    ds = [feature('B', 'same', {'s': '2', 't': ''}), feature('A', 'same', {'s': '1'}),
          feature('C', 'unused', {})]
    rows, summary, _ = run(tmp_path, fs, ds, {'phenotype_key': 'Drug', 'analyses': ['B']})
    assert rows[1][-1] == 'B'
    assert rows[2:] == [['s', 'A', 'subject', '', '', '2'], ['t', 'A', 'subject', '', '', '']]
    assert summary['analyses'] == ['B']
    assert summary['excluded_samples'] == {}
    assert summary['duplicate_metabolites_dropped'] == []


@pytest.mark.parametrize('shape', ['list', 'mapping', 'bare'])
def test_json_record_shapes_and_refmet_fallback(tmp_path, shape):
    fs = factor('001', 'Drug:NA')
    ds = feature('01', '   ', {'001': '0002.00'}, 'ref-name')
    if shape == 'list':
        fs, ds = [fs], [ds]
    elif shape == 'mapping':
        fs, ds = {'1': fs}, {'1': ds}
    rows, summary, _ = run(tmp_path, fs, ds)
    assert rows[0][-1] == 'ref-name'
    assert rows[1][-1] == '01'
    assert rows[2:] == [['001', 'NA', 'subject', '', '', '0002.00']]
    assert summary['phenotype_counts'] == {'NA': 1}


def test_default_analysis_sort_record_order_and_csv_quoting(tmp_path):
    fs = [factor('s, "quoted"', 'Drug:case:one | Other:has,comma')]
    sid = fs[0]['local_sample_id']
    data = [feature('B', 'b', {sid: '4'}), feature('A', 'z', {sid: '1'}),
            feature('A', 'a,quoted', {sid: '2'}), feature('A', 'z', {sid: '3'})]
    rows, summary, _ = run(tmp_path, fs, data)
    assert rows[0][-4:] == ['z', 'a,quoted', 'z.1', 'b']
    assert rows[1][-4:] == ['A', 'A', 'A', 'B']
    assert rows[2] == [sid, 'case:one', 'has,comma', 'subject', '', '', '1', '2', '3', '4']
    assert summary['duplicate_metabolites_dropped'] == []


def test_all_samples_excluded_still_writes_layout(tmp_path):
    rows, summary, config = run(tmp_path, [factor('s', 'Drug:A')], [feature('A', 'm', {})])
    assert len(rows) == 2
    assert summary['n_samples'] == 0
    assert summary['n_features'] == 1
    assert summary['phenotype_counts'] == {}
    assert summary['excluded_samples'] == {'s': 'not measured in A'}
    assert config['qc_sample_types'] == []


def test_absent_phenotype_requires_review_no_output(tmp_path):
    paths = inputs(tmp_path, [factor('s', 'Treatment:A')], [feature('A', 'm', {'s': '1'})])
    with pytest.raises(Exception) as exc:
        prepare(*paths)
    assert 'Drug' in str(exc.value)
    assert not paths[-1].exists() or not list(paths[-1].iterdir())


def test_cli_success_and_conflict_failure(tmp_path):
    import prepare as module
    script = Path(module.__file__).resolve()
    paths = inputs(tmp_path / 'ok', [factor('01', 'Drug:NA')], [feature('A', 'm', {'01': '1'})])
    command = [sys.executable, str(script), '--factors', str(paths[0]), '--data', str(paths[1]),
               '--task', str(paths[2]), '--output', str(paths[3])]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (paths[3] / 'prepared.csv').is_file()
    bad = inputs(tmp_path / 'bad', [factor('cli conflict', 'Drug:A'), factor('cli conflict', 'Drug:B')],
                 [feature('A', 'm', {'cli conflict': '2'})])
    result = subprocess.run([sys.executable, str(script), '--factors', str(bad[0]), '--data', str(bad[1]),
                             '--task', str(bad[2]), '--output', str(bad[3])], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'cli conflict' in result.stderr
    assert not bad[3].exists() or not list(bad[3].iterdir())
