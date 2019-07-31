import os

import yaml

from zyaml import Scanner
from zyaml.scanner import Scanner2


def verify_sample(sample, benchmarks):
    for impl in benchmarks.available:
        value = impl.load_sanitized(sample.path, stringify=str)
        assert sample.name != "zyaml" or value is not None
        if value:
            assert value == sample.expected


def test_samples(samples, benchmarks):
    for sample in samples:
        verify_sample(sample, benchmarks)


def test_lexeme():
    p = os.path.join(os.path.dirname(__file__), "samples/example-2.1.yml")

    with open(p) as fh:
        from ruamel.yaml import YAML
        yaml = YAML(typ="safe")
        docs = list(yaml.load_all(fh))
        print(docs)

    with open(p) as fh:
        s = Scanner2(fh)
        l = list(s.tokens())
        print(l)


def test_tokens(samples, benchmarks):
    for sample in samples:
        value = benchmarks.available[0].load_sanitized(sample.path)
        with open(sample.path) as fh:
            scanner = Scanner(fh)
            ztokens = list(scanner.tokens(comments=True))

        with open(sample.path) as fh:
            ytokens = list(yaml_tokens(fh.read()))

        print("-- %s" % sample.path)

        print("-- zyaml tokens")
        print("\n".join(str(s) for s in ztokens))

        print("-- yaml tokens")
        print("\n".join(str(s) for s in ytokens))


def yaml_tokens(buffer, comments=True):
    yaml_loader = yaml.BaseLoader(buffer)

    try:
        curr = yaml_loader.get_token()
        while curr is not None:
            yield curr
            next = yaml_loader.get_token()
            if comments:
                for comment in comments_between_tokens(curr, next):
                    yield comment
            curr = next

    except yaml.scanner.ScannerError as e:
        print("--> scanner error: %s" % e)


def comments_between_tokens(token1, token2):
    """Find all comments between two tokens"""
    if token2 is None:
        buf = token1.end_mark.buffer[token1.end_mark.pointer:]

    elif (token1.end_mark.line == token2.start_mark.line and
          not isinstance(token1, yaml.StreamStartToken) and
          not isinstance(token2, yaml.StreamEndToken)):
        return

    else:
        buf = token1.end_mark.buffer[token1.end_mark.pointer:
                                     token2.start_mark.pointer]

    for line in buf.split('\n'):
        pos = line.find('#')
        if pos != -1:
            yield line[pos:]
