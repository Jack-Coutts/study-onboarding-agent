"""Convert frozen Metabolomics Workbench REST records into pipeline inputs."""
import argparse
import csv
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

import yaml

TECHNICAL = ('Sample type', 'Batch', 'Injection order')
CANONICAL = {key.casefold(): key for key in TECHNICAL}


def text(value):
    return '' if value is None else str(value)


def records(path, identifying_key):
    with Path(path).open(encoding='utf-8') as handle:
        raw = json.load(handle)
    if isinstance(raw, list):
        result = raw
    elif isinstance(raw, dict):
        result = [raw] if identifying_key in raw else list(raw.values())
    else:
        raise ValueError('Expected a JSON record, list, or record mapping')
    if any(not isinstance(item, dict) for item in result):
        raise ValueError('Expected JSON records')
    return result


def parse_factors(record):
    sample = text(record['local_sample_id'])
    result = {}
    for segment in text(record.get('factors')).split('|'):
        if not segment.strip():
            continue
        if ':' not in segment:
            raise ValueError('Malformed factor for sample ' + sample)
        key, value = (part.strip() for part in segment.split(':', 1))
        key = CANONICAL.get(key.casefold(), key)
        if key in result and result[key] != value:
            raise ValueError('Conflicting factor ' + key + ' for sample ' + sample)
        result[key] = value
    return sample, result


def unique_headers(names):
    # Reserve original names too, so e.g. x, x, x.1 becomes x, x.2, x.1.
    reserved = set(names)
    used = set()
    counts = {}
    result = []
    for name in names:
        candidate = name
        if candidate in used:
            number = counts.get(name, 0) + 1
            candidate = name + '.' + str(number)
            while candidate in reserved or candidate in used:
                number += 1
                candidate = name + '.' + str(number)
            counts[name] = number
        used.add(candidate)
        result.append(candidate)
    return result


def prepare(factors_json: Path, data_json: Path, task_yaml: Path, output_dir: Path) -> None:
    """Write prepared.csv, summary.json, and config.yaml to output_dir."""
    with Path(task_yaml).open(encoding='utf-8') as handle:
        task = yaml.safe_load(handle)
    phenotype_key = text(task['phenotype_key'])
    samples = {}
    keys = set()
    for record in records(factors_json, 'local_sample_id'):
        sample, factors = parse_factors(record)
        if sample in samples and samples[sample] != factors:
            raise ValueError('Conflicting factor records for sample ' + sample)
        samples[sample] = factors
        keys.update(factors)
    if phenotype_key not in keys:
        raise ValueError('Phenotype key absent from factors: ' + phenotype_key)
    extra_keys = sorted(keys - set(TECHNICAL) - {phenotype_key})
    data = records(data_json, 'analysis_id')
    if task.get('analyses') is None:
        analyses = sorted({text(r['analysis_id']) for r in data})
    else:
        analyses = [text(a) for a in task['analyses']]
    grouped = {a: [] for a in analyses}
    measured = {a: set() for a in analyses}
    for record in data:
        analysis = text(record['analysis_id'])
        if analysis in grouped:
            values = record.get('DATA') or {}
            if not isinstance(values, dict):
                raise ValueError('DATA must be a sample-to-value mapping')
            grouped[analysis].append(record)
            measured[analysis].update(values)
    features = []
    owners = {}
    dropped = []
    for analysis in analyses:
        for record in grouped[analysis]:
            name = next((text(record.get(k)) for k in ('metabolite_name', 'refmet_name')
                         if text(record.get(k)).strip()), 'unnamed')
            if name != 'unnamed' and name in owners and owners[name] != analysis:
                dropped.append({'metabolite': name, 'analysis_id': analysis,
                                'kept_from': owners[name]})
                continue
            if name != 'unnamed':
                owners.setdefault(name, analysis)
            features.append((name, analysis, record.get('DATA') or {}))
    control_types = {text(v).casefold() for v in task.get('control_sample_types', [])}
    rename = {text(k): text(v) for k, v in (task.get('map') or {}).items()}
    keep = None if task.get('keep') is None else {text(v) for v in task['keep']}
    excluded = {}
    rows = []
    counts = Counter()
    qc_values = set()
    for sample in sorted(samples):
        factors = samples[sample]
        sample_type = factors.get('Sample type', '')
        control = sample_type.casefold() in control_types
        phenotype = '' if control else factors.get(phenotype_key, '')
        if not control and not phenotype:
            excluded[sample] = 'no phenotype'
            continue
        if not control:
            phenotype = rename.get(phenotype, phenotype)
            if keep is not None and phenotype not in keep:
                excluded[sample] = 'phenotype not in keep: ' + phenotype
                continue
        missing = next((a for a in analyses if sample not in measured[a]), None)
        if missing is not None:
            excluded[sample] = 'not measured in ' + missing
            continue
        if control:
            qc_values.add(sample_type)
        else:
            counts[phenotype] += 1
        rows.append([sample, phenotype] + [factors.get(k, '') for k in extra_keys] +
                    [sample_type if control else 'subject', factors.get('Batch', ''),
                     factors.get('Injection order', '')] +
                    [text(values.get(sample)) for _, _, values in features])
    metadata = ['Samples', 'Phenotype'] + extra_keys + list(TECHNICAL)
    header = unique_headers(metadata + [f[0] for f in features])
    method = ['METHOD'] + [''] * (len(metadata) - 1) + [f[1] for f in features]
    summary = {
        'n_samples': len(rows), 'n_features': len(features),
        'phenotype_counts': dict(counts), 'analyses': analyses,
        'extra_factor_keys': extra_keys, 'excluded_samples': excluded,
        'duplicate_metabolites_dropped': dropped,
        'technical_columns_from_factors': [k for k in TECHNICAL if k in keys],
        'blank_technical_columns': [k for k in ('Batch', 'Injection order') if k not in keys],
    }
    config = {
        'sample_metadata_header_row': 1, 'feature_names_row': 1,
        'data_start_row': 3, 'feature_start_column': len(metadata) + 1,
        'feature_metadata_label_column': 1, 'sheet_name': None,
        'target_column': 'Phenotype', 'sample_column': 'Samples',
        'sample_type_column': 'Sample type', 'batch_column': 'Batch',
        'position_column': 'Injection order', 'qc_sample_types': sorted(qc_values),
    }
    # No filesystem output until all validation and preparation have succeeded.
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in ('prepared.csv', 'summary.json', 'config.yaml'):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                             dir=output_dir, delete=False) as handle:
                temporary = handle.name
                if filename == 'prepared.csv':
                    writer = csv.writer(handle)
                    writer.writerow(header)
                    writer.writerow(method)
                    writer.writerows(rows)
                elif filename == 'summary.json':
                    json.dump(summary, handle, ensure_ascii=False, indent=2)
                    handle.write('\n')
                else:
                    yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)
            os.replace(temporary, output_dir / filename)
            temporary = None
        finally:
            if temporary is not None:
                os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--factors', required=True, type=Path)
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--task', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.factors, args.data, args.task, args.output)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
