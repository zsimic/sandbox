import json

from .conftest import json_sanitized, ZyamlImplementation


def test_samples(all_samples):
    skipped = 0
    impl = ZyamlImplementation()
    for sample in all_samples:
        result = impl.load(sample, stacktrace=False)
        payload = result.json_payload()
        expected = sample.expected
        payload = json_sanitized(payload)
        expected = json_sanitized(expected)
        if expected is None:
            skipped += 1
            continue
        # jsonify to avoid diffs on inf/nan floats
        jpayload = json.dumps(payload, sort_keys=True, indent=2)
        jexpected = json.dumps(expected, sort_keys=True, indent=2)
        assert jpayload == jexpected, "Failed sample %s" % sample

    assert skipped == 0, "Skipped %s tests, please refresh" % skipped
