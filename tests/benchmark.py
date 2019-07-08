import re
import timeit
from functools import partial

from conftest import data_paths, load_poyo, load_pyyaml, load_ruamel, load_zyaml, relative_path


class BenchResults:
    def __init__(self):
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

    def wrapup(self):
        for name, seconds in self.seconds.items():
            info = "" if seconds == self.fastest else " [x %.1f]" % (seconds / self.fastest)
            self.outcome[name] = "%.3fs%s" % (seconds, info)


def bench_pyyaml(path):
    return load_pyyaml(path)


def bench_poyo(path):
    return load_poyo(path)


def bench_ruamel(path):
    return load_ruamel(path)


def bench_zyaml(path):
    return load_zyaml(path)


def run_bench(results, path, iterations, func):
    name = func.__name__
    try:
        t = timeit.Timer(stmt=partial(func, path))
        results.add(name, t.timeit(iterations))

    except Exception as e:
        results.add(name, None, message="failed %s" % e)


def run(iterations=100):
    for path in data_paths():
        print("%s:" % relative_path(path))
        results = BenchResults()
        run_bench(results, path, iterations, bench_zyaml)
        run_bench(results, path, iterations, bench_pyyaml)
        run_bench(results, path, iterations, bench_poyo)
        run_bench(results, path, iterations, bench_ruamel)
        results.wrapup()
        for name, outcome in sorted(results.outcome.items()):
            print("  %s: %s" % (name, outcome))
        print()


if __name__ == "__main__":
    run()
