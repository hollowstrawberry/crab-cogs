"""Focused parser/Discord payload tests, without a bot login or API calls."""

import asyncio
import io
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
from imagescanner.comfy import ComfyMetadataReader
from imagescanner.moss_metadata import MAX_REGIONS, from_params, read_layout, summary_params
from imagescanner.moss_metadata.view import LayoutSource, LayoutView, add_summary_fields, render_overlay, send_layout
from imagescanner.moss_metadata.workflow import resolve_moss_prompt
from PIL import Image


def prompt(items=None, **summary):
    return json.dumps(
        {
            "summary": {"caption": "A winter scene", "canvas": "single", "meta": ["illustration"], **summary},
            "items": items
            if items is not None
            else [
                {"label": "character", "caption": "A person on the left", "bbox": [-50, -100, 50, 0]},
                {
                    "label": "text",
                    "caption": "A sign on the right",
                    "text": 'Hello "{world}"\nMOSS',
                    "bbox": [-50, 0, 50, 100],
                },
            ],
            "bbox_coord_space": "abs_centralized",
            "bbox_format": "yxyx",
        }
    )


def graph(positive=None):
    return {
        "sampler": {"class_type": "KSampler", "inputs": {"positive": ["encode", 0], "negative": ["negative", 0]}},
        "encode": {
            "class_type": "ArcEnCielMossTextEncode",
            "inputs": {"text": positive if positive is not None else prompt()},
        },
        "negative": {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality"}},
    }


def png(size=(200, 100)):
    stream = io.BytesIO()
    Image.new("RGB", size, "#444444").save(stream, format="PNG")
    return stream.getvalue()


def interaction(user=5):
    return NS(
        user=NS(id=user),
        response=NS(defer=AsyncMock(), edit_message=AsyncMock(), send_message=AsyncMock()),
        followup=NS(send=AsyncMock(return_value=NS(edit=AsyncMock()))),
    )


class ParserTests(unittest.TestCase):
    def test_scene_regions_text_suffix_and_unmodified_input(self):
        raw = prompt() + " <lora:demo:0.8> additional words"
        params = {"Prompt": raw, "Size": "200x100", "Seed": 123}
        layout = from_params(params)
        self.assertEqual(layout.regions[0].normalized, (0, 0, 1, 0.5))
        self.assertEqual(layout.regions[1].normalized, (0, 0.5, 1, 1))
        self.assertEqual(layout.meta, ("illustration",))
        self.assertEqual(layout.regions[1].text, 'Hello "{world}"\nMOSS')
        self.assertEqual(layout.suffix, " <lora:demo:0.8> additional words")
        self.assertNotIn("bbox", str(summary_params(params, layout)))
        self.assertEqual(params["Prompt"], raw)
        self.assertEqual(summary_params(params, None), params)

    def test_invalid_and_clipped_boxes_keep_descriptions(self):
        boxes = [None, [0, 0, 1], [20, 20, 0, 30], [100, 100, 200, 200], [False, 0, 1, 1], [0, 0, float("inf"), 2]]
        for bbox in boxes:
            with self.subTest(bbox=bbox):
                result = read_layout(prompt([{"caption": "Keep me", "bbox": bbox}]), 100, 100)
                self.assertEqual(result.regions[0].caption, "Keep me")
                self.assertIsNone(result.regions[0].normalized)
                self.assertTrue(result.warnings)
        clipped = read_layout(prompt([{"bbox": [-100, -200, 100, 200]}]), 200, 100)
        self.assertEqual(clipped.regions[0].normalized, (0, 0, 1, 1))
        self.assertEqual(clipped.regions[0].bbox, (-100, -200, 100, 200))
        self.assertTrue(clipped.warnings)
        self.assertIsNone(read_layout(prompt(), None, 100).regions[0].normalized)
        self.assertIsNone(read_layout(prompt(canvas="multi"), 200, 100).regions[0].normalized)

    def test_unsupported_and_bounded_inputs(self):
        for value in ("normal prompt", "{broken", "{}", prompt().replace("yxyx", "xyxy"), "x" * 131073):
            self.assertIsNone(read_layout(value))
        self.assertIsNone(read_layout(prompt([{}] * (MAX_REGIONS + 1))))
        self.assertIsNone(read_layout(prompt([{"bbox": [0, 0, 10**400, 1]}]), 100, 100).regions[0].normalized)
        self.assertEqual(read_layout(prompt([])).regions, ())

    def test_connected_workflow_only(self):
        flow = graph()
        flow["unused"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt(caption="Wrong scene")}}
        self.assertEqual(resolve_moss_prompt(flow), prompt())
        flow["sampler2"] = {"class_type": "KSampler", "inputs": {"positive": ["unused", 0]}}
        self.assertIsNone(resolve_moss_prompt(flow))
        for value in (["missing", 0], ["encode", 0], ["encode", 1]):
            self.assertIsNone(resolve_moss_prompt(graph(value)))
        self.assertIsNone(resolve_moss_prompt(graph("ordinary text")))
        self.assertIsNone(resolve_moss_prompt({str(i): {} for i in range(4097)}))

    def test_editor_resolution_and_replacement(self):
        flow = graph(["replace", 0])
        flow.update(
            {
                "replace": {
                    "class_type": "StringReplace",
                    "inputs": {"string": ["layout", 0], "find": "snow", "replace": "rain"},
                },
                "layout": {
                    "class_type": "MOSSImageLayoutPrompt",
                    "inputs": {
                        "prompt": "snow",
                        "element": ["editor", 2],
                        "width": ["resolution", 0],
                        "height": ["resolution", 1],
                        "character_boxes": "1",
                    },
                },
                "resolution": {
                    "class_type": "ResolutionSelector",
                    "inputs": {"aspect_ratio": "1:1 (Square)", "megapixels": 1, "multiple": 8},
                },
                "editor": {
                    "class_type": "CreateBoundingBoxes",
                    "inputs": {
                        "width": 1024,
                        "height": 1024,
                        "editor_state": [
                            {"x": 0, "y": 0, "width": 512, "height": 1024, "metadata": {"desc": "A coat"}},
                            {
                                "x": 512,
                                "y": 0,
                                "width": 512,
                                "height": 1024,
                                "metadata": {"type": "text", "desc": "A sign", "text": "Hi"},
                            },
                        ],
                    },
                },
            }
        )
        layout = read_layout(resolve_moss_prompt(flow), 1024, 1024)
        self.assertEqual(layout.scene, "rain")
        self.assertEqual(layout.regions[0].label, "character")
        self.assertEqual(layout.regions[0].bbox, (-512, -512, 512, 0))
        self.assertEqual(layout.regions[1].text, "Hi")
        flow["editor"]["inputs"]["bboxes"] = ["unsupported", 0]
        self.assertIsNone(resolve_moss_prompt(flow))

    def test_ui_workflow_and_broken_links(self):
        flow = {
            "nodes": [
                {"id": 1, "type": "ArcEnCielMossTextEncode", "widgets_values": [prompt()]},
                {"id": 2, "type": "KSampler", "inputs": [{"name": "positive", "link": 1}]},
            ],
            "links": [[1, 1, 0, 2, 0, "CONDITIONING"]],
        }
        self.assertEqual(resolve_moss_prompt(flow), prompt())
        flow["nodes"][0]["inputs"] = [{"name": "text", "link": 999}]
        self.assertIsNone(resolve_moss_prompt(flow))

    def test_comfy_reader_retains_raw_and_machine_prompt(self):
        raw = json.dumps(graph())
        result = ComfyMetadataReader.from_info({"prompt": raw}, 200, 100)
        self.assertTrue(result.is_comfy)
        self.assertEqual(result.moss_prompt, prompt())
        self.assertEqual(result.as_dict()["Prompt"], prompt())
        self.assertEqual(result.raw, raw)
        self.assertEqual(result.negative_prompt, "low quality")
        ordinary = ComfyMetadataReader.from_info({"prompt": json.dumps(graph("normal prompt"))}, 200, 100)
        self.assertIsNone(ordinary.moss_prompt)
        self.assertEqual(ordinary.as_dict()["Prompt"], "normal prompt")

    def test_overlay_aspect_ratio_and_original_bytes(self):
        layout = read_layout(prompt(), 200, 100)
        for size in ((200, 100), (100, 200), (200, 200), (2000, 1000)):
            original = png(size)
            output = render_overlay(original, layout)
            with Image.open(io.BytesIO(output)) as image:
                self.assertAlmostEqual(image.width / image.height, size[0] / size[1])
                self.assertLessEqual(max(image.size), 1024)
                self.assertNotEqual(image.getpixel((0, 0)), (68, 68, 68))
            with Image.open(io.BytesIO(original)) as image:
                self.assertEqual(image.getpixel((0, 0)), (68, 68, 68))
        with self.assertRaises(OSError):
            render_overlay(b"broken", layout)

    def test_summary_discord_limits(self):
        raw = prompt(caption="*" * 10000)
        layout = read_layout(raw, 200, 100)
        embed = discord.Embed(description="links " * 250)
        add_summary_fields(embed, {"Prompt": raw, **{f"Param {i}": "x" * 2000 for i in range(30)}}, layout)
        self.assertLessEqual(len(embed), 6000)
        self.assertLessEqual(len(embed.fields), 25)
        self.assertTrue(all(len(field.value) <= 1024 for field in embed.fields))


class ViewTests(unittest.IsolatedAsyncioTestCase):
    def source(self, **kwargs):
        return LayoutSource(read_layout(prompt(), 200, 100), **kwargs)

    async def test_lazy_preview_cached_across_concurrent_clicks(self):
        source = self.source(attachment=NS(read=AsyncMock(return_value=png())))
        with patch("imagescanner.moss_metadata.view.render_overlay", wraps=render_overlay) as render:
            await asyncio.gather(source.preview(), source.preview())
            render.assert_called_once()
            source.attachment.read.assert_awaited_once()
        failed = self.source(image_bytes=b"invalid")
        self.assertIsNone(await failed.preview())

    async def test_private_spoiler_send(self):
        source = self.source(image_bytes=png(), spoiler=True)
        event = interaction()
        await send_layout(event, source, 60)
        event.response.defer.assert_awaited_once_with(thinking=True, ephemeral=True)
        args = event.followup.send.call_args.kwargs
        self.assertTrue(args["ephemeral"])
        self.assertTrue(args["file"].spoiler)
        self.assertIn('"spoiler": true', json.dumps(args["view"].to_components()))
        self.assertIn("attachment://SPOILER_layout.png", json.dumps(args["view"].to_components()))
        self.assertIsInstance(args["view"], discord.ui.LayoutView)
        args["view"].stop()

    async def test_selection_preserves_attachment_and_pagination(self):
        layout = read_layout(
            prompt([{"caption": f"Region {i}", "bbox": [-50, -100, 50, 100]} for i in range(30)]), 200, 100
        )
        view = LayoutView(LayoutSource(layout), 5, "layout.png", 60)
        self.assertEqual(len(view.selector.options), 25)
        event = interaction()
        await view.next.callback(event)
        self.assertEqual(view.selected, 25)
        self.assertEqual(len(view.selector.options), 5)
        self.assertTrue(view.next.disabled)
        self.assertNotIn("attachments", event.response.edit_message.call_args.kwargs)
        view.selector._values = ["27"]
        await view.selector.callback(event)
        self.assertEqual(view.selected, 27)
        await view.previous.callback(event)
        self.assertEqual(view.selected, 0)
        self.assertTrue(view.previous.disabled)
        self.assertFalse(await view.interaction_check(interaction(6)))
        self.assertTrue(await view.interaction_check(event))
        view.message = NS(edit=AsyncMock())
        await view.on_timeout()
        self.assertTrue(view.selector.disabled)
        view.stop()

    async def test_export_full_region_and_no_image_fallback(self):
        source = self.source()
        event = interaction()
        await send_layout(event, source, 60)
        args = event.followup.send.call_args.kwargs
        self.assertNotIn("file", args)
        view = args["view"]
        view.selected = 1
        received = []

        async def read_file(**kwargs):
            received.append(kwargs["file"].fp.read().decode())

        event.response.send_message.side_effect = read_file
        await view.export.callback(event)
        self.assertEqual(received, [source.layout.regions[1].caption + "\n" + source.layout.regions[1].text])
        view.stop()


if __name__ == "__main__":
    unittest.main()
