import datetime
import inspect
import json
import os
import re
import sys
import timeit
from functools import partial

import click
import poyo
import pytest
import ruamel.yaml
import runez
import strictyaml
import yaml as pyyaml

import zyaml


TESTS_FOLDER = os.path.abspath(os.path.dirname(__file__))
PROJECT_FOLDER = os.path.dirname(TESTS_FOLDER)
SAMPLE_FOLDER = os.path.join(TESTS_FOLDER, "samples")


def relative_sample_path(path, base=SAMPLE_FOLDER):
    if path and path.startswith(base):
        return path[len(base) + 1:]
    return path


def ignored_dirs(names):
    for name in names:
        if name.startswith("."):
            yield Sample(name)


def get_descendants(ancestor, adjust=None, _result=None):
    if _result is None:
        _result = {}
    for m in ancestor.__subclasses__():
        name = m.__name__
        if adjust is not None:
            name = adjust(name)
        _result[name] = m
        get_descendants(m, adjust=adjust, _result=_result)
    return _result


def scan_samples(sample_name):
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
    if isinstance(sample_name, (list, tuple)):
        for name in sample_name:
            result.extend(scan_samples(name))
    else:
        result.extend(scan_samples(sample_name))
    return sorted(result, key=lambda x: x.key)


@pytest.fixture
def vanilla_samples():
    return get_samples("vanilla")


def json_sanitized(value, stringify=zyaml.decode, dt=str):
    if value is None:
        return None
    if isinstance(value, set):
        return [json_sanitized(v, stringify=stringify, dt=dt) for v in sorted(value)]
    if isinstance(value, (tuple, list)):
        return [json_sanitized(v, stringify=stringify, dt=dt) for v in value]
    if isinstance(value, dict):
        return dict((str(k), json_sanitized(v, stringify=stringify, dt=dt)) for k, v in value.items())
    if isinstance(value, datetime.date):
        return dt(value)
    if isinstance(value, strictyaml.representation.YAML):
        return dt(value)
    if stringify is None:
        return value
    if not isinstance(value, (int, str, float)):
        return stringify(value)
    return stringify(value)


class BenchmarkRunner(object):
    def __init__(self, functions, target_name=None, iterations=100):
        self.functions = functions
        self.target_name = target_name
        self.iterations = iterations
        self.fastest = None
        self.seconds = {}
        self.outcome = {}

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

    def run(self, stacktrace=False):
        for name, func in self.functions.items():
            t = timeit.Timer(stmt=func)
            if stacktrace:
                self.add(name, t.timeit(self.iterations))
                continue

            try:
                self.add(name, t.timeit(self.iterations))

            except Exception as e:
                self.add(name, None, message=runez.shortened(str(e)))

        for name, seconds in self.seconds.items():
            info = "" if seconds == self.fastest else " [x %.1f]" % (seconds / self.fastest)
            self.outcome[name] = "%.3fs%s" % (seconds, info)

    def report(self):
        result = []
        if self.target_name:
            result.append("%s:" % self.target_name)
        for name, outcome in sorted(self.outcome.items()):
            result.append("  %s: %s" % (name, outcome))
        return "\n".join(result)


def stacktrace_option():
    return click.option(
        "--stacktrace", "-x",
        default=None, is_flag=True,
        help="Leave exceptions uncaught (to conveniently stop in debugger)"
    )


class ImplementationCollection(object):
    def __init__(self, names, default="zyaml,ruamel"):
        self.available = get_descendants(YmlImplementation, adjust=lambda x: x.replace("Implementation", "").lower())
        self.available = dict((n, i()) for n, i in self.available.items())
        self.unknown = []
        self.selected = []
        self.uncombined = set("raw".split())
        if names.startswith("+"):
            names = "%s,%s" % (names[1:], default)
        names = [s.strip() for s in names.split(",")]
        names = [s for s in names if s]
        seen = {}
        for name in names:
            found = 0
            for i in self.available.values():
                if name == "all" or name in i.name:
                    if i.name not in seen:
                        seen[i.name] = True
                        self.selected.append(i)
                    found += 1
            if found == 0:
                self.unknown.append(name)
        self.combinations = None

    def track_result_combination(self, impl, value):
        name = impl.name
        if self.combinations is None:
            self.combinations = {}
            for i1 in self.selected:
                for i2 in self.selected:
                    if i1.name < i2.name and i1.name not in self.uncombined and i2.name not in self.uncombined:
                        self.combinations[(i1.name, i2.name)] = set()
        for names, values in self.combinations.items():
            if name in names:
                values.add(value)

    def __repr__(self):
        return ",".join(str(i) for i in self.selected)

    def __len__(self):
        return len(self.selected)

    def __iter__(self):
        for i in self.selected:
            yield i


def implementations_option(option=True, default="zyaml,ruamel", count=None, **kwargs):
    """
    :param bool option: If True, make this an option
    :param str default: Default implementation(s) to use
    :param int|None count: Exact number of implementations needed (when applicable)
    :param kwargs: Passed-through to click
    :return ImplementationCollection: Implementations to use
    """
    kwargs["default"] = default

    def _callback(_ctx, _param, value):
        implementations = ImplementationCollection(value, default=default)
        if implementations.unknown:
            raise click.BadParameter("Unknown implementation%s %s" % (plural(len(implementations)), ", ".join(implementations.unknown)))
        if count and len(implementations) != count:
            if count == 1:
                raise click.BadParameter("Need exactly 1 implementation")
            raise click.BadParameter("Need exactly %s implementations" % count)
        return implementations

    if option:
        if count:
            hlp = "%s implementation%s to use" % (count, plural(count))
        else:
            hlp = "Implementations to use"
        kwargs.setdefault("help", hlp)
        kwargs.setdefault("show_default", True)
        kwargs.setdefault("metavar", "CSV")
        return click.option("--implementations", "-i", callback=_callback, **kwargs)

    return click.argument("implementations", callback=_callback, **kwargs)


def plural(count):
    return "s" if count != 1 else ""


def samples_arg(option=False, default="vanilla", count=None, **kwargs):
    def _callback(_ctx, _param, value):
        s = get_samples(value)
        if not s:
            raise click.BadParameter("No samples match %s" % value)
        if count and len(s) != count:
            raise click.BadParameter("Need exactly %s sample%s, filter yielded %s" % (count, plural(count), len(s)))
        return s

    kwargs["default"] = default
    kwargs.setdefault("metavar", "SAMPLE%s" % plural(count).upper())

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


@main.command()
@stacktrace_option()
@implementations_option()
@samples_arg()
def benchmark(stacktrace, implementations, samples):
    """Run parsing benchmarks"""
    for sample in samples:
        impls = dict((i.name, partial(i.load, sample)) for i in implementations)
        with runez.Anchored(SAMPLE_FOLDER):
            bench = BenchmarkRunner(impls, target_name=sample.name, iterations=200)
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
@stacktrace_option()
@click.option("--compact/--no-compact", "-1", is_flag=True, default=None, help="Do not show diff text")
@click.option("--untyped", "-u", is_flag=True, help="Parse everything as strings")
@implementations_option(count=2)
@samples_arg(nargs=-1, default=None)
def diff(stacktrace, compact, untyped, implementations, samples):
    """Compare deserialization of 2 implementations"""
    stringify = str if untyped else zyaml.decode
    if compact is None:
        compact = len(samples) > 1
    with runez.TempFolder():
        generated_files = []
        for sample in samples:
            generated_files.append([sample])
            for impl in implementations:
                assert isinstance(impl, YmlImplementation)
                result = impl.load(sample, stacktrace=stacktrace)
                if result.data is not None:
                    result.data = json_sanitized(result.data, stringify=stringify, dt=simplified_date)
                fname = "%s-%s.json" % (impl.name, sample.basename)
                generated_files[-1].extend([fname, result])
                result.json = "error" if result.error else impl.json_representation(result, stringify=stringify)
                if not compact:
                    with open(fname, "w") as fh:
                        if result.error:
                            fh.write("%s\n" % result.error)
                        else:
                            fh.write(result.json)

        matches = 0
        failed = 0
        differ = 0
        for sample, n1, r1, n2, r2 in generated_files:
            if r1.error and r2.error:
                matches += 1
                failed += 1
                print("%s: both failed" % sample)
            elif r1.json == r2.json:
                matches += 1
                print("%s: OK" % sample)
            else:
                differ += 1
                if compact:
                    print("%s: differ" % sample)

        if not compact:
            for sample, n1, r1, n2, r2 in generated_files:
                if r1.json != r2.json:
                    output = runez.run("diff", "-br", "-U1", n1, n2, fatal=None, include_error=True)
                    print("========  %s  ========" % sample)
                    print(output)
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
        print("Moving %s -> %s" % (relative_sample_path(source, base=PROJECT_FOLDER), relative_sample_path(dest, base=PROJECT_FOLDER)))
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
        sys.exit("No folder %s" % relative_sample_path(dest, base=PROJECT_FOLDER))
    move(sample.path, dest, sample.basename, ".yml")
    move(sample.expected_path, dest, sample.basename, ".json", subfolder="_expected")


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
@implementations_option(count=1, default="zyaml")
@samples_arg()
def refresh(stacktrace, implementations, samples):
    """Refresh expected json for each sample"""
    for root, dirs, files in os.walk(SAMPLE_FOLDER):
        if root.endswith("_expected"):
            for fname in files:
                ypath = os.path.dirname(root)
                ypath = os.path.join(ypath, fname.replace(".json", ".yml"))
                if not os.path.isfile(ypath):
                    # Delete _expected json files for yml files that have been moved
                    jpath = os.path.join(root, fname)
                    print("Deleting %s" % relative_sample_path(jpath))
                    os.unlink(jpath)

    for sample in samples:
        sample.refresh(impl=implementations.selected[0], stacktrace=stacktrace)


@main.command()
@stacktrace_option()
@implementations_option(default="raw,zyaml,ruamel")
@samples_arg(default="misc.yml")
def show(stacktrace, implementations, samples):
    """Show deserialized yaml objects as json"""
    for sample in samples:
        print("========  %s  ========" % sample)
        assert isinstance(implementations, ImplementationCollection)
        for impl in implementations:
            assert isinstance(impl, YmlImplementation)
            result = impl.load(sample, stacktrace=stacktrace)
            if result.error:
                rep = "Error: %s\n" % result.error
                implementations.track_result_combination(impl, "error")
            else:
                rep = impl.json_representation(result)
                implementations.track_result_combination(impl, rep)
            print("--------  %s  --------" % impl)
            print(rep)
        if implementations.combinations:
            combinations = ["/".join(x) for x in implementations.combinations]
            fmt = "-- %%%ss %%s" % max(len(s) for s in combinations)
            for names, values in implementations.combinations.items():
                print(fmt % ("/".join(names), "matches" if len(values) == 1 else "differ"))
            print()


@main.command()
@stacktrace_option()
@implementations_option(default="zyaml,pyyaml_base")
@samples_arg(default="misc.yml")
def tokens(stacktrace, implementations, samples):
    """Refresh expected json for each sample"""
    for sample in samples:
        print("========  %s  ========" % sample)
        for impl in implementations:
            print("--------  %s  --------" % impl)
            for t in impl.tokens(sample, stacktrace=stacktrace):
                print(t)
            print()


class Sample(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.basename = os.path.basename(self.path)
        self.basename, _, self.extension = self.basename.rpartition(os.path.extsep)
        self.folder = os.path.dirname(self.path)
        self.name = relative_sample_path(self.path)
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
                return None
        return self._expected

    def is_match(self, name):
        if name == "all":
            return True
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


class ParseResult(object):
    def __init__(self, impl, sample, data=None):
        self.impl = impl  # type: YmlImplementation
        self.sample = sample
        self.data = data
        self.exception = None
        self.error = None

    def __repr__(self):
        if self.error:
            return "Error: %s" % self.error
        return str(self.data)

    def set_exception(self, exc):
        self.exception = exc
        self.error = runez.shortened(runez.short(str(exc)), size=160)

    def json_payload(self):
        return {"_error": self.error} if self.error else self.data


class YmlImplementation(object):
    """Implementation of loading a yml file"""

    def __repr__(self):
        return self.name

    @property
    def name(self):
        return "_".join(s.lower() for s in re.findall("[A-Z][^A-Z]*", self.__class__.__name__.replace("Implementation", "")))

    def _load(self, stream):
        return []

    def tokens(self, sample, stacktrace=False):
        if stacktrace:
            with open(sample.path) as fh:
                for t in self._tokens(fh.read()):
                    yield t
            return

        try:
            with open(sample.path) as fh:
                for t in self._tokens(fh.read()):
                    yield t
        except Exception as e:
            yield "Error: %s" % e

    def _tokens(self, contents):
        raise Exception("not implemented")

    def _simplified(self, value):
        return zyaml.simplified(value)

    def load_stream(self, contents):
        data = self._load(contents)
        if data is not None and inspect.isgenerator(data):
            data = list(data)
        return self._simplified(data)

    def load_path(self, path):
        with open(path) as fh:
            return self.load_stream(fh)

    def load(self, sample, stacktrace=True):
        """
        :param Sample sample: Sample to load
        :param bool stacktrace: If True, don't catch parsing exceptions
        :return ParseResult: Parsed sample
        """
        if stacktrace:
            return ParseResult(self, sample, self.load_path(sample.path))

        result = ParseResult(self, sample)
        try:
            result.data = self.load_path(sample.path)
        except Exception as e:
            result.set_exception(e)
        return result

    def json_representation(self, result, stringify=zyaml.decode):
        try:
            payload = result.json_payload()
            payload = json_sanitized(payload, stringify=stringify)
            return "%s\n" % json.dumps(payload, sort_keys=True, indent=2)
        except Exception:
            print("Failed to json serialize %s" % result.sample)
            raise


class RawImplementation(YmlImplementation):
    def _load(self, stream):
        return stream.read()

    def json_representation(self, result, stringify=zyaml.decode):
        if result.error:
            return str(result)
        return result.data


class ZyamlImplementation(YmlImplementation):
    def _load(self, stream):
        return zyaml.load(stream)

    def _tokens(self, stream):
        return zyaml.Scanner(stream)

    def _simplified(self, value):
        return value


def ruamel_passthrough_tags(loader, tag, node):
    name = node.__class__.__name__
    if "Seq" in name:
        result = []
        for v in node.value:
            result.append(ruamel_passthrough_tags(loader, tag, v))
        return result
    if "Map" in name:
        result = {}
        for k, v in node.value:
            k = ruamel_passthrough_tags(loader, tag, k)
            v = ruamel_passthrough_tags(loader, tag, v)
            result[k] = v
        return result
    return zyaml.default_marshal(node.value)


class RuamelImplementation(YmlImplementation):
    def _load(self, stream):
        y = ruamel.yaml.YAML(typ="safe")
        ruamel.yaml.add_multi_constructor('', ruamel_passthrough_tags, Loader=ruamel.yaml.SafeLoader)
        # y.constructor.yaml_constructors["tag:yaml.org,2002:timestamp"] = y.constructor.yaml_constructors["tag:yaml.org,2002:str"]
        return y.load_all(stream)


class PyyamlBaseImplementation(YmlImplementation):
    def _load(self, stream):
        return pyyaml.load_all(stream, Loader=pyyaml.BaseLoader)

    def _tokens(self, stream):
        yaml_loader = pyyaml.BaseLoader(stream)
        curr = yaml_loader.get_token()
        while curr is not None:
            yield curr
            curr = yaml_loader.get_token()


class PyyamlSafeImplementation(YmlImplementation):
    def _load(self, stream):
        return pyyaml.load_all(stream, Loader=pyyaml.SafeLoader)


class PyyamlFullImplementation(YmlImplementation):
    def _load(self, stream):
        return pyyaml.load_all(stream, Loader=pyyaml.FullLoader)


class PoyoImplementation(YmlImplementation):
    def _load(self, stream):
        return [poyo.parse_string(stream.read())]


class StrictImplementation(YmlImplementation):
    def _load(self, stream):
        return strictyaml.load(stream.read())


if __name__ == "__main__":
    main()
