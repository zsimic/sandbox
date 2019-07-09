def verify_sample(sample, benchmarks):
    for impl in benchmarks.available:
        value = impl.load_sanitized(sample.path, stringify=str)
        assert sample.name != "zyaml" or value is not None
        if value:
            assert value == sample.expected


def test_samples(samples, benchmarks):
    for sample in samples:
        verify_sample(sample, benchmarks)
