import pytest
from PIL import Image

from framed.font import glyph
from framed.render import fit_image, greeting_frames, parse_color, text_frame


def test_parse_color():
    assert parse_color("#ff8000") == (255, 128, 0)
    assert parse_color([1, 2, 300]) == (1, 2, 255)
    assert parse_color(None, (9, 9, 9)) == (9, 9, 9)
    with pytest.raises(ValueError):
        parse_color("nope")


def test_fit_image_crops_to_square_panel():
    wide = Image.new("RGB", (300, 100), (10, 200, 30))
    out = fit_image(wide, saturation=1.2, contrast=1.1)
    assert out.size == (64, 64) and out.mode == "RGB"


def test_text_frame_and_greeting_shape():
    frame = text_frame(["NO", "PHOTOS"])
    assert frame.size == (64, 64)
    frames = greeting_frames([("ELIJAH", (255, 159, 28))])
    assert len(frames) == 16
    assert all(f.size == (64, 64) for f in frames)
    assert frames[0].tobytes() != frames[-1].tobytes()
    pair = greeting_frames([("ELIJAH", (255, 159, 28)), ("RAM", (76, 201, 240))])
    assert pair[-1].tobytes() != frames[-1].tobytes()
    assert glyph("&") != glyph(" ")
    assert len(greeting_frames([])) == 16
