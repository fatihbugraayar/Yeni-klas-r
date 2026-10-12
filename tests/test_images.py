import io
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from telegram_bot.services.face_censor import FaceCensor, censor_regions
from telegram_bot.services.image_service import BoundedBuffer, InvalidImage, MediaStore, split_grid


def png(array):
    with Image.fromarray(array) as image, io.BytesIO() as buffer:
        image.save(buffer, "PNG")
        return buffer.getvalue()


@pytest.mark.parametrize("grid", range(2, 9))
def test_grid_dimensions_transparency_and_order(grid):
    # The central square contains distinct cells; colored sidebars must be cropped away.
    side = grid * 100
    array = np.zeros((side, side + 200, 4), dtype=np.uint8)
    array[:, :100] = (255, 255, 255, 255)
    array[:, -100:] = (255, 255, 255, 255)
    for row in range(grid):
        for col in range(grid):
            array[row * 100 : (row + 1) * 100, 100 + col * 100 : 100 + (col + 1) * 100] = (
                row * 30,
                col * 30,
                120,
                128,
            )
    tiles = split_grid(png(array), grid)
    assert len(tiles) == grid * grid
    for index, data in enumerate(tiles):
        with Image.open(io.BytesIO(data)) as tile:
            assert tile.size == (100, 100)
            assert tile.convert("RGBA").getpixel((50, 50)) == (
                index // grid * 30,
                index % grid * 30,
                120,
                128,
            )


@pytest.mark.parametrize("mode", ["pixelate", "blur"])
def test_censorship_changes_only_bounding_box_and_preserves_alpha(mode):
    original = np.random.default_rng(4).integers(0, 256, (100, 120, 4), dtype=np.uint8)
    processed = censor_regions(original, [(20, 30, 40, 50)], mode)
    outside = np.ones((100, 120), dtype=bool)
    outside[30:80, 20:60] = False
    assert np.array_equal(processed[outside], original[outside])
    assert np.array_equal(processed[:, :, 3], original[:, :, 3])
    assert not np.array_equal(processed[30:80, 20:60, :3], original[30:80, 20:60, :3])


def test_actual_detector_reports_no_faces_for_blank_image():
    data = png(np.full((256, 256, 3), 255, dtype=np.uint8))
    assert FaceCensor().process(data, "blur", 100_000) is None


def test_decode_rejects_invalid_and_oversized_images():
    with pytest.raises(InvalidImage):
        split_grid(b"not an image", 2)
    with pytest.raises(InvalidImage):
        split_grid(png(np.zeros((100, 100, 4), dtype=np.uint8)), 2, max_pixels=9999)
    with pytest.raises(InvalidImage):
        split_grid(png(np.zeros((100, 100, 4), dtype=np.uint8)), 9)
    with BoundedBuffer(10) as buffer:
        buffer.write(b"1234567890")
        with pytest.raises(InvalidImage):
            buffer.write(b"x")


def test_media_store_rejects_path_traversal(tmp_path):
    store = MediaStore(tmp_path)
    with pytest.raises(ValueError):
        store.directory("../../other")
    with pytest.raises(ValueError):
        store.path("a" * 32, "../../secret")


def test_exif_orientation_applied_and_metadata_removed():
    with Image.new("RGB", (200, 100), "red") as image, io.BytesIO() as buffer:
        exif = Image.Exif()
        exif[274] = 6
        image.save(buffer, "JPEG", exif=exif)
        from telegram_bot.services.image_service import decode_image

        with decode_image(buffer.getvalue(), 30_000) as decoded:
            assert decoded.size == (100, 200)
        for data in split_grid(buffer.getvalue(), 2):
            with Image.open(io.BytesIO(data)) as tile:
                assert not tile.getexif()


@pytest.mark.parametrize("mode", ["pixelate", "blur"])
def test_face_pipeline_returns_lossless_original_size_document(mode, monkeypatch):
    original = np.random.default_rng(12).integers(0, 256, (120, 140, 4), dtype=np.uint8)
    original[:, :, 3] = 255
    monkeypatch.setattr(
        "telegram_bot.services.face_censor.load_detector",
        lambda: SimpleNamespace(
            detectMultiScale=lambda *args, **kwargs: np.array([[20, 30, 40, 50]])
        ),
    )
    result, count = FaceCensor().process(png(original), mode, 100_000)
    assert count == 1
    with Image.open(io.BytesIO(result)) as decoded:
        assert decoded.format == "PNG" and decoded.size == (140, 120)
        array = np.array(decoded)
        assert np.array_equal(array[:30], original[:30])
        assert not np.array_equal(array[30:80, 20:60], original[30:80, 20:60])
