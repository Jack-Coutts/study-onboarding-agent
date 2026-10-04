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
TECH_CANON = {name.lower(): name for name in TECHNICAL}


def text(value):
    return '' if value is None else str(value)


def records(path, marker):
    with Path(path).open(encoding='utf-8') as handle:
        obj = json.load(handle)
    if isinstance(obj, list):
        result = obj
    elif isinstance(obj, dict):
        result = [obj] if marker in obj else list(obj.values())
    else:
        raise ValueError('Expected records in ' + str(path))
    if not all(isinstance(record, dict) for record in result):
        raise ValueError('Expected record objects in ' + str(path))
    return result


def parse_factors(record):
    sample = text(record['local_sample_id'])
    parsed = {}
    for part in text(record.get('factors')).split('|'):
        if not part.strip():
            continue
        if ':' not in part:
            raise ValueError('Malformed factor for sample ' + sample + ': ' + part)
        key, value = part.split(':', 1)
        key, value = key.strip(), value.strip()
        key = TECH_CANON.get(key.lower(), key)
        if key in parsed and parsed[key] != value:
            raise ValueError('Conflicting factor ' + key + ' for sample ' + sample)
        parsed[key] = value
    return sample, parsed


def unique_headers(names):
    # Reserve all original names, including names ending in .1, .2, etc.
    reserved = set(names)
    used = set()
    counts = {}
    result = []
    for name in names:
        if name not in used:
            output = name
        else:
            number = counts.get(name, 0) + 1
            output = name + '.' + str(number)
            while output in reserved or output in used:
                number += 1
                output = name + '.' + str(number)
            counts[name] = number
        used.add(output)
        result.append(output)
    return result


def prepare(factors_json: Path, data_json: Path, task_yaml: Path, output_dir: Path) -> None:
    """Write prepared.csv, summary.json, and config.yaml to output_dir."""
    factors_records = records(factors_json, 'local_sample_id')
    data_records = records(data_json, 'analysis_id')
    with Path(task_yaml).open(encoding='utf-8') as handle:
        task = yaml.safe_load(handle)
    if not isinstance(task, dict) or not task.get('phenotype_key'):
        raise ValueError('Task must specify phenotype_key')
    phenotype_key = text(task['phenotype_key'])
    phenotype_key = TECH_CANON.get(phenotype_key.lower(), phenotype_key)
    samples = {}
    keys = set()
    for record in factors_records:
        sample, factors = parse_factors(record)
        if sample in samples and samples[sample] != factors:
            raise ValueError('Conflicting factor records for sample ' + sample)
        samples[sample] = factors
        keys.update(factors)
    if phenotype_key not in keys:
        raise ValueError('Phenotype factor is absent: ' + phenotype_key)
    extra_keys = sorted(keys - {phenotype_key} - set(TECHNICAL))
    technical_from = [name for name in TECHNICAL if name in keys]
    blank_technical = [name for name in TECHNICAL[1:] if name not in keys]
    by_analysis = {}
    measured = {}
    for record in data_records:
        analysis = text(record['analysis_id'])
        values = record.get('DATA', {})
        if not isinstance(values, dict):
            raise ValueError('DATA must be a sample mapping in analysis ' + analysis)
        by_analysis.setdefault(analysis, []).append(record)
        measured.setdefault(analysis, set()).update(values.keys())
    if task.get('analyses') is None:
        analyses = sorted(by_analysis)
    else:
        analyses = [text(value) for value in task['analyses']]
        if len(set(analyses)) != len(analyses):
            raise ValueError('Repeated selected analysis IDs')
        for analysis in analyses:
            if analysis not in by_analysis:
                raise ValueError('Selected analysis is absent: ' + analysis)

    features = []
    dropped = []
    first_analysis = {}
    for analysis in analyses:
        for record in by_analysis[analysis]:
            name = text(record.get('metabolite_name'))
            if not name.strip():
                name = text(record.get('refmet_name'))
            if not name.strip():
                name = 'unnamed'
            if name != 'unnamed':
                if name in first_analysis and first_analysis[name] != analysis:
                    dropped.append({'metabolite': name, 'analysis_id': analysis,
                                    'kept_from': first_analysis[name]})
                    continue
                first_analysis.setdefault(name, analysis)
            features.append((name, analysis, record.get('DATA', {})))

    rename = {text(key): text(value) for key, value in (task.get('map') or {}).items()}
    keep = None if task.get('keep') is None else {text(value) for value in task['keep']}
    control_types = {text(value).lower() for value in (task.get('control_sample_types') or [])}
    rows = []
    excluded = {}
    phenotype_counts = Counter()
    qc_types = set()
    for sample in sorted(samples):
        factors = samples[sample]
        sample_type = factors.get('Sample type', '')
        is_control = sample_type.lower() in control_types
        raw_phenotype = factors.get(phenotype_key, '')
        phenotype = '' if is_control else rename.get(raw_phenotype, raw_phenotype)
        reason = None
        if not is_control and not raw_phenotype:
            reason = 'no phenotype'
        elif not is_control and keep is not None and phenotype not in keep:
            reason = 'phenotype not in keep: ' + phenotype
        else:
            for analysis in analyses:
                if sample not in measured.get(analysis, set()):
                    reason = 'not measured in ' + analysis
                    break
        if reason is not None:
            excluded[sample] = reason
            continue
        if is_control:
            qc_types.add(sample_type)
        else:
            phenotype_counts[phenotype] += 1
        rows.append([sample, phenotype] + [factors.get(key, '') for key in extra_keys]
                    + [sample_type if is_control else 'subject', factors.get('Batch', ''),
                       factors.get('Injection order', '')]
                    + [text(values.get(sample, '')) for _, _, values in features])

    metadata = ['Samples', 'Phenotype'] + extra_keys + list(TECHNICAL)
    header = unique_headers(metadata + [feature[0] for feature in features])
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(header)
    writer.writerow(['METHOD'] + [''] * (len(metadata) - 1)
                    + [feature[1] for feature in features])
    writer.writerows(rows)
    summary = {
        'n_samples': len(rows), 'n_features': len(features),
        'phenotype_counts': dict(phenotype_counts), 'analyses': analyses,
        'extra_factor_keys': extra_keys, 'excluded_samples': excluded,
        'duplicate_metabolites_dropped': dropped,
        'technical_columns_from_factors': technical_from,
        'blank_technical_columns': blank_technical,
    }
    config = {
        'sample_metadata_header_row': 1, 'feature_names_row': 1, 'data_start_row': 3,
        'feature_start_column': len(metadata) + 1, 'feature_metadata_label_column': 1,
        'sheet_name': None, 'target_column': 'Phenotype', 'sample_column': 'Samples',
        'sample_type_column': 'Sample type', 'batch_column': 'Batch',
        'position_column': 'Injection order', 'qc_sample_types': sorted(qc_types),
    }
    contents = {'prepared.csv': stream.getvalue(),
                'summary.json': json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                'config.yaml': yaml.safe_dump(config, sort_keys=False, allow_unicode=True)}
    output = Path(output_dir)
    # All input validation and serialization precede the first output write.
    for filename in contents:
        destination = output / filename
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError('Output is not a regular file: ' + str(destination))
    output.mkdir(parents=True, exist_ok=True)
    for filename, content in contents.items():
        with (output / filename).open('w', encoding='utf-8', newline='') as handle:
            handle.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--factors', required=True, type=Path)
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--task', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.factors, args.data, args.task, args.output)
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
