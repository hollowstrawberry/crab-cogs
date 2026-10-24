# MOSS image metadata

The **Image Info** context menu and **🔎** reaction DM shows the saved MOSS scene, region count and
usual generation parameters. **View Full** retains the complete original
metadata. **View layout** opens a private Components V2 view with numbered
bounding boxes and a region selector. **Region text** downloads the selected
region's complete caption and literal text.

- Requires Red 3.5.24 or newer (Components V2; verified with discord.py 2.7.1).
- The overlay is created on demand with Pillow, off the event loop, and cached
  for the lifetime of the metadata view. Selecting a region edits text only;
  it does not re-upload the picture or create a new message.
- Spoiler images remain spoilers in the layout gallery. Image proportions are
  preserved. The original attachment and generation payload are not changed.
- Boxes describe intended prompt placement, not detected object boundaries.
  Invalid positions, unknown sizes and unsupported canvases retain their text
  but do not acquire guessed boxes. Out-of-frame positions are clipped only
  for display. Original coordinates remain in the full metadata.
- Native MOSS JSON (including trailing LoRA/additional prompt text) is supported.
  Comfy layouts use bounded, static resolution of known nodes connected to the
  sampler's positive input. Unknown, broken or ambiguous graphs are not executed
  or guessed. Non-MOSS images keep their existing metadata view.
- Region menus paginate at Discord's 25-option limit. Long descriptions are
  shortened for display and remain complete in the text download / View Full.
- No LLM calls, tool-schema changes, API uploads or persistent caches are added.

The `moss_metadata` package is kept identical in `holo-cogs/arcenciel` and
`crab-cogs/imagescanner`. These are separate Red cog distributions; neither
requires installation of the other. Apply shared parser/view fixes and the
matching parser tests to both copies.

## Focused verification

With the cog's Red runtime/dependencies available:

```sh
python -m unittest discover -s tests -p 'test_moss*.py'
python -m mypy --strict --follow-imports=silent imagescanner/moss_metadata
python -m ruff check imagescanner/moss_metadata tests/test_moss*.py
```

Before enabling in a server, check one uploaded MOSS image via Image Info and via a 🔎 reaction DM, select a region, download
its text, and repeat with a spoiler image. Confirm the original message remains
unchanged and a conventional image still shows the existing parameters view.
