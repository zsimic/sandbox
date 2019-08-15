import zyaml

from .conftest import json_sanitized


def test_samples(spec_samples):
    skipped = 0
    for sample in spec_samples:
        value = zyaml.load_path(sample.path)
        expected = sample.expected
        if expected is None:
            skipped += 1
        else:
            value = json_sanitized(value)
            assert value == expected
    assert skipped == 0, "Skipped %s tests, please refresh" % skipped
