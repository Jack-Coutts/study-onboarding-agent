import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
import sys
import yaml


TECHNICAL = ('Sample type', 'Batch', 'Injection order')
CANONICAL = {key.casefold(): key for key in TECHNICAL}


def text(value):
    return '' if value is None else str(value)


def records(path, identifying_key):
    with Path(path).open(encoding='utf-8') as handle:
        obj = json.load(handle)
    if isinstance(obj, list):
        result = obj
    elif isinstance(obj, dict):
        result = [obj] if identifying_key in obj else list(obj.values())
    else:
        raise ValueError('Expected a JSON record, record list, or record mapping')
    if any(not isinstance(record, dict) for record in result):
        raise ValueError('Invalid JSON record')
    return result


def parse_factors(record, sample):
    parsed = {}
    for item in text(record.get('factors')).split('|'):
        if ':' not in item:
            continue
        key, value = item.split(':', 1)
        key, value = key.strip(), value.strip()
        key = CANONICAL.get(key.casefold(), key)
        if key in parsed and parsed[key] != value:
            raise ValueError('Conflicting factors for sample ' + repr(sample) + ': ' + key)
        parsed[key] = value
    return parsed


def number_headers(names):
    # Reserve all original names before numbering, including names appearing later.
    reserved = set(names)
    emitted = set()
    numbered = []
    next_number = {}
    for name in names:
        if name not in emitted:
            candidate = name
        else:
            number = next_number.get(name, 1)
            candidate = name + '.' + str(number)
            while candidate in reserved or candidate in emitted:
                number += 1
                candidate = name + '.' + str(number)
            next_number[name] = number + 1
        emitted.add(candidate)
        numbered.append(candidate)
    return numbered


def prepare(factors_json: Path, data_json: Path, task_yaml: Path, output_dir: Path) -> None:
    """Write prepared.csv, summary.json, and config.yaml to output_dir."""
    with Path(task_yaml).open(encoding='utf-8') as handle:
        task = yaml.safe_load(handle)
    phenotype_key = text(task['phenotype_key'])
    phenotype_key = CANONICAL.get(phenotype_key.casefold(), phenotype_key)
    samples = {}
    factor_keys = set()
    for record in records(factors_json, 'local_sample_id'):
        sample = text(record['local_sample_id'])
        factors = parse_factors(record, sample)
        if sample in samples and samples[sample] != factors:
            raise ValueError('Conflicting factors for sample ' + repr(sample))
        samples[sample] = factors
        factor_keys.update(factors)
    if phenotype_key not in factor_keys:
        raise ValueError('Phenotype factor is absent: ' + phenotype_key)
    extra_keys = sorted(factor_keys - set(TECHNICAL) - {phenotype_key})
    technical_present = [key for key in TECHNICAL if key in factor_keys]
    technical_blank = [key for key in TECHNICAL[1:] if key not in factor_keys]

    by_analysis = {}
    for record in records(data_json, 'analysis_id'):
        analysis = text(record['analysis_id'])
        by_analysis.setdefault(analysis, []).append(record)
    analyses = ([text(a) for a in task['analyses']] if 'analyses' in task
                else sorted(by_analysis))
    measured = {}
    features = []
    first_analysis = {}
    dropped = []
    for analysis in analyses:
        measured[analysis] = set()
        for record in by_analysis.get(analysis, []):
            values = record.get('DATA') or {}
            if not isinstance(values, dict):
                raise ValueError('DATA must be a mapping for analysis ' + analysis)
            measured[analysis].update(values)
            name = text(record.get('metabolite_name'))
            if not name.strip():
                name = text(record.get('refmet_name'))
            named = bool(name.strip())
            if not named:
                name = 'unnamed'
            if named and name in first_analysis and first_analysis[name] != analysis:
                dropped.append({'metabolite': name, 'analysis_id': analysis,
                                'kept_from': first_analysis[name]})
                continue
            if named:
                first_analysis.setdefault(name, analysis)
            features.append((name, analysis, values))

    mapping = {text(k): text(v) for k, v in (task.get('map') or {}).items()}
    keep = {text(v) for v in task['keep']} if 'keep' in task else None
    control_types = {text(v).casefold() for v in task.get('control_sample_types', [])}
    exclusions = {}
    rows = []
    phenotype_counts = Counter()
    qc_types = set()
    for sample in sorted(samples):
        factors = samples[sample]
        sample_type = factors.get('Sample type', '')
        control = sample_type.casefold() in control_types
        phenotype = factors.get(phenotype_key, '')
        reason = None
        if control:
            phenotype = ''
        elif not phenotype:
            reason = 'no phenotype'
        else:
            phenotype = mapping.get(phenotype, phenotype)
            if keep is not None and phenotype not in keep:
                reason = 'phenotype not in keep: ' + phenotype
        if reason is None:
            for analysis in analyses:
                if sample not in measured[analysis]:
                    reason = 'not measured in ' + analysis
                    break
        if reason is not None:
            exclusions[sample] = reason
            continue
        if control:
            qc_types.add(sample_type)
        else:
            sample_type = 'subject'
            phenotype_counts[phenotype] += 1
        rows.append([sample, phenotype] + [factors.get(key, '') for key in extra_keys]
                    + [sample_type, factors.get('Batch', ''), factors.get('Injection order', '')]
                    + [text(values.get(sample, '')) for _, _, values in features])

    metadata = ['Samples', 'Phenotype'] + extra_keys + list(TECHNICAL)
    header = number_headers(metadata + [name for name, _, _ in features])
    csv_buffer = io.StringIO(newline='')
    writer = csv.writer(csv_buffer)
    writer.writerow(header)
    writer.writerow(['METHOD'] + [''] * (len(metadata) - 1)
                    + [analysis for _, analysis, _ in features])
    writer.writerows(rows)
    summary = {
        'n_samples': len(rows),
        'n_features': len(features),
        'phenotype_counts': dict(phenotype_counts),
        'analyses': analyses,
        'extra_factor_keys': extra_keys,
        'excluded_samples': exclusions,
        'duplicate_metabolites_dropped': dropped,
        'technical_columns_from_factors': technical_present,
        'blank_technical_columns': technical_blank,
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
    # Complete all validation and serialization before writing any output.
    contents = {
        'prepared.csv': csv_buffer.getvalue(),
        'summary.json': json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
        'config.yaml': yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in contents.items():
        with (output_dir / filename).open('w', encoding='utf-8', newline='') as handle:
            handle.write(content)


def main():
    parser = argparse.ArgumentParser(description='Prepare Workbench metabolomics data')
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
