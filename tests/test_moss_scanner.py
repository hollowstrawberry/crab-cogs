"""Exercise scanner entry points, pagination and spoiler handling without Discord."""

import io
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from imagescanner.comfy import ComfyMetadataReader
from imagescanner.imagescanner import ImageScanner, moss_source
from imagescanner.imageview import ImageView
from imagescanner.utils import read_metadata
from PIL import Image, PngImagePlugin
from test_moss_metadata import graph, interaction, png, prompt


def author():
    member = MagicMock(spec=discord.Member)
    member.id, member.bot, member.color = 5, False, discord.Color.teal()
    member.display_avatar = NS(url="https://example.test/avatar.png")
    return member


def message(attachments):
    return NS(id=123, author=author(), jump_url="https://discord.com/channels/1/2/3", attachments=attachments)


def attachment(spoiler=False):
    return NS(
        filename="image.png",
        url="https://example.test/image.png",
        proxy_url=None,
        is_spoiler=lambda: spoiler,
        read=AsyncMock(return_value=png()),
    )


def cog():
    instance = object.__new__(ImageScanner)
    instance.civitai_emoji = ""
    instance.arcenciel_emoji = "AEC"
    instance.resolve_arcenciel_resources = AsyncMock(return_value=["resource"])
    instance.use_civitai = instance.use_arcenciel = False
    return instance


class ScannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_forge_png_extracts_layout_and_keeps_full_metadata(self):
        raw = prompt() + " <lora:demo:0.8>\nNegative prompt: low quality\nSteps: 24, Seed: 123, Size: 200x100"
        info = PngImagePlugin.PngInfo()
        info.add_text("parameters", raw)
        data = io.BytesIO()
        Image.new("RGB", (200, 100)).save(data, format="PNG", pnginfo=info)
        md = read_metadata(data.getvalue())
        source = moss_source(md, attachment(True), data.getvalue())
        self.assertEqual(source.layout.scene, "A winter scene")
        self.assertEqual(len(source.layout.regions), 2)
        self.assertEqual(source.layout.suffix, " <lora:demo:0.8>")
        self.assertEqual(md.raw, raw)
        self.assertTrue(source.spoiler)
        embed = await cog().prepare_embed(message([attachment(True)]), md, 0)
        self.assertEqual(embed.fields[0].name, "Scene · MOSS")
        self.assertNotIn("bbox_coord_space", str(embed.to_dict()))

    async def test_context_menu_mixed_images_and_lazy_layout(self):
        instance = cog()
        moss = ComfyMetadataReader.from_info({"prompt": json.dumps(graph())}, 200, 100)
        normal = ComfyMetadataReader.from_info({"prompt": json.dumps(graph("normal prompt"))}, 200, 100)
        attachments = [attachment(True), attachment()]
        msg = message(attachments)
        instance.image_cache = {123: ({0: moss, 1: normal}, {0: png(), 1: png()})}
        event = interaction()
        await instance.scanimage_app(event, msg)
        args = event.followup.send.call_args.kwargs
        view = args["view"]
        self.assertIsNone(args["embed"].thumbnail.url)
        self.assertEqual(view.layout_sources[0].layout.scene, "A winter scene")
        self.assertFalse(view.layout_sources[0].attempted)
        self.assertFalse(view.button_layout.disabled)
        await view.right(event)
        self.assertTrue(view.button_layout.disabled)
        self.assertEqual(event.response.edit_message.call_args.kwargs["embed"].thumbnail.url, attachments[1].url)
        await view.left(event)
        with patch("imagescanner.imageview.send_layout", new_callable=AsyncMock) as send:
            await view.view_layout(event)
            self.assertIs(send.call_args.args[1], view.layout_sources[0])
        view.stop()

    async def test_full_metadata_does_not_remove_layout_controls(self):
        md = ComfyMetadataReader.from_info({"prompt": json.dumps(graph())}, 200, 100)
        source = moss_source(md, attachment(True), png())
        view = ImageView([md.raw], [discord.Embed()], True, [source])
        event = interaction()
        event.message = NS(edit=AsyncMock())
        await view.view_full_parameters(event)
        self.assertFalse(view.is_finished())
        event.message.edit.assert_not_awaited()
        self.assertTrue(event.response.send_message.call_args.kwargs["ephemeral"])
        view.stop()

    async def test_reaction_dm_preserves_original_spoiler(self):
        instance = cog()
        md = ComfyMetadataReader.from_info({"prompt": json.dumps(graph())}, 200, 100)
        msg = message([attachment(True)])
        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)
        instance.bot = NS(user=NS(id=99), get_channel=lambda _: channel)
        instance.scan_channels = {12}
        instance.always_scan_generated_images = False
        instance.attach_images = True
        instance.image_cache = {123: ({0: md}, {0: png()})}
        instance.is_valid_red_message = AsyncMock(return_value=True)
        member = author()
        member.send = AsyncMock(return_value=NS(edit=AsyncMock()))
        event = NS(emoji=NS(name="🔎"), member=member, channel_id=12, message_id=123)
        await instance.on_raw_reaction_add(event)
        args = member.send.call_args.kwargs
        self.assertTrue(args["file"].spoiler)
        self.assertIsNone(args["embed"].image.url)
        self.assertTrue(args["view"].layout_sources[0].spoiler)
        args["view"].stop()
        args["file"].close()


if __name__ == "__main__":
    unittest.main()
