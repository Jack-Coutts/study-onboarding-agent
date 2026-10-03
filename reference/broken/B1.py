"""B1: sample IDs read as numbers, so 01 becomes 1."""

MISTAKE = "Sample IDs read as numbers, so `01` becomes `1`"
REPLACEMENTS = [
    (
        '    return "" if value is None else str(value)\n\n\ndef _value',
        '    text = "" if value is None else str(value)\n'
        "    return str(int(text)) if text.isdigit() else text\n\n\ndef _value",
    )
]
