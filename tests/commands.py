import sys

import click

try:
    from . import loaders
except ImportError:
    import loaders


@loaders.main.command()
@loaders.Setup.implementations_option()
@loaders.Setup.samples_arg()
def match(implementations, samples):
    """Compare deserialization of 2 implementations"""
    if len(implementations) != 2:
        sys.exit("Need exactly 2 implementations to compare")

    for sample in samples:
        r1 = implementations[0].load(sample)
        r2 = implementations[1].load(sample)
        print("%s %s" % (r1.diff(r2), sample))


@loaders.main.command()
@loaders.Setup.samples_arg()
def samples(samples):
    """Show which samples match given filter"""
    print("\n".join(str(s) for s in samples))


@loaders.main.command()
@click.option("--stacktrace", help="Show stacktrace on failure")
@loaders.Setup.implementations_option()
@loaders.Setup.samples_arg(default="misc.yml")
def show(stacktrace, implementations, samples):
    """Show deserialized yaml objects as json"""
    for sample in samples:
        report = []
        vals = set()
        for impl in implementations:
            result = impl.load(sample, stacktrace=stacktrace)
            result.wrap = loaders.json_representation
            rep = str(result)
            vals.add(rep)
            report.append("-- %s:\n%s" % (impl, rep))
        print("==== %s (match: %s):" % (sample, len(vals) == 1))
        print("\n".join(report))
        print()


@loaders.main.command()
@loaders.Setup.samples_arg()
def refresh(samples):
    """Refresh expected json for each sample"""
    for sample in samples:
        sample.refresh()


@loaders.main.command()
@loaders.Setup.implementations_option(default="zyaml,pyyaml_base")
@loaders.Setup.samples_arg(default="misc.yml")
def tokens(implementations, samples):
    """Refresh expected json for each sample"""
    for sample in samples:
        print("==== %s:" % sample)
        for impl in implementations:
            print("\n-- %s tokens:" % impl)
            for t in impl.tokens(sample):
                print(t)
            print()


if __name__ == "__main__":
    loaders.main()
