from zyaml.scanner import *


def load(stream, simplified=True):
    """
    :param str|file stream: Stream or contents to load
    :param bool simplified: If True, return document itself when there was only one document (instead of list with 1 item)
    """
    scanner = Scanner(stream)
    return scanner.deserialized(simplified=simplified)


def load_string(contents, simplified=True):
    """
    :param str contents: Yaml to deserialize
    :param bool simplified: If True, return document itself when there was only one document (instead of list with 1 item)
    """
    scanner = Scanner(contents)
    return scanner.deserialized(simplified=simplified)


def load_path(path, simplified=True):
    """
    :param str path: Path to file to deserialize
    :param bool simplified: If True, return document itself when there was only one document (instead of list with 1 item)
    """
    with open(path) as fh:
        return load_string(fh.read(), simplified=simplified)
