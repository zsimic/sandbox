import codecs
import datetime
import json
import logging
import os
import re
import sys
from contextlib import contextmanager
from functools import partial

import click
import pytest
import runez

import zyaml

from .benchmark import BenchmarkRunner
from .ximpl import implementation_option, ImplementationCollection, json_sanitized, ParseResult, YmlImplementation


SAMPLE_FOLDER = runez.log.tests_path("samples")


def ignored_dirs(names):
    for name in names:
        if name.startswith("."):
            yield Sample(name)


def scan_samples(sample_name):
    sample_name = sample_name.strip()
    if not sample_name:
        return

    if os.path.isfile(sample_name) or os.path.isabs(sample_name):
        yield Sample(sample_name)
        return

    folder = SAMPLE_FOLDER
    if os.path.isdir(sample_name):
        folder = sample_name
        sample_name = "all"

    for root, dirs, files in os.walk(folder):
        for dir_name in list(ignored_dirs(dirs)):
            dirs.remove(dir_name)

        for fname in files:
            if fname.endswith(".yml"):
                sample = Sample(os.path.join(root, fname))
                if sample.is_match(sample_name):
                    yield sample


def get_samples(sample_name):
    result = []
    for name in runez.flattened([sample_name], split=","):
        result.extend(scan_samples(name))

    return sorted(result, key=lambda x: x.key)


TESTED_SAMPLES = "flex,invalid,minor,valid"


@pytest.fixture
def all_samples():
    return get_samples(TESTED_SAMPLES)


def stacktrace_option():
    return click.option(
        "--stacktrace", "-x",
        default=None, is_flag=True,
        help="Leave exceptions uncaught (to conveniently stop in debugger)"
    )


def samples_arg(option=False, default=None, count=None, **kwargs):
    def _callback(_ctx, _param, value):
        if count == 1 and hasattr(value, "endswith") and not value.endswith("."):
            value += "."

        if not value:
            raise click.BadParameter("No samples specified")

        s = get_samples(value)
        if not s:
            raise click.BadParameter("No samples match %s" % value)

        if count is not None and 0 < count != len(s):
            raise click.BadParameter("Need exactly %s, filter yielded %s" % (runez.plural(count, "sample"), len(s)))

        return s

    kwargs["default"] = default
    kwargs.setdefault("metavar", "SAMPLE")

    if option:
        kwargs.setdefault("help", "Sample(s) to use")
        kwargs.setdefault("show_default", True)
        return click.option("--samples", "-s", callback=_callback, **kwargs)

    return click.argument("samples", callback=_callback, **kwargs)


@runez.click.group()
@runez.click.debug()
@runez.click.log()
def main(debug, log):
    """Troubleshooting commands, useful for iterating on this library"""
    runez.log.setup(debug=debug, file_location=log, locations=None)
    logging.debug("Running with %s %s", runez.short(sys.executable), ".".join(str(s) for s in sys.version_info))
    runez.Anchored.add([runez.log.project_path(), SAMPLE_FOLDER])


@main.command()
@stacktrace_option()
@click.option("--iterations", "-n", default=100, help="Number of iterations to average")
@click.option("--tokens", "-t", is_flag=True, help="Tokenize only")
@implementation_option()
@samples_arg(default="bench")
def benchmark(stacktrace, iterations, tokens, implementation, samples):
    """Run parsing benchmarks"""
    for sample in samples:
        if tokens:
            impls = dict((i.name, partial(i.tokens, sample)) for i in implementation)

        else:
            impls = dict((i.name, partial(i.load, sample)) for i in implementation)

        bench = BenchmarkRunner(impls, target_name=sample.name, iterations=iterations)
        bench.run(stacktrace)
        print(bench.report())


def simplified_date(value):
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            if value.tzinfo != datetime.timezone.utc:  # Get back to ruamel-like flawed time-zoning
                value = value.astimezone(datetime.timezone.utc)

            value = value.replace(tzinfo=None)

    return str(value)


@main.command()
@click.option("--compact/--no-compact", "-1", is_flag=True, default=None, help="Do not show diff text")
@click.option("--untyped", "-u", is_flag=True, help="Parse everything as strings")
@click.option("--tokens", "-t", is_flag=True, help="Compare tokens")
@implementation_option(count=2)
@samples_arg(nargs=-1)
def diff(compact, untyped, tokens, implementation, samples):
    """Compare deserialization of 2 implementations"""
    stringify = str if untyped else zyaml.decode
    if compact is None:
        compact = len(samples) > 1

    with runez.TempFolder():
        generated_files = []
        for sample in samples:
            generated_files.append([sample])
            for impl in implementation:
                assert isinstance(impl, YmlImplementation)
                result = ParseResult(impl, sample)
                try:
                    if tokens:
                        result.data = list(impl.tokens(sample))
                        result.text = "\n".join(impl.represented_token(t) for t in result.data)

                    else:
                        result.data = impl.load_path(sample.path)
                        payload = json_sanitized(result.data, stringify=stringify, dt=simplified_date)
                        result.text = runez.represented_json(payload)

                except Exception as e:
                    result.set_exception(e)
                    result.text = result.error

                fname = "%s-%s.text" % (impl.name, sample.basename)
                generated_files[-1].extend([fname, result])
                if not compact:
                    with open(fname, "w") as fh:
                        fh.write(result.text)
                        if not result.text.endswith("\n"):
                            fh.write("\n")

        matches = 0
        failed = 0
        differ = 0
        for sample, n1, r1, n2, r2 in generated_files:
            if r1.error and r2.error:
                matches += 1
                failed += 1
                print("%s: both failed" % sample)

            elif r1.text == r2.text:
                matches += 1
                print("%s: OK" % sample)

            else:
                differ += 1
                if compact:
                    print("%s: differ" % sample)

        if not compact:
            for sample, n1, r1, n2, r2 in generated_files:
                if r1.text != r2.text:
                    r = runez.run("diff", "-br", "-U1", n1, n2, fatal=None)
                    print("========  %s  ========" % sample)
                    print(r.full_output)
                    print()

        print()
        print("%s samples, %s match, %s differ, %s failed" % (matches + differ, matches, differ, failed))


@main.command()
@samples_arg()
def find_samples(samples):
    """Show which samples match given filter"""
    for s in samples:
        print(s)


def move(source, dest, basename, extension, subfolder=None):
    if os.path.isfile(source):
        if subfolder:
            dest = os.path.join(dest, subfolder)

        dest = os.path.join(dest, basename + extension)
        print("Moving %s -> %s" % (runez.short(source), runez.short(dest)))
        runez.move(source, dest)


@main.command()
@samples_arg(count=1)
@click.argument("category", nargs=1)
def mv(samples, category):
    """Move a sample to a given category"""
    sample = samples[0]
    if sample.category == category:
        print("%s is already in %s" % (sample, category))
        sys.exit(0)

    dest = os.path.join(SAMPLE_FOLDER, category)
    if not os.path.isdir(dest):
        sys.exit("No folder %s" % runez.short(dest))

    move(sample.path, dest, sample.basename, ".yml")
    move(sample.expected_path, dest, sample.basename, ".json", subfolder="_expected")


@main.command(name="print")
@click.option("--tokens", "-t", is_flag=True, help="Show zyaml tokens as well")
@stacktrace_option()
@implementation_option(default="zyaml,ruamel")
@click.argument("text", nargs=-1)
def print_(tokens, stacktrace, implementation, text):
    """Deserialize given argument as yaml"""
    text = " ".join(text)
    text = codecs.decode(text, "unicode_escape")
    print("--- raw:\n%s" % text)
    for impl in implementation:
        assert isinstance(impl, YmlImplementation)
        if tokens and impl.name == "zyaml":
            result = "\n".join(str(s) for s in impl.tokens(text, stacktrace=stacktrace))
            print("---- %s tokens:\n%s" % (impl, result))

        if stacktrace:
            data = impl.load_string(text)
            rtype = data.__class__.__name__ if data is not None else "None"
            result = impl.json_representation(ParseResult(impl, None, data=data))[:-1]

        else:
            try:
                data = impl.load_string(text)
                rtype = data.__class__.__name__ if data is not None else "None"
                result = impl.json_representation(ParseResult(impl, None, data=data))[:-1]

            except Exception as e:
                rtype = "error"
                result = str(e).replace("\n", " ") or e.__class__.__name__
                result = re.sub(r"\s+", " ", result)
                result = runez.short(result)

        print("---- %s: %s\n%s" % (impl, rtype, result))


def _bench1(size):
    return "%s" % size


def _bench2(size):
    return "{}".format(size)


@main.command()
@click.option("--iterations", "-i", default=100, help="Number of iterations to run")
@click.option("--size", "-s", default=100000, help="Simulated size of each iteration")
def quick_bench(iterations, size):
    """Convenience entry point to time different function samples"""
    functions = {}
    for name, func in globals().items():
        if name.startswith("_bench"):
            name = name[1:]
            functions[name] = partial(func, size)

    bench = BenchmarkRunner(functions, iterations=iterations)
    bench.run(stacktrace=True)
    print(bench.report())


@main.command()
@stacktrace_option()
@implementation_option(count=1, default="zyaml")
@samples_arg(default=TESTED_SAMPLES)
def refresh(stacktrace, implementation, samples):
    """Refresh expected json for each sample"""
    for root, dirs, files in os.walk(SAMPLE_FOLDER):
        if root.endswith("_expected"):
            for fname in files:
                ypath = os.path.dirname(root)
                ypath = os.path.join(ypath, fname.replace(".json", ".yml"))
                if not os.path.isfile(ypath):
                    # Delete _expected json files for yml files that have been moved
                    jpath = os.path.join(root, fname)
                    print("Deleting %s" % runez.short(jpath))
                    os.unlink(jpath)

    for sample in samples:
        sample.refresh(impl=implementation, stacktrace=stacktrace)


@contextmanager
def profiled(enabled):
    if not enabled:
        yield False
        return

    import cProfile
    profiler = cProfile.Profile()
    try:
        profiler.enable()
        yield True

    finally:
        profiler.disable()
        filepath = runez.log.project_path(".tox", "lastrun.profile")
        try:
            profiler.dump_stats(filepath)
            if runez.which("qcachegrind") is None:
                print("run 'brew install qcachegrind'")
                return

            runez.run("pyprof2calltree", "-k", "-i", filepath, stdout=None, stderr=None)

        except Exception as e:
            print("Can't save %s: %s" % (filepath, e))


@main.command()
@click.option("--profile", is_flag=True, help="Enable profiling")
@click.option("--tokens", "-t", is_flag=True, help="Show zyaml tokens as well")
@click.option("--line-numbers", "-n", is_flag=True, help="Show line numbers when showing original yaml")
@stacktrace_option()
@implementation_option(default="zyaml,ruamel")
@samples_arg(default="misc")
def show(profile, tokens, line_numbers, stacktrace, implementation, samples):
    """Show deserialized yaml objects as json"""
    with profiled(profile) as is_profiling:
        for sample in samples:
            print("========  %s  ========" % sample)
            with open(sample.path) as fh:
                if line_numbers:
                    print("".join("%4s: %s" % (n + 1, s) for n, s in enumerate(fh.readlines())))

                else:
                    print("".join(fh.readlines()))

            assert isinstance(implementation, ImplementationCollection)
            for impl in implementation:
                if tokens and impl.name == "zyaml":
                    result = "\n".join(str(s) for s in impl.tokens(sample, stacktrace=stacktrace))
                    print("---- %s tokens:\n%s" % (impl, result))

                print("--------  %s  --------" % impl)
                assert isinstance(impl, YmlImplementation)
                result = impl.load(sample, stacktrace=stacktrace)
                if is_profiling:
                    return

                if result.error:
                    rep = "Error: %s\n" % result.error
                    implementation.track_result_combination(impl, "error")

                else:
                    rep = impl.json_representation(result)
                    implementation.track_result_combination(impl, rep)

                print(rep)

            if implementation.combinations:
                combinations = ["/".join(x) for x in implementation.combinations]
                fmt = "-- %%%ss %%s" % max(len(s) for s in combinations)
                for names, values in implementation.combinations.items():
                    print(fmt % ("/".join(names), "matches" if len(values) == 1 else "differ"))

                print()


@main.command()
@stacktrace_option()
@implementation_option(default="zyaml,pyyaml_base")
@samples_arg(default="misc")
def tokens(stacktrace, implementation, samples):
    """Show tokens for given samples"""
    for sample in samples:
        print("========  %s  ========" % sample)
        with open(sample.path) as fh:
            print("".join(fh.readlines()))

        for impl in implementation:
            print("--------  %s  --------" % impl)
            for t in impl.tokens(sample, stacktrace=stacktrace):
                print(impl.represented_token(t))

            print("")


class Sample(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.basename = os.path.basename(self.path)
        self.basename, _, self.extension = self.basename.rpartition(os.path.extsep)
        self.folder = os.path.dirname(self.path)
        self.name = runez.short(self.path)
        self.category = os.path.dirname(self.name)
        self.key = self.name if "/" in self.name else "./%s" % self.name
        self._expected = None

    def __repr__(self):
        return self.name

    @property
    def expected_path(self):
        return os.path.join(self.folder, "_expected", "%s.json" % self.basename)

    @property
    def expected(self):
        if self._expected is None:
            try:
                with open(self.expected_path) as fh:
                    self._expected = json.load(fh)

            except (OSError, IOError):
                return runez.UNSET

        return self._expected

    def is_match(self, name):
        if name == "all":
            return True

        if name.endswith("."):  # Special case when looking for exactly 1 sample
            if name[:-1] == self.basename:
                return True

            if self.basename.endswith(name[:-1]) and len(self.basename) > len(name):
                return self.basename[-len(name)] == "-"

            return False

        if self.category.startswith(name):
            return True

        if self.basename.startswith(name) or self.basename.endswith(name):
            return True

    def refresh(self, impl, stacktrace=None):
        """
        :param YmlImplementation impl: Implementation to use
        :param bool stacktrace: If True, don't catch parsing exceptions
        """
        result = impl.load(self, stacktrace=stacktrace)
        rep = impl.json_representation(result)
        folder = os.path.dirname(self.expected_path)
        if not os.path.isdir(folder):
            os.mkdir(folder)

        with open(self.expected_path, "w") as fh:
            fh.write(rep)


if __name__ == "__main__":
    main()
