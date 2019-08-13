"""
See https://github.com/zsimic/yaml for more info
"""

import re
import timeit
from functools import partial

try:
    from . import loaders
except ImportError:
    import loaders


@loaders.main.command()
@loaders.Setup.implementations_option()
@loaders.Setup.samples_arg()
def benchmark(implementations, samples):
    """Run parsing benchmarks"""
    for sample in samples:
        bench = SingleBenchmark(sample, implementations)
        bench.run()
        print(bench.report())


class SingleBenchmark:
    def __init__(self, sample, implementations):
        self.implementations = implementations
        self.sample = sample
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
        for impl in self.implementations:
            try:
                t = timeit.Timer(stmt=partial(impl.load, self.sample))
                self.add(impl.name, t.timeit(self.iterations))

            except Exception as e:
                self.add(impl.name, None, message="failed %s" % e)

        for name, seconds in self.seconds.items():
            info = "" if seconds == self.fastest else " [x %.1f]" % (seconds / self.fastest)
            self.outcome[name] = "%.3fs%s" % (seconds, info)

    def report(self):
        result = ["%s:" % self.sample]
        for name, outcome in sorted(self.outcome.items()):
            result.append("  %s: %s" % (name, outcome))
        return "\n".join(result)


if __name__ == "__main__":
    benchmark()
