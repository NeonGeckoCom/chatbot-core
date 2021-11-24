def remove_prefix(prefixed_string: str, prefix: str):
    """
    Removes the specified prefix from the string
    :param prefixed_string: raw string to clean
    :param prefix: prefix to remove
    :return: string with prefix removed
    """
    if prefixed_string.startswith(prefix):
        return prefixed_string[len(prefix):]
    return prefixed_string
