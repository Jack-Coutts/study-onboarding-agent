"""B3: Batch and Injection order filled in when the deposit has no such factor."""

MISTAKE = "`Batch` and `Injection order` filled in when the deposit has no such factor"
REPLACEMENTS = [
    (
        '    return values.pop() if values else ""',
        '    return values.pop() if values else ("" if keys else "1")',
    )
]
