from .conftest import ZyamlImplementation


def test_samples(vanilla_samples):
    skipped = 0
    impl = ZyamlImplementation()
    for sample in vanilla_samples:
        result = impl.load(sample, stacktrace=False)
        payload = result.json_payload()
        expected = sample.expected
        if expected is None:
            skipped += 1
        else:
            assert payload == expected, "Failed sample %s" % sample
    assert skipped == 0, "Skipped %s tests, please refresh" % skipped
