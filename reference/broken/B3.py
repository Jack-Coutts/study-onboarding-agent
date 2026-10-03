"""B3: Batch and Injection order filled in when the deposit has no such factor."""

MISTAKE = "`Batch` and `Injection order` filled in when the deposit has no such factor"
REPLACEMENTS = [
    (
        '    return factors.get(key, "") if key is not None else ""',
        '    return factors.get(key, "") if key is not None else "1"',
    )
]
