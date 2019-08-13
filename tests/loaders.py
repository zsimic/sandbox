"""
See https://github.com/zsimic/yaml for more info
"""

import datetime
import inspect
import json
import os
import re

import click
import poyo
import runez
import strictyaml
import yaml as pyyaml
from ruamel.yaml import YAML as RYAML

import zyaml


@runez.click.group()
@runez.click.debug()
@runez.click.log()
def main(debug, log):
    """Useful troubleshooting commands, useful for iterating on this lib"""
    runez.log.setup(debug=debug, file_location=log, locations=None)


class Setup(object):

    TESTS_FOLDER = os.path.abspath(os.path.dirname(__file__))
    SAMPLE_FOLDER = os.path.join(TESTS_FOLDER, "samples")
    LOADERS = []

    @staticmethod
    def implementations_option(option=True, **kwargs):
        def _callback(_ctx, _param, value):
            names = [s.strip() for s in value.split(",")]
            names = [s for s in names if s]
            result = []
            for name in names:
                impl = Setup.get_implementations(name)
                if not impl:
                    raise click.BadParameter("Unknown implementation %s" % name)
                result.extend(impl)
            return result

        kwargs.setdefault("default", "zyaml,ruamel")

        if option:
            kwargs.setdefault("help", "Implementation(s) to use")
            return click.option("--implementations", "-i", callback=_callback, **kwargs)

        return click.argument("implementations", callback=_callback, **kwargs)

    @staticmethod
    def samples_arg(option=False, **kwargs):
        def _callback(_ctx, _param, value):
            return Setup.get_samples(value)

        kwargs.setdefault("default", "spec")

        if option:
            kwargs.setdefault("help", "Sample(s) to use")
            return click.option("--samples", "-s", callback=_callback, **kwargs)

        return click.argument("samples", callback=_callback, **kwargs)

    @staticmethod
    def get_implementations(name):
        result = []
        for impl in Setup.LOADERS:
            if name in impl.name or name.replace("_", " ") in impl.name:
                result.append(impl)
        return result

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
    def get_samples(path):
        result = []
        if os.path.isdir(path):
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

    def refresh(self, loader=None):
        """
        :param BaseLoader loader: Loader to use
        """
        if loader is None:
            loader = ZyamlLoader()
        rep = loader.json_representation(self, stringify=as_is)
        with open(self.expected_path, "w") as fh:
            fh.write(rep)


class ParseResult(object):
    def __init__(self, loader, sample, data=None):
        self.loader = loader  # type: BaseLoader
        self.wrap = str
        self.sample = sample
        self.data = data
        self.exception = None
        self.error = None

    def __repr__(self):
        if self.error:
            return "error: %s" % self.error
        return self.wrap(self.data)

    def diff(self, other):
        if self.error or other.error:
            if self.error and other.error:
                return "invalid"
            return "%s %s  " % ("F " if self.error else "  ", "F " if other.error else "  ")
        if self.data == other.data:
            return "match  "
        return "diff   "


class BaseLoader(object):
    """Implementation of loading a yml file"""

    def __repr__(self):
        return self.name

    @property
    def name(self):
        return " ".join(s.lower() for s in re.findall("[A-Z][^A-Z]*", self.__class__.__name__.replace("Loader", "")))

    def _load(self, stream):
        return []

    def tokens(self, sample, comments=True):
        try:
            with open(sample.path) as fh:
                for t in self._tokens(fh.read(), comments):
                    yield t
        except Exception as e:
            yield "--> can't get tokens: %s" % e

    def _tokens(self, contents, comments):
        raise Exception("not implemented")

    def load_stream(self, contents):
        data = self._load(contents)
        if data is not None and inspect.isgenerator(data):
            data = list(data)
        return zyaml.simplified(data)

    def load_path(self, path):
        with open(path) as fh:
            return self.load_stream(fh)

    def load(self, sample, stacktrace=None):
        if stacktrace is None:
            # By default, show stacktrace when running in pycharm
            stacktrace = "PYCHARM_HOSTED" in os.environ

        if stacktrace:
            return ParseResult(self, sample, self.load_path(sample.path))

        result = ParseResult(self, sample)
        try:
            result.data = self.load_path(sample.path)
        except Exception as e:
            result.exception = e
            result.error = str(e)
        return result

    def json_representation(self, sample, stringify=as_is):
        result = self.load(sample)
        return json_representation(result.data, stringify=stringify)


def json_representation(data, stringify=as_is):
    data = json_sanitized(data, stringify=stringify)
    return json.dumps(data, sort_keys=True, indent=2)


class ZyamlLoader(BaseLoader):
    def _load(self, stream):
        return zyaml.load_string(stream.read())

    def _tokens(self, stream, comments):
        settings = zyaml.ScanSettings(yield_comments=comments)
        return zyaml.scan_tokens(stream, settings=settings)


class RuamelLoader(BaseLoader):
    def _load(self, stream):
        y = RYAML(typ="safe")
        y.constructor.yaml_constructors["tag:yaml.org,2002:timestamp"] = y.constructor.yaml_constructors["tag:yaml.org,2002:str"]
        return y.load_all(stream)


class PyyamlBaseLoader(BaseLoader):
    def _load(self, stream):
        return pyyaml.load_all(stream, Loader=pyyaml.BaseLoader)

    def _tokens(self, stream, comments):
        yaml_loader = pyyaml.BaseLoader(stream)
        curr = yaml_loader.get_token()
        while curr is not None:
            yield curr
            nxt = yaml_loader.get_token()
            if comments:
                for comment in self._comments_between_tokens(curr, nxt):
                    yield comment
            curr = nxt

    def _comments_between_tokens(self, token1, token2):
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
                yield zyaml.CommentToken(token1.end_mark.line, token1.end_mark.column, line[pos:])


class PoyoLoader(BaseLoader):
    def _load(self, stream):
        return [poyo.parse_string(stream.read())]


class StrictLoader(BaseLoader):
    def _load(self, stream):
        return strictyaml.load(stream.read())


for impl in BaseLoader.__subclasses__():
    Setup.LOADERS.append(impl())
