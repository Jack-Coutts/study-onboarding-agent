"""Convert a Workbench REST deposit to the fixed pipeline layout."""
import argparse
import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

TECHNICAL = ('Sample type', 'Batch', 'Injection order')
TECH_KEYS = {key.casefold(): key for key in TECHNICAL}


def text(value):
    return '' if value is None else str(value)


def records(path, marker):
    with Path(path).open(encoding='utf-8') as stream:
        obj = json.load(stream)
    if isinstance(obj, list):
        result = obj
    elif isinstance(obj, dict):
        result = [obj] if marker in obj else list(obj.values())
    else:
        raise ValueError('Expected records in ' + str(path))
    if not all(isinstance(rec, dict) for rec in result):
        raise ValueError('Expected record objects in ' + str(path))
    return result


def parse_factors(raw, sample):
    result = {}
    for item in text(raw).split('|'):
        if not item.strip():
            continue
        if ':' not in item:
            raise ValueError('Invalid factor for sample ' + sample + ': ' + item)
        key, value = item.split(':', 1)
        key, value = key.strip(), value.strip()
        key = TECH_KEYS.get(key.casefold(), key)
        if key in result and result[key] != value:
            raise ValueError('Conflicting factor ' + key + ' for sample ' + sample)
        result[key] = value
    return result


def unique_headers(names):
    # Reserve every literal header before allocating duplicate suffixes.
    reserved = set(names)
    used = set()
    counts = {}
    answer = []
    for name in names:
        if name not in used:
            candidate = name
        else:
            number = counts.get(name, 0) + 1
            candidate = name + '.' + str(number)
            while candidate in reserved or candidate in used:
                number += 1
                candidate = name + '.' + str(number)
            counts[name] = number
        used.add(candidate)
        answer.append(candidate)
    return answer


def feature_name(rec):
    for key in ('metabolite_name', 'refmet_name'):
        name = text(rec.get(key))
        if name.strip():
            return name, False
    return 'unnamed', True


def prepare(factors_json: Path, data_json: Path, task_yaml: Path, output_dir: Path) -> None:
    """Write prepared.csv, summary.json, and config.yaml to output_dir."""
    with Path(task_yaml).open(encoding='utf-8') as stream:
        task = yaml.safe_load(stream)
    if not isinstance(task, dict) or not task.get('phenotype_key'):
        raise ValueError('Task must specify phenotype_key')
    phenotype_key = text(task['phenotype_key'])
    phenotype_key = TECH_KEYS.get(phenotype_key.casefold(), phenotype_key)
    samples = {}
    all_keys = set()
    for rec in records(factors_json, 'local_sample_id'):
        if 'local_sample_id' not in rec:
            raise ValueError('Missing local_sample_id in factor record')
        sample = text(rec['local_sample_id'])
        factors = parse_factors(rec.get('factors'), sample)
        if sample in samples and samples[sample] != factors:
            raise ValueError('Conflicting factor records for sample ' + sample)
        samples[sample] = factors
        all_keys.update(factors)
    if phenotype_key not in all_keys:
        raise ValueError('Phenotype factor is absent: ' + phenotype_key)
    extra = sorted(all_keys - {phenotype_key} - set(TECHNICAL))
    groups = {}
    measured = {}
    for rec in records(data_json, 'analysis_id'):
        if 'analysis_id' not in rec:
            raise ValueError('Missing analysis_id in data record')
        analysis = text(rec['analysis_id'])
        values = rec.get('DATA')
        if values is None:
            values = {}
        if not isinstance(values, dict):
            raise ValueError('DATA must be a mapping for analysis ' + analysis)
        values = {text(key): text(value) for key, value in values.items()}
        name, anonymous = feature_name(rec)
        groups.setdefault(analysis, []).append((name, anonymous, values))
        measured.setdefault(analysis, set()).update(values)
    if task.get('analyses') is None:
        analyses = sorted(groups)
    else:
        analyses = [text(a) for a in task['analyses']]
        if len(set(analyses)) != len(analyses):
            raise ValueError('Repeated selected analysis ID')
        for analysis in analyses:
            if analysis not in groups:
                raise ValueError('Selected analysis is absent: ' + analysis)
    features = []
    first_analysis = {}
    dropped = []
    for analysis in analyses:
        for name, anonymous, values in groups[analysis]:
            if not anonymous:
                if name in first_analysis and first_analysis[name] != analysis:
                    dropped.append({'metabolite': name, 'analysis_id': analysis,
                                    'kept_from': first_analysis[name]})
                    continue
                first_analysis.setdefault(name, analysis)
            features.append((name, analysis, values))
    controls = {text(value).casefold() for value in task.get('control_sample_types', []) or []}
    mapping = {text(k): text(v) for k, v in (task.get('map') or {}).items()}
    keep = None if task.get('keep') is None else {text(v) for v in task['keep']}
    excluded = {}
    kept = []
    phenotype_counts = Counter()
    qc_types = set()
    for sample in sorted(samples):
        factors = samples[sample]
        sample_type = factors.get('Sample type', '')
        is_control = sample_type.casefold() in controls
        phenotype = ''
        if not is_control:
            raw = factors.get(phenotype_key, '')
            if not raw:
                excluded[sample] = 'no phenotype'
                continue
            phenotype = mapping.get(raw, raw)
            if keep is not None and phenotype not in keep:
                excluded[sample] = 'phenotype not in keep: ' + phenotype
                continue
        missing = next((a for a in analyses if sample not in measured[a]), None)
        if missing is not None:
            excluded[sample] = 'not measured in ' + missing
            continue
        if is_control:
            qc_types.add(sample_type)
        else:
            phenotype_counts[phenotype] += 1
        kept.append([sample, phenotype] + [factors.get(key, '') for key in extra] +
                    [sample_type if is_control else 'subject', factors.get('Batch', ''),
                     factors.get('Injection order', '')] +
                    [values.get(sample, '') for _, _, values in features])
    metadata = ['Samples', 'Phenotype'] + extra + list(TECHNICAL)
    header = unique_headers(metadata + [name for name, _, _ in features])
    csv_buffer = io.StringIO(newline='')
    writer = csv.writer(csv_buffer, lineterminator='\n')
    writer.writerow(header)
    writer.writerow(['METHOD'] + [''] * (len(metadata) - 1) + [a for _, a, _ in features])
    writer.writerows(kept)
    summary = {
        'n_samples': len(kept), 'n_features': len(features),
        'phenotype_counts': dict(phenotype_counts), 'analyses': analyses,
        'extra_factor_keys': extra, 'excluded_samples': excluded,
        'duplicate_metabolites_dropped': dropped,
        'technical_columns_from_factors': [key for key in TECHNICAL if key in all_keys],
        'blank_technical_columns': [key for key in TECHNICAL[1:] if key not in all_keys],
    }
    config = {
        'sample_metadata_header_row': 1, 'feature_names_row': 1, 'data_start_row': 3,
        'feature_start_column': len(metadata) + 1, 'feature_metadata_label_column': 1,
        'sheet_name': None, 'target_column': 'Phenotype', 'sample_column': 'Samples',
        'sample_type_column': 'Sample type', 'batch_column': 'Batch',
        'position_column': 'Injection order', 'qc_sample_types': sorted(qc_types),
    }
    # Do not create or touch outputs until every validation and computation succeeds.
    contents = {'prepared.csv': csv_buffer.getvalue(),
                'summary.json': json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                'config.yaml': yaml.safe_dump(config, sort_keys=False, allow_unicode=True)}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for filename, content in contents.items():
        path = output / filename
        # Avoid following an existing link, and ensure the result is a regular file.
        if path.is_symlink():
            path.unlink()
        path.write_text(content, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--factors', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.factors, args.data, args.task, args.output)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
