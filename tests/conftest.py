import pytest

try:
    from . import loaders
except ImportError:
    import loaders


@pytest.fixture
def spec_samples():
    return loaders.Setup.get_samples("spec")
