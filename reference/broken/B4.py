"""B4: conflicting duplicate factor records resolved by keeping the first."""

MISTAKE = "Conflicting duplicate factor records resolved by keeping the first"
REPLACEMENTS = [
    (
        "            if samples[sample_id] != factors:\n",
        "            if False:  # keeps the first record\n",
    )
]
