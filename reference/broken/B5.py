"""B5: QC and blank samples without a phenotype are dropped."""

MISTAKE = "QC and blank samples without a phenotype are dropped"
REPLACEMENTS = [
    (
        '        if is_control:\n            phenotype = ""\n',
        '        if is_control and raw_phenotype:\n            phenotype = ""\n',
    )
]
