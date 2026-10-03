"""B6: a literal NA label is read as missing."""

MISTAKE = "A literal `NA` label is read as missing"
REPLACEMENTS = [
    (
        '        raw_phenotype = sample_factors.get(task.phenotype_key, "")\n',
        '        raw_phenotype = sample_factors.get(task.phenotype_key, "")\n'
        '        if raw_phenotype in {"NA", "N/A", "NaN", "nan", "null"}:\n'
        '            raw_phenotype = ""\n',
    )
]
