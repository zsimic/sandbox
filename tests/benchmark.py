# -*- encoding: utf-8 -*-
import timeit

import runez

from . import TestSettings


class BenchmarkedFunction(object):
    def __init__(self, name, function, iterations):
        self.name = name
        self.function = function
        self.iterations = iterations
        self.error = None
        self.seconds = None

    def __repr__(self):
        return self.report()

    def resolved_call(self):
        result = self.function()
        if isinstance(result, Exception):
            raise result

    def run(self):
        t = timeit.Timer(stmt=self.resolved_call)
        if TestSettings.stacktrace:
            self.seconds = t.timeit(self.iterations)
            return

        try:
            self.seconds = t.timeit(self.iterations)

        except Exception as e:
            self.error = e

    def report(self, fastest=None, indent=""):
        message = "%s%s: " % (indent, self.name)
        if self.error:
            return "%s%s" % (message, TestSettings.represented(self.error, size=-len(message)))

        if self.seconds is None:
            return "%s%s" % (message, runez.red("no result"))

        info = ""
        if fastest and self.seconds and fastest.seconds and self.seconds != fastest.seconds:
            info = runez.dim(" [x %.1f]" % (self.seconds / fastest.seconds))

        unit = u"μ"
        x = self.seconds / self.iterations * 1000000
        if x >= 999:
            x = x / 1000
            unit = "m"

        if x >= 999:
            x = x / 1000
            unit = "s"

        return "%s%s: %.3f %ss/i%s" % (indent, self.name, x, unit, info)


class BenchmarkRunner(object):
    def __init__(self, functions, target_name=None, iterations=100):
        self.benchmarks = []
        for name, func in functions.items():
            self.benchmarks.append(BenchmarkedFunction(name, func, iterations))

        self.target_name = target_name
        self.fastest = None

    def run(self, ):
        for bench in self.benchmarks:
            bench.run()
            if bench.seconds is not None:
                if self.fastest is None or self.fastest.seconds > bench.seconds:
                    self.fastest = bench

    def report(self):
        result = []
        indent = ""
        if self.target_name:
            indent = "  "
            result.append("%s:" % self.target_name)

        for bench in self.benchmarks:
            result.append(bench.report(fastest=self.fastest, indent=indent))

        return "\n".join(result)
