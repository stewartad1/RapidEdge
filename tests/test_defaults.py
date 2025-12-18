from app import services


def test_color_each_pierce_defaults_true():
    """Ensure the module-level default for per-pierce coloring is True."""
    assert services.COLOR_EACH_PIERCE is True
