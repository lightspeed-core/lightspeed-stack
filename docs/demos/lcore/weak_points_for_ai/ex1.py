# hasattr + getattr - better data model needed?

    for key, value in entry.items():
        if not hasattr(tool, key):
            return False
        attr = getattr(tool, key)
        if attr is None:
            return False
        if attr != value and str(attr) != value:
            return False
    return True
