import pytest

from framed.sources.icloud import ICloudError, album_token, base_url, partition, pick_derivative


def test_token_from_url_and_partition():
    token = album_token("https://www.icloud.com/sharedalbum/#B0a5oqs3qXyZ123")
    assert token == "B0a5oqs3qXyZ123"
    assert partition("A1abc") == 1
    assert partition("B0a5oqs3qXyZ123") == 0 * 62 + 36
    assert base_url("A5xyz").startswith("https://p05-sharedstreams.icloud.com/A5xyz/")
    assert base_url("A5xyz", "p42-sharedstreams.icloud.com").startswith("https://p42-")
    with pytest.raises(ICloudError):
        album_token("https://example.com/#Z123")


def test_pick_smallest_derivative_above_min_width():
    derivatives = {
        "342": {"width": 342, "height": 200, "checksum": "small"},
        "1024": {"width": 1024, "height": 600, "checksum": "mid"},
        "2049": {"width": 2049, "height": 1200, "checksum": "big"},
    }
    assert pick_derivative(derivatives, 256) == ("small", 342, 200)
    assert pick_derivative(derivatives, 500) == ("mid", 1024, 600)
    assert pick_derivative(derivatives, 5000) == ("big", 2049, 1200)
    assert pick_derivative({}, 256) is None
