"""On-demand, private MOSS layout view. Shared verbatim by both cog repos."""

import asyncio
import io
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field

import discord
from PIL import Image, ImageDraw

from .types import MossLayout, MossRegion

PREVIEW_SIZE = 1024
MAX_PIXELS = 64_000_000
PAGE_SIZE = 25
COLORS = ("#22d3ee", "#fbbf24", "#f472b6", "#a3e635", "#c4b5fd", "#fb923c")


def display(value: str, limit: int) -> str:
    escaped = discord.utils.escape_markdown(discord.utils.escape_mentions(value))
    return escaped if len(escaped) <= limit else escaped[: limit - 1] + "…"


def render_overlay(data: bytes, layout: MossLayout) -> bytes:
    with Image.open(io.BytesIO(data)) as source:
        if source.width * source.height > MAX_PIXELS:
            raise ValueError("Image is too large for a layout preview.")
        source.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE))
        preview = source.convert("RGB")
    draw = ImageDraw.Draw(preview)
    width, height = preview.size
    for index, region in enumerate(layout.regions):
        if region.normalized is None:
            continue
        top, left, bottom, right = region.normalized
        coords = (
            round(left * (width - 1)),
            round(top * (height - 1)),
            round(right * (width - 1)),
            round(bottom * (height - 1)),
        )
        color = COLORS[index % len(COLORS)]
        draw.rectangle(coords, outline="black", width=5)
        draw.rectangle(coords, outline=color, width=3)
        label = str(index + 1)
        left_px, top_px, right_px, bottom_px = draw.textbbox((0, 0), label)
        badge = Image.new("RGB", (round(right_px - left_px) + 8, round(bottom_px - top_px) + 6), "black")
        ImageDraw.Draw(badge).text((4 - left_px, 3 - top_px), label, fill=color)
        badge_height = max(22, round(max(width, height) / 26))
        badge = badge.resize((round(badge.width * badge_height / badge.height), badge_height), Image.Resampling.LANCZOS)
        x = min(coords[0] + 4, max(0, width - badge.width))
        y = min(coords[1] + 4, max(0, height - badge.height))
        preview.paste(badge, (x, y))
    output = io.BytesIO()
    # No original metadata is written into this temporary display copy.
    preview.save(output, format="PNG")
    return output.getvalue()


@dataclass
class LayoutSource:
    layout: MossLayout
    attachment: discord.Attachment | None = None
    image_bytes: bytes | None = None
    spoiler: bool = False
    overlay: bytes | None = field(default=None, init=False)
    attempted: bool = field(default=False, init=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def preview(self) -> bytes | None:
        async with self.lock:
            if not self.attempted:
                self.attempted = True
                if any(r.normalized is not None for r in self.layout.regions):
                    try:
                        data = self.image_bytes
                        if data is None and self.attachment is not None:
                            data = await self.attachment.read()
                        if data is not None:
                            self.overlay = await asyncio.to_thread(render_overlay, data, self.layout)
                    except (discord.HTTPException, OSError, ValueError, Image.DecompressionBombError):
                        # The region descriptions and exports still work without an image.
                        pass
            return self.overlay


class RegionSelect(discord.ui.Select["LayoutView"]):
    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.select_region(interaction)


class ActionButton(discord.ui.Button["LayoutView"]):
    def __init__(self, label: str, emoji: str, action: Callable[[discord.Interaction], Awaitable[None]]):
        super().__init__(label=label, emoji=emoji)
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.action(interaction)


class LayoutView(discord.ui.LayoutView):
    def __init__(self, source: LayoutSource, owner_id: int, filename: str | None, timeout: float):
        super().__init__(timeout=timeout)
        self.source = source
        self.owner_id = owner_id
        self.filename = filename
        self.selected = 0
        self.message: discord.WebhookMessage | None = None
        self.selector = RegionSelect(placeholder="Select a region")
        self.previous = ActionButton("Previous regions", "⬅️", self.previous_page)
        self.next = ActionButton("Next regions", "➡️", self.next_page)
        self.export = ActionButton("Region text", "📄", self.export_region)
        self.refresh()

    @property
    def region(self) -> MossRegion | None:
        regions = self.source.layout.regions
        return regions[self.selected] if regions else None

    def refresh(self) -> None:
        self.clear_items()
        layout = self.source.layout
        container: discord.ui.Container[LayoutView] = discord.ui.Container(accent_color=discord.Color.teal())
        container.add_item(
            discord.ui.TextDisplay(
                "## MOSS · Scene & regions\n"
                "-# Saved prompt areas describe intended placement, not detected object boundaries."
            )
        )
        if self.filename:
            container.add_item(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(f"attachment://{self.filename}", spoiler=self.source.spoiler)
                )
            )
        else:
            container.add_item(
                discord.ui.TextDisplay("Layout preview unavailable. Saved descriptions are shown below.")
            )
        if layout.warnings:
            container.add_item(discord.ui.TextDisplay(display("\n".join(layout.warnings), 400)))
        region = self.region
        if region:
            start = self.selected // PAGE_SIZE * PAGE_SIZE
            self.selector.options = [
                discord.SelectOption(
                    label=display(f"{i + 1} · {r.label}", 100), value=str(i), default=i == self.selected
                )
                for i, r in enumerate(layout.regions[start : start + PAGE_SIZE], start)
            ]
            container.add_item(discord.ui.ActionRow(self.selector))
            body = f"### {self.selected + 1} · {display(region.label, 80)}\n"
            body += display(region.caption or "No description saved.", 2300)
            if region.text is not None:
                body += f"\n**Literal text**\n{display(region.text, 700)}"
            body += "\n-# Region text downloads the complete description and literal text."
            container.add_item(discord.ui.TextDisplay(body))
            controls: discord.ui.ActionRow[LayoutView] = discord.ui.ActionRow()
            if len(layout.regions) > PAGE_SIZE:
                self.previous.disabled = start == 0
                self.next.disabled = start + PAGE_SIZE >= len(layout.regions)
                controls.add_item(self.previous)
                controls.add_item(self.next)
            controls.add_item(self.export)
            container.add_item(controls)
        else:
            container.add_item(discord.ui.TextDisplay(display(layout.scene or "No regions saved.", 3000)))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Open your own image metadata view to use these controls.", ephemeral=True
        )
        return False

    async def update(self, interaction: discord.Interaction) -> None:
        self.refresh()
        # No attachment changes: the one overlay is retained, including its spoiler flag.
        await interaction.response.edit_message(view=self, allowed_mentions=discord.AllowedMentions.none())

    async def select_region(self, interaction: discord.Interaction) -> None:
        self.selected = int(self.selector.values[0])
        await self.update(interaction)

    async def previous_page(self, interaction: discord.Interaction) -> None:
        self.selected = max(0, (self.selected // PAGE_SIZE - 1) * PAGE_SIZE)
        await self.update(interaction)

    async def next_page(self, interaction: discord.Interaction) -> None:
        self.selected = min(len(self.source.layout.regions) - 1, (self.selected // PAGE_SIZE + 1) * PAGE_SIZE)
        await self.update(interaction)

    async def export_region(self, interaction: discord.Interaction) -> None:
        if self.region is None:
            return
        content = self.region.caption + ("\n" + self.region.text if self.region.text is not None else "")
        file = discord.File(io.BytesIO(content.encode()), filename=f"region_{self.selected + 1}.txt")
        try:
            await interaction.response.send_message(file=file, ephemeral=True)
        finally:
            file.close()

    async def on_timeout(self) -> None:
        for control in (self.selector, self.previous, self.next, self.export):
            control.disabled = True
        if self.message:
            with suppress(discord.HTTPException):
                await self.message.edit(view=self)


async def send_layout(interaction: discord.Interaction, source: LayoutSource, timeout: float) -> None:
    await interaction.response.defer(thinking=True, ephemeral=True)
    overlay = await source.preview()
    file = discord.File(io.BytesIO(overlay), filename="layout.png", spoiler=source.spoiler) if overlay else None
    view = LayoutView(source, interaction.user.id, file.filename if file else None, timeout)
    try:
        if file:
            view.message = await interaction.followup.send(
                view=view, file=file, ephemeral=True, allowed_mentions=discord.AllowedMentions.none(), wait=True
            )
        else:
            view.message = await interaction.followup.send(
                view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none(), wait=True
            )
    finally:
        if file:
            file.close()


def add_summary_fields(embed: discord.Embed, params: dict[str, object], layout: MossLayout) -> None:
    from . import summary_params

    # Reserve room for resource links/title/footer. Full metadata stays downloadable.
    budget = 4000
    for name, value in summary_params(params, layout).items():
        if len(embed.fields) >= 25 or budget < 100:
            break
        name = display(name, 256)
        value = display(str(value), min(1000, budget - len(name))) or "—"
        embed.add_field(name=name, value=value, inline="Prompt" not in name and "Scene" not in name)
        budget -= len(name) + len(value)
