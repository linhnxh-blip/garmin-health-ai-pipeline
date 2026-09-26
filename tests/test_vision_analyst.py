import pytest
from PIL import Image
import io

from src.analytics.vision_analyst import analyze_meal_image

def test_analyze_meal_image_dummy_or_fallback(monkeypatch):
    # Create dummy 100x100 red image
    img = Image.new("RGB", (100, 100), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    res = analyze_meal_image(img_bytes, caption="Lẩu hải sản và 2 lon bia", timestamp="2026-09-19 19:30:00")
    assert isinstance(res, dict)
    assert "meal_type" in res
    assert "dishes" in res
    assert "total_calories" in res
    assert "short_summary" in res
