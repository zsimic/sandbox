from zyaml.scanner import *


__version__ = "0.1.1"


def load(stream):
    """
    :param str|file stream: Stream or contents to load
    """
    scanner = Scanner(stream)
    return scanner.deserialized()


def load_string(contents):
    """
    :param str contents: Yaml to deserialize
    """
    scanner = Scanner(contents)
    return scanner.deserialized()


def load_path(path):
    """
    :param str path: Path to file to deserialize
    """
    with open(path) as fh:
        return load_string(fh.read())
