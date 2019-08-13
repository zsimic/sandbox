"""
See https://github.com/zsimic/yaml for more info
"""

import datetime
import inspect
import json
import os

import poyo
import runez
import strictyaml
import yaml as pyyaml
from ruamel.yaml import YAML as RYAML
from yaml.scanner import ScannerError


import zyaml


@runez.click.group()
@runez.click.debug()
@runez.click.log()
def main(debug, log):
    """Useful troubleshooting commands, useful for iterating on this lib"""
    runez.log.setup(debug=debug, file_location=log, locations=None)


def samples(**kwargs):
    """Samples to use"""
    kwargs.setdefault("default", "spec")
    return runez.click.option(samples, **kwargs)


class Setup(object):

    TESTS_FOLDER = os.path.abspath(os.path.dirname(__file__))
    SAMPLE_FOLDER = os.path.join(TESTS_FOLDER, "samples")
    SPEC_FOLDER = os.path.join(SAMPLE_FOLDER, "spec")
    YML_IMPLEMENTATIONS = []

    @staticmethod
    def implementations(names):
        names = set(names.split(","))
        return [i for i in Setup.YML_IMPLEMENTATIONS if i.name in names]

    @staticmethod
    def ignored_dirs(names):
        for name in names:
            if name.startswith("."):
                yield Sample(name)

    @staticmethod
    def find_samples(match, path=None):
        if path is None:
            for root, dirs, files in os.walk(Setup.SAMPLE_FOLDER):
                for name in list(Setup.ignored_dirs(dirs)):
                    dirs.remove(name)
                for fname in files:
                    if fname.endswith(".yml"):
                        for sample in Setup.find_samples(match, path=os.path.join(root, fname)):
                            yield sample
            return
        sample = Sample(path)
        if match == "all" or match in sample.relative_path:
            yield sample

    @staticmethod
    def get_samples(path=None, default="misc.yml"):
        if not path:
            path = default
        result = []
        if path:
            if isinstance(path, list):
                for p in path:
                    for sample in Setup.get_samples(p):
                        result.append(sample)
            elif os.path.isdir(path):
                path = os.path.abspath(path)
                for fname in os.listdir(path):
                    if fname.endswith(".yml"):
                        sample = Sample(os.path.join(path, fname))
                        result.append(sample)
            elif os.path.isfile(path) or os.path.isabs(path):
                result.append(Sample(path))
            else:
                for sample in Setup.find_samples(path):
                    result.append(sample)
        return sorted(result, key=lambda x: "zz" + x.relative_path if "/" in x.relative_path else x.relative_path)


class Sample(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.basename = os.path.basename(self.path)
        self.folder = os.path.dirname(self.path)
        if self.path.startswith(Setup.SAMPLE_FOLDER):
            self.relative_path = self.path[len(Setup.SAMPLE_FOLDER) + 1:]
        else:
            self.relative_path = self.path
        self._expected = None

    def __repr__(self):
        return self.relative_path

    @property
    def expected_path(self):
        return os.path.join(self.folder, "expected", self.basename.replace(".yml", ".json"))

    @property
    def expected(self):
        if self._expected is None:
            try:
                with open(self.expected_path) as fh:
                    self._expected = json.load(fh)
            except (OSError, IOError):
                return None
        return self._expected

    def refresh(self):
        value = load_ruamel(self.path)
        value = json_sanitized(value)
        with open(self.expected_path, "w") as fh:
            json.dump(value, fh, sort_keys=True, indent=2)


def as_is(value):
    return value


def json_sanitized(value, stringify=as_is):
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        return [json_sanitized(v) for v in value]
    if isinstance(value, dict):
        return dict((str(k), json_sanitized(v)) for k, v in value.items())
    if isinstance(value, datetime.date):
        return str(value)
    if not isinstance(value, (int, str, float)):
        return stringify(value)
    return stringify(value)


class ParseResult(object):
    def __init__(self, data=None):
        self.data = data
        self.exception = None
        self.error = None


class YmlImplementation(object):
    """Implementation of loading a yml file"""
    def __init__(self, func):
        self.name = func.__name__.replace("load_", "")
        self.func = func

    def __repr__(self):
        return self.name

    def load_stream(self, contents, wrap=None, stringify=None):
        is_full, data = self.func(contents)
        if data is not None and inspect.isgenerator(data):
            data = list(data)
        if is_full:
            data = zyaml.simplified(data)
        if wrap is not None:
            if stringify is None:
                stringify = as_is
            data = wrap(data, stringify)
        return data

    def load_path(self, path, wrap=None, stringify=None):
        with open(path) as fh:
            return self.load_stream(fh, wrap=wrap, stringify=stringify)

    def load(self, path, wrap=None, stringify=None, catch=None):
        if catch is None:
            # By default, do not catch exceptions when running in pycharm (debugger then conveniently stops on them)
            catch = "PYCHARM_HOSTED" not in os.environ

        if not catch:
            return ParseResult(self.load_path(path, wrap=wrap, stringify=stringify))

        result = ParseResult()
        try:
            result.data = self.load_path(path, wrap=wrap, stringify=stringify)
        except Exception as e:
            result.exception = e
            result.error = str(e)
        return result


def yaml_implementation(func):
    """Decorator to provide yaml implementation loaders easily"""
    Setup.YML_IMPLEMENTATIONS.append(YmlImplementation(func))
    return func


@yaml_implementation
def load_pyyaml_base(stream):
    return True, pyyaml.load_all(stream, Loader=pyyaml.BaseLoader)


@yaml_implementation
def load_pyyaml_full(stream):
    return True, pyyaml.load_all(stream, Loader=pyyaml.FullLoader)


@yaml_implementation
def load_pyyaml_safe(stream):
    return True, pyyaml.load_all(stream, Loader=pyyaml.SafeLoader)


@yaml_implementation
def load_poyo(stream):
    return False, poyo.parse_string(stream.read())


@yaml_implementation
def load_ruamel(stream):
    y = RYAML(typ="safe")
    y.constructor.yaml_constructors["tag:yaml.org,2002:timestamp"] = y.constructor.yaml_constructors["tag:yaml.org,2002:str"]
    return True, y.load_all(stream)


@yaml_implementation
def load_strict(stream):
    return True, strictyaml.load(stream.read())


@yaml_implementation
def load_zyaml(stream):
    return True, zyaml.load_string(stream.read())


def comments_between_tokens(token1, token2):
    """Find all comments between two tokens"""
    if token2 is None:
        buf = token1.end_mark.buffer[token1.end_mark.pointer:]

    elif (token1.end_mark.line == token2.start_mark.line and
          not isinstance(token1, pyyaml.StreamStartToken) and
          not isinstance(token2, pyyaml.StreamEndToken)):
        return

    else:
        buf = token1.end_mark.buffer[token1.end_mark.pointer:token2.start_mark.pointer]

    for line in buf.split('\n'):
        pos = line.find('#')
        if pos != -1:
            yield line[pos:]


def yaml_tokens(buffer, comments=True):
    yaml_loader = pyyaml.BaseLoader(buffer)
    try:
        curr = yaml_loader.get_token()
        while curr is not None:
            yield curr
            next = yaml_loader.get_token()
            if comments:
                for comment in comments_between_tokens(curr, next):
                    yield comment
            curr = next
    except ScannerError as e:
        print("--> scanner error: %s" % e)
