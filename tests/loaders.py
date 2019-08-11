import datetime
import json
import os

import poyo
import strictyaml
import yaml as pyyaml
from ruamel.yaml import YAML as RYAML
from yaml.scanner import ScannerError

import zyaml


TESTS_FOLDER = os.path.abspath(os.path.dirname(__file__))
SAMPLE_FOLDER = os.path.join(TESTS_FOLDER, "samples")
SPEC_FOLDER = os.path.join(SAMPLE_FOLDER, "spec")


class Sample(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.basename = os.path.basename(self.path)
        self.folder = os.path.dirname(self.path)
        if self.path.startswith(SAMPLE_FOLDER):
            self.relative_path = self.path[len(SAMPLE_FOLDER) + 1:]
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

    @staticmethod
    def ignored_dirs(names):
        for name in names:
            if name.startswith("."):
                yield Sample(name)

    @staticmethod
    def find_samples(match, path=None):
        if path is None:
            for root, dirs, files in os.walk(SAMPLE_FOLDER):
                for name in list(Sample.ignored_dirs(dirs)):
                    dirs.remove(name)
                for fname in files:
                    if fname.endswith(".yml"):
                        for sample in Sample.find_samples(match, path=os.path.join(root, fname)):
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
                    for sample in Sample.get_samples(p):
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
                for sample in Sample.find_samples(path):
                    result.append(sample)
        return sorted(result, key=lambda x: "zz" + x.relative_path if "/" in x.relative_path else x.relative_path)


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


class YmlImplementation(object):
    """Implementation of loading a yml file"""
    available = []

    def __init__(self, func):
        self.name = func.__name__.replace("load_", "")
        self.func = func

    def __repr__(self):
        return self.name

    @staticmethod
    def add(func):
        """
        :param callable func: Implementation to use to load a yml file for this benchmark
        """
        YmlImplementation.available.append(YmlImplementation(func))
        return func

    def load(self, path):
        return self.func(path)

    def load_sanitized(self, path, stringify=as_is):
        try:
            return json_sanitized(self.func(path), stringify=stringify)

        except Exception:
            return None


def loaded_pyaml(stream, loader):
    docs = list(pyyaml.load_all(stream, Loader=loader))
    return zyaml.simplified(docs)


@YmlImplementation.add
def load_pyyaml_base(path):
    with open(path) as fh:
        return loaded_pyaml(fh, pyyaml.BaseLoader)


# @YmlImplementation.add
def load_pyyaml_full(path):
    with open(path) as fh:
        return loaded_pyaml(fh, pyyaml.FullLoader)


# @YmlImplementation.add
def load_pyyaml_safe(path):
    with open(path) as fh:
        return loaded_pyaml(fh, pyyaml.SafeLoader)


@YmlImplementation.add
def load_poyo(path):
    with open(path) as fh:
        return poyo.parse_string(fh.read())


def loaded_ruamel(stream):
    y = RYAML(typ="safe")
    y.constructor.yaml_constructors["tag:yaml.org,2002:timestamp"] = y.constructor.yaml_constructors["tag:yaml.org,2002:str"]
    return zyaml.simplified(list(y.load_all(stream)))


@YmlImplementation.add
def load_ruamel(path):
    with open(path) as fh:
        return loaded_ruamel(fh)


@YmlImplementation.add
def load_strict(path):
    with open(path) as fh:
        docs = strictyaml.load(fh.read())
        if len(docs) == 1:
            return docs[0]
        return docs[0] if len(docs) == 1 else docs


@YmlImplementation.add
def load_zyaml(path):
    docs = zyaml.load_path(path)
    return docs


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
