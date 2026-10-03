"""B8: a repeated metabolite name is numbered onto a name that already exists."""

MISTAKE = "A repeated metabolite name is numbered onto a name that already exists"
REPLACEMENTS = [
    (
        "            count = count + 1 if column in names else counts.get(column, 0)\n",
        "            break\n",
    )
]
