import asyncio
import io
import re
import shutil
import time
import warnings
from pathlib import Path

from aiogram import Bot
from aiogram.types import Message
from PIL import Image, ImageOps, UnidentifiedImageError


class InvalidImage(ValueError):
    pass


class BoundedBuffer(io.BytesIO):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise InvalidImage("Upload exceeds byte limit")
        return super().write(data)


async def download_image(bot: Bot, message: Message, limit: int) -> bytes:
    media = message.document or (message.photo[-1] if message.photo else None)
    if media is None or (media.file_size and media.file_size > limit):
        raise InvalidImage("Missing or oversized image")
    with BoundedBuffer(limit) as buffer:
        await bot.download(media, destination=buffer)
        return buffer.getvalue()


def decode_image(data: bytes, max_pixels: int) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with io.BytesIO(data) as stream, Image.open(stream) as source:
                if source.format not in {"PNG", "WEBP", "JPEG"}:
                    raise InvalidImage("Unsupported image format")
                if getattr(source, "n_frames", 1) != 1:
                    raise InvalidImage("Animated images are not supported")
                if source.width * source.height > max_pixels:
                    raise InvalidImage("Image exceeds pixel limit")
                source.load()
                with ImageOps.exif_transpose(source) as oriented:
                    return oriented.convert("RGBA")
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidImage("Unable to decode image") from exc


def split_grid(data: bytes, grid: int, max_pixels: int = 16_000_000) -> list[bytes]:
    if grid not in range(2, 9):
        raise InvalidImage("Grid must be between 2 and 8")
    return _slice_grid(data, grid, 100, "WEBP", max_pixels)


def split_studio_grid(
    data: bytes, grid: int, output_type: str, max_pixels: int = 16_000_000
) -> list[bytes]:
    if grid not in range(1, 10):
        raise InvalidImage("Studio grid must be between 1 and 9")
    if output_type not in {"custom_emoji", "regular"}:
        raise InvalidImage("Unsupported studio output")
    size = 100 if output_type == "custom_emoji" else 512
    return _slice_grid(data, grid, size, "PNG", max_pixels)


def _encode_tile(tile: Image.Image, output_format: str) -> bytes:
    with io.BytesIO() as buffer:
        if output_format == "WEBP":
            tile.save(buffer, format="WEBP", lossless=True, method=6)
        else:
            tile.save(buffer, format="PNG", optimize=True)
        output = buffer.getvalue()
    if len(output) > 512 * 1024:
        # A detailed 512px RGBA PNG can exceed Telegram's static sticker byte limit.
        # Only those tiles use a reduced palette, including transparent colors.
        with (
            tile.quantize(colors=256, method=Image.Quantize.FASTOCTREE) as reduced,
            io.BytesIO() as buffer,
        ):
            reduced.save(buffer, format="PNG", optimize=True)
            output = buffer.getvalue()
        if len(output) > 512 * 1024:
            raise InvalidImage("Sticker exceeds byte limit")
    return output


def _slice_grid(
    data: bytes, grid: int, size: int, output_format: str, max_pixels: int
) -> list[bytes]:
    with decode_image(data, max_pixels) as image:
        side = min(image.size)
        if side < grid:
            raise InvalidImage("Image too small for grid")
        left, top = (image.width - side) // 2, (image.height - side) // 2
        with image.crop((left, top, left + side, top + side)) as square:
            tiles = []
            for row in range(grid):
                for col in range(grid):
                    bounds = (
                        col * side // grid,
                        row * side // grid,
                        (col + 1) * side // grid,
                        (row + 1) * side // grid,
                    )
                    with (
                        square.crop(bounds) as crop,
                        crop.resize((size, size), Image.Resampling.LANCZOS) as tile,
                    ):
                        tiles.append(_encode_tile(tile, output_format))
            return tiles


class MediaStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Invalid job ID")
        path = self.root / job_id
        if path.resolve().parent != self.root:
            raise ValueError("Media path outside root")
        return path

    def path(self, job_id: str, filename: str) -> Path:
        if not re.fullmatch(r"(?:tile_\d{2}\.(?:webp|png)|result\.png)", filename):
            raise ValueError("Invalid media filename")
        return self.directory(job_id) / filename

    def write(self, job_id: str, files: dict[str, bytes]):
        self.directory(job_id).mkdir(exist_ok=True)
        for name, data in files.items():
            self.path(job_id, name).write_bytes(data)

    def ready(self, job) -> bool:
        names = job.params.get("files", [])
        return bool(names) and all(self.path(job.id, name).is_file() for name in names)

    def remove(self, job_id: str):
        path = self.directory(job_id)
        if path.exists():
            shutil.rmtree(path)

    def aged_directories(self) -> list[str]:
        return [
            path.name
            for path in self.root.iterdir()
            if path.is_dir()
            and re.fullmatch(r"[a-f0-9]{32}", path.name)
            and time.time() - path.stat().st_mtime > 3600
        ]


class ImageService:
    def __init__(self, store: MediaStore, max_pixels: int, concurrency: int):
        self.store = store
        self.max_pixels = max_pixels
        self.slots = asyncio.Semaphore(concurrency)

    async def emoji(self, data: bytes, grid: int, job_id: str) -> dict:
        def prepare():
            tiles = split_grid(data, grid, self.max_pixels)
            files = {f"tile_{index:02d}.webp": tile for index, tile in enumerate(tiles)}
            self.store.write(job_id, files)
            return {"grid": grid, "files": list(files), "uploaded": []}

        async with self.slots:
            return await asyncio.to_thread(prepare)

    async def photo(self, data: bytes, mode: str, job_id: str, censor) -> dict | None:
        def prepare():
            result = censor.process(data, mode, self.max_pixels)
            if result is None:
                return None
            output, count = result
            if len(output) > 49_000_000:
                raise InvalidImage("Result exceeds document upload limit")
            self.store.write(job_id, {"result.png": output})
            return {"mode": mode, "files": ["result.png"], "faces": count}

        async with self.slots:
            return await asyncio.to_thread(prepare)

    async def studio(self, data: bytes, grid: int, output_type: str, job_id: str) -> dict:
        def prepare():
            tiles = split_studio_grid(data, grid, output_type, self.max_pixels)
            files = {f"tile_{index:02d}.png": tile for index, tile in enumerate(tiles)}
            self.store.write(job_id, files)
            return {
                "grid": grid,
                "output_type": output_type,
                "files": list(files),
                "uploaded": [],
            }

        async with self.slots:
            return await asyncio.to_thread(prepare)
