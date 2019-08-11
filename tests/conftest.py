from __future__ import absolute_import

import json
import os
import re
import sys
import timeit
from functools import partial

import pytest

import zyaml

try:
    from .loaders import json_sanitized, load_ruamel, loaded_ruamel, Sample, yaml_tokens, YmlImplementation
except ImportError:
    from loaders import json_sanitized, load_ruamel, loaded_ruamel, Sample, yaml_tokens, YmlImplementation


SAMPLE_FOLDER = os.path.join(os.path.dirname(__file__), "samples")
SPEC_FOLDER = os.path.join(SAMPLE_FOLDER, "spec")


class BenchmarkCollection(object):
    def __init__(self, samples):
        self.samples = samples

    def run(self, *names):
        for sample in self.samples:
            bench = SingleBenchmark(sample.path)
            bench.run()
            print(bench.report())


@pytest.fixture
def spec_samples():
    return Sample.get_samples("spec")


@pytest.fixture
def samples():
    return Sample.get_samples("spec")


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
        for impl in YmlImplementation.available:
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


def show_jsonified(func, path):
    """
    :param callable func: Function to use to deserialize contents of 'path'
    :param str path: Path to yaml file to deserialize
    """
    name = func.__name__
    try:
        if name == "load_path":
            name = "zyaml"
        else:
            name = name.replace("load_", "")
        docs = func(path)
        docs = json_sanitized(docs)
        print("-- %s:\n%s" % (name, json.dumps(docs, sort_keys=True, indent=2)))
        return docs

    except Exception as e:
        print("-- %s:\n%s" % (name, e))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        args = sys.argv[2:]

    else:
        command = "benchmark"
        args = []

    if command == "benchmark":
        BenchmarkCollection(Sample.get_samples("spec")).run(*args)
        sys.exit(0)

    if command == "refresh":
        for sample in Sample.get_samples("spec"):
            sample.refresh()
        sys.exit(0)

    if command == "match":
        for sample in Sample.get_samples(args, default=["spec", SAMPLE_FOLDER]):
            try:
                zdoc = zyaml.load_path(sample.path)
            except Exception:
                zdoc = None

            try:
                rdoc = load_ruamel(sample.path)
            except Exception:
                rdoc = None

            if zdoc is None or rdoc is None:
                if zdoc is None and rdoc is None:
                    match = "invalid"
                else:
                    match = "%s %s  " % (" " if zdoc else "zF", " " if rdoc else "rF")
            elif zdoc == rdoc:
                match = "match "
            else:
                match = "diff  "
            print("%s %s" % (match, sample))
        sys.exit(0)

    if command == "samples":
        print("\n".join(str(s) for s in Sample.get_samples(args)))
        sys.exit(0)

    if command == "print":
        for arg in args:
            arg = arg.replace("\\n", "\n") + "\n"
            zdoc = json_sanitized(zyaml.load_string(arg))
            print("-- zdoc:\n%s" % zdoc)
            rdoc = loaded_ruamel(arg)
            print("-- ruamel:\n%s" % rdoc)
        sys.exit(0)

    if command == "show":
        for sample in Sample.get_samples(args):
            print("==== %s:" % sample)
            zdoc = show_jsonified(zyaml.load_path, sample.path)
            rdoc = show_jsonified(load_ruamel, sample.path)
            print("\nmatch: %s" % (zdoc == rdoc))
        sys.exit(0)

    if command == "tokens":
        for sample in Sample.get_samples(args):
            print("==== %s:" % sample)
            with open(sample.path) as fh:
                ztokens = list(zyaml.scan_tokens(fh.read()))

            with open(sample.path) as fh:
                ytokens = list(yaml_tokens(fh.read()))

            print("\n-- zyaml tokens")
            print("\n".join(str(s) for s in ztokens))
            print("\n\n-- yaml tokens")
            print("\n".join(str(s) for s in ytokens))
            print("\n")
        sys.exit(0)

    sys.exit("Unknown command %s" % command)
