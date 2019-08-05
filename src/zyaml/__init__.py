from zyaml.scan import BlockEntryToken, ParserStack, ScalarToken, scan_tokens


def load(stream):
    if hasattr(stream, "read"):
        stream = stream.read()
    return load_string(stream)


def load_string(contents):
    """
    :param str contents: Yaml to deserialize
    """
    stack = ParserStack()
    for token in scan_tokens(contents):
        stack.process(token)
    return stack.root


def load_path(path):
    with open(path) as fh:
        return load_string(fh.read())
