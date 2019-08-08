import zyaml


def test_samples(samples):
    skipped = 0
    for sample in samples:
        value = zyaml.load_path(sample.path)
        expected = sample.expected
        if expected is None:
            skipped += 1
        else:
            assert value == expected
    assert skipped == 0, "Skipped %s tests, please refresh" % skipped
