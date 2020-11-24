from zyaml.scanner import *


__version__ = "0.1.2"


def load_string(contents):
    """
    Args:
        contents (str): Yaml to deserialize (can be a callable that yields one line at a time)

    Returns:
        (list | dict): Deserialized object
    """
    scanner = Scanner(contents)
    return scanner.deserialized()


def load_path(path):
    """
    Args:
        path (str): Path to file to deserialize

    Returns:
        (list | dict): Deserialized object
    """
    with open(path) as fh:
        scanner = Scanner(fh)
        return scanner.deserialized()
