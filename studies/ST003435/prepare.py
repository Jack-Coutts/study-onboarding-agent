"""Convert frozen Workbench REST records to the pipeline's three-file layout."""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import yaml


TECHNICAL = ('Sample type', 'Batch', 'Injection order')
TECH_LOOKUP = {key.casefold(): key for key in TECHNICAL}


def text(value):
    return '' if value is None else str(value)


def read_records(path, identifying_key):
    with Path(path).open(encoding='utf-8') as handle:
        obj = json.load(handle)
    if isinstance(obj, list):
        records = obj
    elif isinstance(obj, dict):
        if identifying_key in obj:
            records = [obj]
        else:
            # JSON object insertion order is the REST record order.
            records = list(obj.values())
    else:
        raise ValueError(f'{path}: expected a record, list, or object of records')
    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f'{path}: records must be objects')
    return records


def parse_factors(record):
    sample = text(record.get('local_sample_id'))
    if 'local_sample_id' not in record or record['local_sample_id'] is None:
        raise ValueError('Factor record has no local_sample_id')
    result = {}
    for part in text(record.get('factors')).split('|'):
        if not part.strip():
            continue
        if ':' not in part:
            raise ValueError(f'Sample {sample!r}: malformed factor {part!r}')
        key, value = (piece.strip() for piece in part.split(':', 1))
        key = TECH_LOOKUP.get(key.casefold(), key)
        if key in result and result[key] != value:
            raise ValueError(f'Sample {sample!r}: conflicting factor {key!r}')
        result[key] = value
    return sample, result


def feature_name(record):
    for key in ('metabolite_name', 'refmet_name'):
        name = text(record.get(key))
        if name.strip():
            return name
    return 'unnamed'


def unique_headers(names):
    """Mangle duplicates while reserving all explicitly supplied names."""
    reserved = set(names)
    used = set()
    next_number = {}
    output = []
    for name in names:
        candidate = name
        if candidate in used:
            number = next_number.get(name, 1)
            candidate = f'{name}.{number}'
            while candidate in reserved or candidate in used:
                number += 1
                candidate = f'{name}.{number}'
            next_number[name] = number + 1
        used.add(candidate)
        output.append(candidate)
    return output


def prepare(factors_json: Path, data_json: Path, task_yaml: Path, output_dir: Path) -> None:
    """Write prepared.csv, summary.json, and config.yaml to output_dir."""
    factors_records = read_records(factors_json, 'local_sample_id')
    data_records = read_records(data_json, 'analysis_id')
    with Path(task_yaml).open(encoding='utf-8') as handle:
        task = yaml.safe_load(handle)
    if not isinstance(task, dict) or not task.get('phenotype_key'):
        raise ValueError('Task must specify phenotype_key')
    phenotype_key = text(task['phenotype_key'])
    phenotype_key = TECH_LOOKUP.get(phenotype_key.casefold(), phenotype_key)

    samples = {}
    factor_keys = set()
    # Validate every record, even records for samples that will be excluded.
    # No output files or directories are created until validation is complete.
    for record in factors_records:
        sample, factors = parse_factors(record)
        if sample in samples and samples[sample] != factors:
            differing = sorted(set(samples[sample]) | set(factors))
            differing = [k for k in differing if samples[sample].get(k) != factors.get(k)]
            raise ValueError(f'Sample {sample!r}: conflicting factor records ({", ".join(differing)})')
        samples[sample] = factors
        factor_keys.update(factors)
    if phenotype_key not in factor_keys:
        raise ValueError(f'Phenotype key {phenotype_key!r} is absent from factors')

    extra_keys = sorted(factor_keys - {phenotype_key} - set(TECHNICAL))
    technical_present = [key for key in TECHNICAL if key in factor_keys]
    blank_technical = [key for key in ('Batch', 'Injection order') if key not in factor_keys]

    by_analysis = {}
    for record in data_records:
        analysis = text(record.get('analysis_id'))
        if not analysis:
            raise ValueError('Data record has no analysis_id')
        values = record.get('DATA')
        if values is None:
            values = {}
        if not isinstance(values, dict):
            raise ValueError(f'Analysis {analysis!r}: DATA must be an object')
        by_analysis.setdefault(analysis, []).append((record, values))
    requested = task.get('analyses')
    if requested is None:
        analyses = sorted(by_analysis)
    else:
        if not isinstance(requested, list):
            raise ValueError('analyses must be a list')
        analyses = [text(a) for a in requested]
        if len(set(analyses)) != len(analyses):
            raise ValueError('analyses contains duplicate IDs')

    measured = {}
    features = []
    dropped = []
    first_analysis = {}
    for analysis in analyses:
        measured[analysis] = set()
        for record, values in by_analysis.get(analysis, []):
            # Membership, not nonblank intensity, defines measurement.
            # Even discarded duplicate features contribute to membership.
            measured[analysis].update(values)
            name = feature_name(record)
            if name != 'unnamed' and name in first_analysis and first_analysis[name] != analysis:
                dropped.append({'metabolite': name, 'analysis_id': analysis,
                                'kept_from': first_analysis[name]})
                continue
            if name != 'unnamed':
                first_analysis.setdefault(name, analysis)
            features.append((name, analysis, values))

    mapping = task.get('map') or {}
    mapping = {text(k): text(v) for k, v in mapping.items()}
    keep = task.get('keep')
    keep = None if keep is None else {text(label) for label in keep}
    controls = {text(value).casefold() for value in (task.get('control_sample_types') or [])}
    excluded = {}
    phenotype_counts = Counter()
    qc_types = set()
    rows = []
    for sample in sorted(samples):
        factors = samples[sample]
        sample_type = factors.get('Sample type', '')
        is_control = sample_type.casefold() in controls
        phenotype = ''
        reason = None
        if not is_control:
            original = factors.get(phenotype_key, '')
            if not original:
                reason = 'no phenotype'
            else:
                phenotype = mapping.get(original, original)
                if keep is not None and phenotype not in keep:
                    reason = f'phenotype not in keep: {phenotype}'
        if reason is None:
            for analysis in analyses:
                if sample not in measured[analysis]:
                    reason = f'not measured in {analysis}'
                    break
        if reason is not None:
            excluded[sample] = reason
            continue
        if is_control:
            qc_types.add(sample_type)
        else:
            phenotype_counts[phenotype] += 1
        row = [sample, phenotype] + [factors.get(key, '') for key in extra_keys]
        row += [sample_type if is_control else 'subject',
                factors.get('Batch', ''), factors.get('Injection order', '')]
        for _, _, values in features:
            value = text(values.get(sample))
            row.append(value if value.strip() else '')
        rows.append(row)

    metadata = ['Samples', 'Phenotype'] + extra_keys + list(TECHNICAL)
    headers = unique_headers(metadata + [name for name, _, _ in features])
    method_row = ['METHOD'] + [''] * (len(metadata) - 1) + [a for _, a, _ in features]
    summary = {
        'n_samples': len(rows),
        'n_features': len(features),
        'phenotype_counts': dict(phenotype_counts),
        'analyses': analyses,
        'extra_factor_keys': extra_keys,
        'excluded_samples': excluded,
        'duplicate_metabolites_dropped': dropped,
        'technical_columns_from_factors': technical_present,
        'blank_technical_columns': blank_technical,
    }
    config = {
        'sample_metadata_header_row': 1,
        'feature_names_row': 1,
        'data_start_row': 3,
        'feature_start_column': len(metadata) + 1,
        'feature_metadata_label_column': 1,
        'sheet_name': None,
        'target_column': 'Phenotype',
        'sample_column': 'Samples',
        'sample_type_column': 'Sample type',
        'batch_column': 'Batch',
        'position_column': 'Injection order',
        'qc_sample_types': sorted(qc_types),
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Never follow an existing output symlink when writing the regular files.
    for name in ('prepared.csv', 'summary.json', 'config.yaml'):
        destination = output_dir / name
        if destination.is_symlink():
            destination.unlink()
        if destination.is_dir():
            raise ValueError(f'Output destination is a directory: {destination}')
    with (output_dir / 'prepared.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerow(method_row)
        writer.writerows(rows)
    with (output_dir / 'summary.json').open('w', encoding='utf-8') as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    with (output_dir / 'config.yaml').open('w', encoding='utf-8') as handle:
        yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)


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
