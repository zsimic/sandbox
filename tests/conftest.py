import json
import os
import sys

import pytest

import zyaml

try:
    from . import loaders
except ImportError:
    import loaders


SAMPLE_FOLDER = os.path.join(os.path.dirname(__file__), "samples")
SPEC_FOLDER = os.path.join(SAMPLE_FOLDER, "spec")


@pytest.fixture
def spec_samples():
    return loaders.Setup.get_samples("spec")


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
        docs = loaders.json_sanitized(docs)
        print("-- %s:\n%s" % (name, json.dumps(docs, sort_keys=True, indent=2)))
        return docs

    except Exception as e:
        print("-- %s:\n%s" % (name, e))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        args = sys.argv[2:]

    else:
        command = "match"
        args = []

    if command == "refresh":
        for sample in loaders.Setup.get_samples("spec"):
            sample.refresh()
        sys.exit(0)

    if command == "match":
        for sample in loaders.Setup.get_samples(args, default=["spec", SAMPLE_FOLDER]):
            try:
                zdoc = zyaml.load_path(sample.path)
            except Exception:
                zdoc = None

            try:
                rdoc = loaders.load_ruamel(sample.path)
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
        print("\n".join(str(s) for s in loaders.Setup.get_samples(args)))
        sys.exit(0)

    if command == "print":
        for arg in args:
            arg = arg.replace("\\n", "\n") + "\n"
            zdoc = loaders.json_sanitized(zyaml.load_string(arg))
            print("-- zdoc:\n%s" % zdoc)
            rdoc = loaders.loaded_ruamel(arg)
            print("-- ruamel:\n%s" % rdoc)
        sys.exit(0)

    if command == "show":
        for sample in loaders.Setup.get_samples(args):
            print("==== %s:" % sample)
            zdoc = show_jsonified(zyaml.load_path, sample.path)
            rdoc = show_jsonified(loaders.load_ruamel, sample.path)
            print("\nmatch: %s" % (zdoc == rdoc))
        sys.exit(0)

    if command == "tokens":
        for sample in loaders.Setup.get_samples(args):
            print("==== %s:" % sample)
            with open(sample.path) as fh:
                ztokens = list(zyaml.scan_tokens(fh.read()))

            with open(sample.path) as fh:
                ytokens = list(loaders.yaml_tokens(fh.read()))

            print("\n-- zyaml tokens")
            print("\n".join(str(s) for s in ztokens))
            print("\n\n-- yaml tokens")
            print("\n".join(str(s) for s in ytokens))
            print("\n")
        sys.exit(0)

    sys.exit("Unknown command %s" % command)
