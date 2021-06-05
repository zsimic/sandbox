import logging
import os
import sys

import click
import runez

from zyaml import load_path, tokens_from_path
from zyaml.marshal import decode


class TestSamples:

    SAMPLE_FOLDER = runez.SYS_INFO.tests_path("samples")
    K_DESERIALIZED = "json"
    K_TOKEN = "token"

    @classmethod
    def option(cls, default=None, count=None, **kwargs):
        def _callback(_ctx, _param, value):
            if not value:
                value = default

            if count == 1 and hasattr(value, "endswith") and not value.endswith("."):
                value += "."

            if not value:
                raise click.BadParameter("No samples specified")

            s = cls.get_samples(value)
            if not s:
                raise click.BadParameter("No samples match %s" % value)

            if count and count != len(s):
                raise click.BadParameter("Need exactly %s, filter yielded %s" % (runez.plural(count, "sample"), len(s)))

            if count == 1:
                return s[0]

            return s

        if count == 1:
            metavar = "SAMPLE"

        elif count:
            metavar = ",".join("SAMPLE%s" % (i + 1) for i in range(count))

        else:
            metavar = "SAMPLES..."

        kwargs.setdefault("metavar", metavar)
        name = "sample" if count == 1 else "samples"
        kwargs.setdefault("nargs", count if count and count >= 1 else -1)
        return click.argument(name, callback=_callback, **kwargs)

    @classmethod
    def get_samples(cls, sample_name):
        result = []
        for name in runez.flattened([sample_name], split=","):
            result.extend(cls.scan_samples(name))

        return sorted(result, key=lambda x: x.key)

    @classmethod
    def scan_samples(cls, sample_name):
        sample_name = sample_name.strip()
        if not sample_name:
            return

        if os.path.isfile(sample_name) or os.path.isabs(sample_name):
            yield Sample(sample_name)
            return

        folder = os.path.join(cls.SAMPLE_FOLDER, sample_name)
        if os.path.isdir(folder):
            sample_name = "all"

        else:
            folder = cls.SAMPLE_FOLDER

        for root, dirs, files in os.walk(folder):
            for dir_name in ignored_dirs(dirs):
                dirs.remove(dir_name)

            for fname in files:
                if fname.endswith(".yml"):
                    sample = Sample(os.path.join(root, fname))
                    if sample.is_match(sample_name):
                        yield sample

    @classmethod
    def clean_samples(cls, verbose=False):
        cleanable = []
        for root, dirs, files in os.walk(cls.SAMPLE_FOLDER):
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

        for root, dirs, files in os.walk(cls.SAMPLE_FOLDER):
            if not dirs and not files:
                cleanable.append(root)
                runez.delete(root, logger=logging.info)

        print("%s cleaned" % runez.plural(cleanable, "file"))

    @classmethod
    def move_sample_file(cls, sample, new_category, new_basename, kind=None):
        dest = os.path.join(cls.SAMPLE_FOLDER, new_category)
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
            if kind == TestSamples.K_TOKEN:
                tokens = tokens_from_path(self.path)
                actual = [str(t) for t in tokens]

            else:
                actual = load_path(self.path)
                actual = runez.serialize.json_sanitized(actual, stringify=decode, none_key="-null-")

        except Exception as e:
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
            kinds = (TestSamples.K_DESERIALIZED, TestSamples.K_TOKEN)

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
            kinds = (TestSamples.K_DESERIALIZED, TestSamples.K_TOKEN)

        for kind in kinds:
            if existing:
                expected = self.expected_content(kind)
                if expected is runez.UNSET:
                    continue

            actual = self.deserialized(kind)
            path = self.expected_path(kind)
            runez.save_json(actual, path, keep_none=True, logger=logging.info)


def ignored_dirs(names):
    return [name for name in names if name.startswith(".")]


def textual_diff(kind, actual, expected):
    actual_error = isinstance(actual, dict) and actual.get("_error") or None
    expected_error = isinstance(expected, dict) and expected.get("_error") or None
    if actual_error != expected_error:
        if actual_error:
            return diff_overview(kind, actual_error, expected_error, "deserialization failed")

        return diff_overview(kind, actual_error, expected_error, "deserialization did NOT yield expected error")

    if type(actual) != type(expected):
        return diff_overview(kind, type(actual), type(expected), "differing types")

    if kind == TestSamples.K_TOKEN:
        actual = "%s\n" % "\n".join(actual)
        expected = "%s\n" % "\n".join(expected)

    else:
        actual = runez.represented_json(actual, keep_none=True, none_key="-null-")
        expected = runez.represented_json(expected, keep_none=True, none_key="-null-")

    if actual != expected:
        with runez.TempFolder(dryrun=False):
            runez.write("actual", actual)
            runez.write("expected", expected)
            r = runez.run("diff", "-br", "-U1", "expected", "actual", fatal=None, dryrun=False)
            return formatted_diff(r.full_output)


def diff_overview(kind, actual, expected, message):
    report = ["[%s] %s" % (kind, message)]
    if actual is not None:
        report.append("actual: %s" % actual)

    if expected is not None:
        report.append("expected: %s" % expected)

    return "\n".join(report)


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
