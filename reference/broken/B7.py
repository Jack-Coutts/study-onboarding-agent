"""B7: a metabolite measured in two analyses is written twice."""

MISTAKE = "A metabolite measured in two analyses is written twice"
REPLACEMENTS = [
    (
        "            if name != UNNAMED and owner.setdefault(name, analysis) != analysis:\n",
        "            if False:  # never drops a metabolite repeated across analyses\n",
    )
]
