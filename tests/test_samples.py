import zyaml


def test_samples(samples):
    for sample in samples:
        value = zyaml.load_path(sample.path)
        assert value == sample.expected
