from zyaml.scanner import *


__version__ = "0.1.2"


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


def load_stream(stream):
    """
    Args:
        stream (collections.abc.Iterable): Yaml to deserialize (can be a callable that yields one line at a time)

    Returns:
        (list | dict | None): Deserialized object
    """
    scanner = Scanner(stream)
    return scanner.deserialized()


def load_string(text):
    """
    Args:
        text (str): Yaml to deserialize

    Returns:
        (list | dict | None): Deserialized object
    """
    scanner = Scanner(text.splitlines())
    return scanner.deserialized()


def tokens_from_path(path):
    with open(path) as fh:
        scanner = Scanner(fh)
        return list(scanner.tokens())


def tokens_from_stream(stream):
    scanner = Scanner(stream)
    return list(scanner.tokens())


def tokens_from_string(text):
    scanner = Scanner(text.splitlines())
    return list(scanner.tokens())
