"""B2: a sample missing from one analysis is kept with blank values."""

MISTAKE = "A sample missing from one analysis is kept with blank values"
REPLACEMENTS = [
    (
        "        missing = [analysis for analysis in analyses"
        " if sample_id not in measured[analysis]]",
        "        missing: list[str] = []",
    )
]
