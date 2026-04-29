import asyncio
import discord
import discord.ui as ui
from io import BytesIO

from gptimage.base import GptImageBase
from gptimage.utils import normalize_image

class EditModal(ui.Modal):
    def __init__(self, cog: GptImageBase, message: discord.Message):
        super().__init__(title="Image Editing")
        self.cog = cog
        self.message = message
        self.prompt_edit = ui.Label(
            text="Prompt",
            component=ui.TextInput(
                style=discord.TextStyle.long,
                min_length=3,
            )
        )
        self.add_item(self.prompt_edit)

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.prompt_edit.component, discord.ui.TextInput)        
        prompt = self.prompt_edit.component.value
        await interaction.response.defer(thinking=True)
        fp = BytesIO()
        if not self.message.attachments:  # refresh interaction message
            self.message = await self.message.channel.fetch_message(self.message.id)
        await self.message.attachments[0].save(fp)
        image_bytes, resolution = await asyncio.to_thread(normalize_image, fp)
        await self.cog.imagine(interaction, resolution, prompt, [image_bytes])
