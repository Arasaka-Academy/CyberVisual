from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw
import pytest

from cybervisual.overlay import draw_overlay, encode_jpeg


@pytest.mark.parametrize("bitmap_font_api", [False, True])
def test_annotated_frame_remains_available_with_legacy_bitmap_font_api(monkeypatch, bitmap_font_api):
    if bitmap_font_api:
        def unsupported_bbox(self, xy, text, font=None):
            raise ValueError("Only supported for TrueType fonts")
        monkeypatch.setattr(ImageDraw.ImageDraw, "textbbox", unsupported_bbox)
        monkeypatch.setattr(ImageDraw.ImageDraw, "textsize", lambda self, text, font=None: (6 * len(text), 11), raising=False)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    output = draw_overlay(frame, [{"label": "person", "confidence": 0.9,
                                 "bbox": {"x1": 30, "y1": 40, "x2": 100, "y2": 100}}])
    assert output.shape == frame.shape
    assert np.any(output[40, 30:100])
    image = Image.open(BytesIO(encode_jpeg(output)))
    assert image.size == (160, 120)
    assert image.format == "JPEG"
