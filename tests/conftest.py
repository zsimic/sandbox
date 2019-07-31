import datetime
import json
import os
import re
import sys
import timeit
from functools import partial

import poyo
import pytest
import strictyaml
import yaml
from ruamel.yaml import YAML

import zyaml


SAMPLE_FOLDER = os.path.join(os.path.dirname(__file__), "samples")


def asis(value):
    return value


def json_sanitized(value, stringify=asis):
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
        self.basename = os.path.basename(path)
        self.name = self.basename.replace(".yml", "")
        self.folder = os.path.dirname(path)
        self.expected_path = os.path.join(self.folder, "expected", "%s.json" % self.name)
        self._expected = None
        self.path = path

    def __repr__(self):
        return self.name

    @property
    def expected(self):
        if self._expected is None:
            with open(self.expected_path) as fh:
                self._expected = json.load(fh)
        return self._expected

    def refresh(self):
        value = load_ruamel(self.path)
        value = json_sanitized(value)
        with open(self.expected_path, "w") as fh:
            json.dump(value, fh, sort_keys=True, indent=2)


class YmlImplementation(object):
    """Implementation of loading a yml file"""
    def __init__(self, func):
        self.name = func.__name__.replace("load_", "")
        self.func = func

    def __repr__(self):
        return self.name

    def load(self, path):
        return self.func(path)

    def load_sanitized(self, path, stringify=asis):
        try:
            return json_sanitized(self.func(path), stringify=stringify)

        except Exception as e:
            return None


class BenchmarkCollection(object):
    def __init__(self):
        self.available = []
        self.samples = []
        for fname in os.listdir(SAMPLE_FOLDER):
            if fname.endswith(".yml"):
                self.samples.append(Sample(os.path.join(SAMPLE_FOLDER, fname)))

    def add(self, func):
        """
        :param callable func: Implementation to use to load a yml file for this benchmark
        """
        self.available.append(YmlImplementation(func))
        return func

    def run(self):
        for sample in self.samples:
            bench = SingleBenchmark(sample.path)
            bench.run()
            print(bench.report())


BENCHMARKS = BenchmarkCollection()


@pytest.fixture
def samples():
    return BENCHMARKS.samples


@pytest.fixture
def benchmarks():
    return BENCHMARKS


class SingleBenchmark:
    def __init__(self, path):
        self.path = path
        self.fastest = None
        self.seconds = {}
        self.outcome = {}
        self.iterations = 100

    def add(self, name, seconds, message=None):
        if seconds is None:
            if not message:
                message = "failed"
            else:
                message = message.strip().replace("\n", " ")
                message = re.sub(r"\s+", " ", message)
                message = "failed: %s..." % message[:180]
            self.outcome[name] = message
            return
        if self.fastest is None or self.fastest > seconds:
            self.fastest = seconds
        self.seconds[name] = seconds

    def run(self):
        for impl in BENCHMARKS.available:
            try:
                t = timeit.Timer(stmt=partial(impl.load, self.path))
                self.add(impl.name, t.timeit(self.iterations))

            except Exception as e:
                self.add(impl.name, None, message="failed %s" % e)

        for name, seconds in self.seconds.items():
            info = "" if seconds == self.fastest else " [x %.1f]" % (seconds / self.fastest)
            self.outcome[name] = "%.3fs%s" % (seconds, info)

    def report(self):
        result = ["%s:" % os.path.basename(self.path)]
        for name, outcome in sorted(self.outcome.items()):
            result.append("  %s: %s" % (name, outcome))
        return "\n".join(result)


def load_pyaml(path, loader):
    with open(path) as fh:
        docs = list(yaml.load_all(fh, Loader=loader))
        if len(docs) == 1:
            return docs[0]
        return docs


@BENCHMARKS.add
def load_pyyaml_base(path):
    return load_pyaml(path, yaml.BaseLoader)


# @BENCHMARKS.add
# def load_pyyaml_full(path):
#     return load_pyaml(path, yaml.FullLoader)
#
#
# @BENCHMARKS.add
# def load_pyyaml_safe(path):
#     return load_pyaml(path, yaml.SafeLoader)
#
#
# @BENCHMARKS.add
# def load_poyo(path):
#     with open(path) as fh:
#         return poyo.parse_string(fh.read())
#
#
@BENCHMARKS.add
def load_ruamel(path):
    with open(path) as fh:
        yaml = YAML(typ="safe")
        docs = list(yaml.load_all(fh))
        if len(docs) == 1:
            return docs[0]
        return docs


@BENCHMARKS.add
def load_strict(path):
    with open(path) as fh:
        docs = strictyaml.load(fh.read())
        if len(docs) == 1:
            return docs[0]
        return docs


# @BENCHMARKS.add
# def load_zyaml(path):
#     with open(path) as fh:
#         d = zyaml.load(fh)
#         return d

from zyaml import Scanner

@BENCHMARKS.add
def load_zyaml1(path):
    with open(path) as fh:
        scanner = Scanner(fh)
        return scanner.scan1()


@BENCHMARKS.add
def load_zyaml2(path):
    with open(path) as fh:
        scanner = Scanner(fh)
        return scanner.scan2()


@BENCHMARKS.add
def load_lexemes(path):
    with open(path) as fh:
        scanner = Scanner(fh)
        return list(scanner.lexemes())


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "refresh":
        for s in BENCHMARKS.samples:
            s.refresh()
        sys.exit(0)
    BENCHMARKS.run()
