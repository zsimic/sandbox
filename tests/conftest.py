import os
import re
import timeit
from functools import partial

import poyo
import poyo.parser
import poyo.patterns
import yaml
from ruamel.yaml import YAML

import zyaml


DATA_FOLDER = os.path.join(os.path.dirname(__file__), "data")
BENCHMARKS = {}


def benchmarkable(func):
    name = func.__name__.replace("load_", "")
    BENCHMARKS[name] = func
    return func


def data_paths(folder=DATA_FOLDER):
    for fname in os.listdir(folder):
        fpath = os.path.join(folder, fname)
        if fname.endswith(".yml"):
            yield fpath


def run_benchmarks():
    for path in data_paths():
        bench = Benchmark(path)
        bench.run()
        print(bench.report())


class Benchmark:
    def __init__(self, path):
        self.path = path
        self.fastest = None
        self.seconds = {}
        self.outcome = {}
        self.benchmarks = BENCHMARKS
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
        for name, func in self.benchmarks.items():
            try:
                t = timeit.Timer(stmt=partial(func, self.path))
                self.add(name, t.timeit(self.iterations))

            except Exception as e:
                self.add(name, None, message="failed %s" % e)

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


@benchmarkable
def load_pyyaml_base(path):
    return load_pyaml(path, yaml.BaseLoader)


@benchmarkable
def load_pyyaml_full(path):
    return load_pyaml(path, yaml.FullLoader)


@benchmarkable
def load_pyyaml_safe(path):
    return load_pyaml(path, yaml.SafeLoader)


@benchmarkable
def load_poyo(path):
    with open(path) as fh:
        return poyo.parse_string(fh.read())


@benchmarkable
def load_ruamel(path):
    with open(path) as fh:
        yaml = YAML(typ="safe")
        docs = list(yaml.load_all(fh))
        if len(docs) == 1:
            return docs[0]
        return docs


@benchmarkable
def load_zyaml(path):
    with open(path) as fh:
        d = zyaml.load(fh)
        return d


if __name__ == "__main__":
    run_benchmarks()
