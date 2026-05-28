def count_decimal_places(x) -> int:
    s = str(x)
    if "." in s:
        decimals = len(s.split(".")[1])
        return decimals
    return 0
