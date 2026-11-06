import pytest

from cybervisual.network_camera.soap import duration


@pytest.mark.parametrize("value,seconds", [("P0D", 0), ("PT0S", 0), ("PT1M30S", 90),
                                          ("P1DT2H3M4.5S", 93784.5)])
def test_duration_accepts_xsd_client_serializations(value, seconds):
    assert duration(value) == seconds


@pytest.mark.parametrize("value", ["P", "PT", "P1DT", "P1M", "-PT1S", "nan"])
def test_duration_rejects_ambiguous_or_negative_values(value):
    with pytest.raises(ValueError):
        duration(value)
