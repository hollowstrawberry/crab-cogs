import re
import discord
import discord.ui as ui
from copy import deepcopy

from gptimage.views.image import ImageView


class ModifyModal(ui.Modal):
    def __init__(self, parent_view: ImageView):
        super().__init__(title="Image Generation")
        self.parent_view = parent_view
        self.prompt_edit = ui.Label(
            text="Prompt",
            component=ui.TextInput(
                style=discord.TextStyle.long,
                default=parent_view.prompt,
                min_length=3,
            )
        )
        self.add_item(self.prompt_edit)
        
    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.prompt_edit.component, discord.ui.TextInput)        
        prompt = self.prompt_edit.component.value
        await interaction.response.defer(thinking=True)
        await self.parent_view.cog.imagine(interaction, prompt, self.parent_view.resolution, self.parent_view.images)
