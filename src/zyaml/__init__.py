from .scanner import Scanner
from .visitor import TokenVisitor


__version__ = "0.1.2"


def load_path(path, visitor=TokenVisitor):
    """
    Args:
        path (str): Path to file to deserialize
        visitor (type(TokenVisitor)): Visitor to use

    Returns:
        (list): Deserialized documents
    """
    with open(path) as fh:
        return deserialized(Scanner(fh), visitor)


def load_string(text, visitor=TokenVisitor):
    """
    Args:
        text (str): Yaml to deserialize
        visitor (type(TokenVisitor)): Visitor to use

    Returns:
        (list): Deserialized documents
    """
    return deserialized(Scanner(text.splitlines()), visitor)


def deserialized(scanner, visitor):
    """
    Args:
        scanner (Scanner): Token scanner
        visitor (type(TokenVisitor)): Visitor to use

    Returns:
        (list): Deserialized documents
    """
    visitor = visitor()
    assert isinstance(visitor, TokenVisitor)
    return visitor.deserialized(scanner.tokens())


def tokens_from_path(path):
    with open(path) as fh:
        scanner = Scanner(fh)
        return list(scanner.tokens())


def tokens_from_string(text):
    scanner = Scanner(text.splitlines())
    return scanner.tokens()
