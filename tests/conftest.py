import codecs
import datetime
import logging
import os
import sys
from contextlib import contextmanager
from functools import partial

import click
import pytest
import runez

from zyaml import load_path, tokens_from_path
from zyaml.marshal import decode, ParseError

from . import TestSettings
from .benchmark import BenchmarkRunner
from .ximpl import implementation_option, ImplementationCollection, ParseResult, YmlImplementation


SAMPLE_FOLDER = runez.log.tests_path("samples")
K_DESERIALIZED = "json"
K_TOKEN = "token"
TESTED_SAMPLES = "flex,invalid,misc,valid"


@pytest.fixture
def all_samples():
    return get_samples(TESTED_SAMPLES)


def get_samples(sample_name):
    result = []
    for name in runez.flattened([sample_name], split=","):
        result.extend(scan_samples(name))

    return sorted(result, key=lambda x: x.key)


def ignored_dirs(names):
    return [name for name in names if name.startswith(".")]


def scan_samples(sample_name):
    sample_name = sample_name.strip()
    if not sample_name:
        return

    if os.path.isfile(sample_name) or os.path.isabs(sample_name):
        yield Sample(sample_name)
        return

    folder = os.path.join(SAMPLE_FOLDER, sample_name)
    if os.path.isdir(folder):
        sample_name = "all"

    else:
        folder = SAMPLE_FOLDER

    for root, dirs, files in os.walk(folder):
        for dir_name in ignored_dirs(dirs):
            dirs.remove(dir_name)

        for fname in files:
            if fname.endswith(".yml"):
                sample = Sample(os.path.join(root, fname))
                if sample.is_match(sample_name):
                    yield sample


def samples_arg(option=False, default=None, count=None, **kwargs):
    def _callback(_ctx, _param, value):
        if not option and not value:
            value = default

        if count == 1 and hasattr(value, "endswith") and not value.endswith("."):
            value += "."

        if not value:
            raise click.BadParameter("No samples specified")

        s = get_samples(value)
        if not s:
            raise click.BadParameter("No samples match %s" % value)

        if count and count != len(s):
            raise click.BadParameter("Need exactly %s, filter yielded %s" % (runez.plural(count, "sample"), len(s)))

        if count == 1:
            return s[0]

        return s

    kwargs.setdefault("metavar", "SAMPLE")
    name = "sample" if count == 1 else "samples"
    if option:
        if default:
            kwargs["default"] = default

        kwargs.setdefault("help", "Sample(s) to use")
        kwargs.setdefault("show_default", True)
        return click.option("--%s" % name, "-s", callback=_callback, **kwargs)

    kwargs.setdefault("nargs", count if count and count >= 1 else -1)
    return click.argument(name, callback=_callback, **kwargs)


@runez.click.group()
@runez.click.color()
@runez.click.debug()
@runez.click.dryrun()
@runez.click.log()
@click.option("--lines", "-l", default=None, is_flag=True, help="Show line numbers")
@click.option("--stacktrace", "-x", default=None, is_flag=True, help="Leave exceptions uncaught (to conveniently stop in debugger)")
def main(debug, log, lines, stacktrace):
    """Troubleshooting commands, useful for iterating on this library"""
    TestSettings.line_numbers = lines
    TestSettings.stacktrace = stacktrace
    runez.log.setup(debug=debug, console_level=logging.INFO, file_location=log, locations=None)
    logging.debug("Running with %s %s", runez.short(sys.executable), ".".join(str(s) for s in sys.version_info))
    runez.Anchored.add([runez.log.project_path(), SAMPLE_FOLDER])


@main.command()
@click.option("--iterations", "-n", default=100, help="Number of iterations to average")
@click.option("--tokens", "-t", is_flag=True, help="Tokenize only")
@implementation_option()
@samples_arg(default="bench")
def benchmark(iterations, tokens, implementation, samples):
    """Compare parsing speed of same file across yaml implementations"""
    for sample in samples:
        if tokens:
            impls = dict((i.name, partial(i.tokens, sample)) for i in implementation)

        else:
            impls = dict((i.name, partial(i.load_sample, sample)) for i in implementation)

        bench = BenchmarkRunner(impls, target_name=sample.name, iterations=iterations)
        bench.run()
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
@samples_arg()
def diff(compact, untyped, tokens, implementation, samples):
    """Compare deserialization of 2 implementations"""
    stringify = str if untyped else decode
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
                        result.data = impl.load_sample(sample)
                        result.text = runez.represented_json(result.data, stringify=stringify, dt=simplified_date)

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
def find(samples):
    """Show which samples match given filter"""
    for s in samples:
        print(s)


def move_sample_file(sample, new_category, new_basename, kind=None):
    dest = os.path.join(SAMPLE_FOLDER, new_category)
    if not os.path.isdir(dest):
        sys.exit("No folder %s" % runez.red(dest))

    if kind:
        extension = ".json"
        source = sample.expected_path(kind)
        dest = os.path.join(dest, "_xpct-%s" % kind)

    else:
        extension = ".yml"
        source = sample.path

    if os.path.isfile(source):
        dest = os.path.join(dest, new_basename + extension)
        runez.move(source, dest, logger=logging.info)


@main.command()
@samples_arg(count=1)
@click.argument("target", nargs=1)
def mv(sample, target):
    """Move a test sample (and its baseline) to a new place"""
    new_category, _, new_basename = target.partition("/")
    if "/" in new_basename:
        sys.exit("Invalid target '%s': use at most one / separator" % runez.red(target))

    if not new_basename:
        new_basename = sample.basename

    if new_basename.endswith(".yml"):
        new_basename = new_basename[:-4]

    old_source = os.path.join(sample.category, sample.basename)
    new_target = os.path.join(new_category, new_basename)
    if old_source == new_target:
        print("%s is already in the right spot" % runez.bold(sample))
        sys.exit(0)

    existing = get_samples(new_target + ".yml")
    if existing:
        sys.exit("There is already a sample '%s'" % runez.red(new_target))

    move_sample_file(sample, new_category, new_basename)
    move_sample_file(sample, new_category, new_basename, kind=K_DESERIALIZED)
    move_sample_file(sample, new_category, new_basename, kind=K_TOKEN)
    _clean()


@main.command(name="print")
@click.option("--tokens", "-t", is_flag=True, help="Show tokens as well")
@implementation_option()
@click.argument("text", nargs=-1)
def print_(tokens, implementation, text):
    """Deserialize given argument as yaml"""
    text = " ".join(text)
    text = codecs.decode(text, "unicode_escape")
    TestSettings.show_lines(text)
    for impl in implementation:
        assert isinstance(impl, YmlImplementation)
        if tokens:
            data = "\n".join(str(s) for s in impl.tokens(text))
            rtype = "tokens"

        else:
            data = impl.load_string(text)
            rtype = data.__class__.__name__ if data is not None else "None"

        print("---- %s: %s\n%s" % (runez.bold(impl), runez.dim(rtype), represented_result(data)))


def represented_result(data):
    if isinstance(data, Exception):
        return runez.red(runez.short(data))

    return runez.stringified(data, converter=runez.represented_json)


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
    bench.run()
    print(bench.report())


def _clean(verbose=False):
    cleanable = []
    for root, dirs, files in os.walk(SAMPLE_FOLDER):
        if not dirs and not files:
            cleanable.append(root)

        if os.path.basename(root).startswith("_xpct-"):
            for fname in files:
                ypath = os.path.dirname(root)
                ypath = os.path.join(ypath, "%s.yml" % runez.basename(fname))
                if not os.path.isfile(ypath):
                    # Delete _xpct-* files that correspond to moved samples
                    cleanable.append(os.path.join(root, fname))

    if not cleanable:
        if verbose:
            print("No cleanable _xpct- files found")

        return

    for path in cleanable:
        runez.delete(path, logger=logging.info)

    for root, dirs, files in os.walk(SAMPLE_FOLDER):
        if not dirs and not files:
            cleanable.append(root)
            runez.delete(root, logger=logging.info)

    print("%s cleaned" % runez.plural(cleanable, "file"))


@main.command()
def clean():
    """Clean tests/samples/, remove left-over old baselines"""
    _clean(verbose=True)


@main.command()
@click.option("--existing", is_flag=True, help="Replay existing case only")
@click.option("--tokens", "-t", is_flag=True, help="Replay tokens only")
@samples_arg(default=TESTED_SAMPLES)
def replay(existing, tokens, samples):
    """Rerun samples and compare them with their current baseline"""
    kinds = []
    if tokens:
        kinds.append(K_TOKEN)

    skipped = 0
    for sample in samples:
        report = sample.replay(*kinds)
        if report is runez.UNSET:
            skipped += 1
            report = None if existing else " %s" % runez.yellow("skipped")

        elif report:
            report = "\n%s" % "\n".join("  %s" % s for s in report.splitlines())

        else:
            report = " %s" % runez.green("OK")

        if report is not None:
            print("** %s:%s" % (runez.bold(sample.name), report))

    if skipped:
        print(runez.dim("-- %s skipped" % runez.plural(skipped, "sample")))


@main.command()
@click.option("--existing", is_flag=True, help="Refresh existing case only")
@click.option("--tokens", "-t", is_flag=True, help="Refresh tokens only")
@samples_arg(default=TESTED_SAMPLES)
def refresh(existing, tokens, samples):
    """Refresh expected baseline for each test sample"""
    kinds = []
    if tokens:
        kinds.append(K_TOKEN)

    _clean()
    for sample in samples:
        sample.refresh(*kinds, existing=existing)


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
@click.option("--tokens", "-t", is_flag=True, help="Show yaml tokens as well")
@implementation_option()
@samples_arg()
def show(profile, tokens, implementation, samples):
    """Show deserialized yaml objects as json"""
    with profiled(profile) as is_profiling:
        for sample in samples:
            TestSettings.show_lines(sample)
            assert isinstance(implementation, ImplementationCollection)
            for impl in implementation:
                if tokens and impl.name == "zyaml":
                    result = "\n".join(str(s) for s in impl.tokens(sample))
                    print("---- %s tokens:\n%s" % (impl, result))

                print("--------  %s  --------" % impl)
                assert isinstance(impl, YmlImplementation)
                result = impl.load_sample(sample)
                if is_profiling:
                    return

                if result.error:
                    rep = runez.red(result.error)
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
@implementation_option(default="zyaml,pyyaml")
@samples_arg()
def tokens(implementation, samples):
    """Show tokens for given samples"""
    for sample in samples:
        TestSettings.show_lines(sample)
        for impl in implementation:
            print("--------  %s  --------" % impl)
            for t in impl.tokens(sample):
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
        self._expected = {}

    def __repr__(self):
        return self.name

    def expected_path(self, kind):
        return os.path.join(self.folder, "_xpct-%s" % kind, "%s.json" % self.basename)

    def expected_content(self, kind):
        path = self.expected_path(kind)
        content = self._expected.get(kind)
        if content is not None:
            return content

        content = runez.UNSET
        if os.path.exists(path):
            content = runez.read_json(path)

        self._expected[kind] = content
        return content

    def is_match(self, name):
        if name == "all":
            return True

        if name.endswith("."):  # Special case when looking for exactly 1 sample
            if name[:-1] == self.basename:
                return True

            if self.basename.endswith(name[:-1]) and len(self.basename) > len(name):
                return self.basename[-len(name)] == "-"

            return False

        if self.name.startswith(name):
            return True

        if self.category.startswith(name):
            return True

        if self.basename.startswith(name) or self.basename.endswith(name):
            return True

    def deserialized(self, kind):
        try:
            if kind == K_TOKEN:
                tokens = tokens_from_path(self.path)
                actual = [str(t) for t in tokens]

            else:
                actual = load_path(self.path)
                actual = runez.serialize.json_sanitized(actual, stringify=decode)

        except ParseError as e:
            actual = {"_error": runez.short(e)}

        return actual

    def replay(self, *kinds):
        """
        Args:
            kinds: Kinds to replay (json and/or token)

        Returns:
            (str | runez.UNSET | None): Message explaining why replay didn't yield expected (UNSET if no baseline available)
        """
        if not kinds:
            kinds = (K_DESERIALIZED, K_TOKEN)

        problem = runez.UNSET
        for kind in kinds:
            expected = self.expected_content(kind)
            if expected is not None and expected is not runez.UNSET:
                actual = self.deserialized(kind)
                problem = textual_diff(kind, actual, expected)
                if problem:
                    return problem

        return problem

    def refresh(self, *kinds, **kwargs):
        """
        Args:
            kinds: Kinds to replay (json and/or token)
        """
        existing = kwargs.pop("existing", False)
        if not kinds:
            kinds = (K_DESERIALIZED, K_TOKEN)

        for kind in kinds:
            if existing:
                expected = self.expected_content(kind)
                if expected is runez.UNSET:
                    continue

            actual = self.deserialized(kind)
            path = self.expected_path(kind)
            runez.save_json(actual, path, keep_none=True, logger=logging.info)


def diff_overview(kind, actual, expected, message):
    report = ["[%s] %s" % (kind, message)]
    if actual is not None:
        report.append("actual: %s" % actual)

    if expected is not None:
        report.append("expected: %s" % expected)

    return "\n".join(report)


def textual_diff(kind, actual, expected):
    actual_error = isinstance(actual, dict) and actual.get("_error") or None
    expected_error = isinstance(expected, dict) and expected.get("_error") or None
    if actual_error != expected_error:
        if actual_error:
            return diff_overview(kind, actual_error, expected_error, "deserialization failed")

        return diff_overview(kind, actual_error, expected_error, "deserialization did NOT yield expected error")

    if type(actual) != type(expected):
        return diff_overview(kind, type(actual), type(expected), "differing types")

    if kind == K_TOKEN:
        actual = "%s\n" % "\n".join(actual)
        expected = "%s\n" % "\n".join(expected)

    else:
        actual = runez.represented_json(actual, keep_none=True)
        expected = runez.represented_json(expected, keep_none=True)

    if actual != expected:
        with runez.TempFolder(dryrun=False):
            runez.write("actual", actual)
            runez.write("expected", expected)
            r = runez.run("diff", "-br", "-U1", "expected", "actual", fatal=None, dryrun=False)
            return formatted_diff(r.full_output)


def formatted_diff(text):
    if text:
        result = []
        for line in text.splitlines():
            if line.startswith("--- expected"):
                line = "--- expected"

            elif line.startswith("+++ actual"):
                line = "+++ actual"

            result.append(line.strip())

        return "\n".join(result)


if __name__ == "__main__":
    main()
