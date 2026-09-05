from PIL import Image

from framed.font import GLYPH_H, GLYPH_W, GLYPHS, draw_centered, draw_text, fit_text, text_width


def test_every_glyph_is_five_by_seven():
    for ch, rows in GLYPHS.items():
        assert len(rows) == GLYPH_H, ch
        assert all(len(r) == GLYPH_W for r in rows), ch


def test_width_and_fit():
    assert text_width("ABC") == 17
    assert fit_text("WELCOME", 64) == ("WELCOME", 1)
    assert fit_text("ABCDEFGHIJK", 64) == ("ABCDEFGHIJK", 0)  # 11 chars fit only unspaced
    text, spacing = fit_text("ABCDEFGHIJKLMNOP", 64)
    assert spacing == 0 and text_width(text, 0) <= 64


def test_draw_lowercase_and_unknown_characters():
    img = Image.new("RGB", (64, 64))
    draw_text(img, "hi ☃", 0, 0, (255, 255, 255))
    ref = Image.new("RGB", (64, 64))
    draw_text(ref, "HI", 0, 0, (255, 255, 255))
    assert img.tobytes().count(b"\xff") == ref.tobytes().count(b"\xff")


def test_centered_scaled_text_stays_inside_panel():
    img = Image.new("RGB", (64, 64))
    draw_centered(img, "RAM", 20, (0, 255, 0), scale=2)
    px = img.load()
    assert any(px[x, 20] != (0, 0, 0) for x in range(64))
    assert all(px[x, 19] == (0, 0, 0) for x in range(64))
    assert all(px[x, 34] == (0, 0, 0) for x in range(64))
