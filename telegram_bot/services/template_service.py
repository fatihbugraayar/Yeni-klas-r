import asyncio
import io

from PIL import Image, ImageDraw, ImageFont


def draw_blueprint(grid: int) -> bytes:
    """Render a reference layout locally; no generator or network access is involved."""
    if grid not in range(1, 10):
        raise ValueError("Studio grid must be between 1 and 9")
    size = 1024
    label_font = ImageFont.load_default(size=22)
    number_font = ImageFont.load_default(size=max(24, 112 // grid))
    with Image.new("RGB", (size, size), "#fafafa") as image, io.BytesIO() as buffer:
        draw = ImageDraw.Draw(image)
        for y in range(0, size, 16):
            for x in range(0, size, 16):
                if (x // 16 + y // 16) % 2:
                    draw.rectangle((x, y, x + 15, y + 15), fill="#eeeeee")
        for index in range(1, grid):
            coordinate = index * size // grid
            for position in range(0, size, 18):
                end = min(position + 10, size - 1)
                draw.line((coordinate, position, coordinate, end), fill="#737b89", width=2)
                draw.line((position, coordinate, end, coordinate), fill="#737b89", width=2)
        for row in range(grid):
            for col in range(grid):
                x, y = col * size // grid, row * size // grid
                right, bottom = (col + 1) * size // grid, (row + 1) * size // grid
                label = f"{chr(65 + row)}{col + 1}"
                draw.rounded_rectangle((x + 9, y + 9, x + 65, y + 40), radius=6, fill="#ffffff")
                draw.text((x + 16, y + 12), label, font=label_font, fill="#545e70")
                number = str(row * grid + col + 1)
                box = draw.textbbox((0, 0), number, font=number_font)
                draw.text(
                    (
                        (x + right - box[2] + box[0]) // 2,
                        (y + bottom - box[3] + box[1]) // 2 - box[1],
                    ),
                    number,
                    font=number_font,
                    fill="#b3b7bf",
                )
        draw.rectangle((1, 1, size - 2, size - 2), outline="#737b89", width=3)
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


class TemplateService:
    def __init__(self, slots: asyncio.Semaphore):
        self.slots = slots

    async def generate(self, grid: int) -> bytes:
        async with self.slots:
            return await asyncio.to_thread(draw_blueprint, grid)
