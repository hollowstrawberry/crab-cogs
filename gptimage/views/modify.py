import io
import discord
import discord.ui as ui

from gptimage.views.image import ImageView


class ModifyModal(ui.Modal):
    def __init__(self, parent_view: ImageView):
        super().__init__(title="Image Editing")
        self.parent_view = parent_view
        self.prompt_edit = ui.Label(
            text="Prompt",
            component=ui.TextInput(
                style=discord.TextStyle.long,
                min_length=3,
            )
        )
        self.add_item(self.prompt_edit)
        
    async def on_submit(self, interaction: discord.Interaction):
        assert self.parent_view.message and isinstance(self.prompt_edit.component, discord.ui.TextInput)        
        prompt = self.prompt_edit.component.value
        await interaction.response.defer(thinking=True)
        image = io.BytesIO()
        await self.parent_view.message.attachments[0].save(image)
        await self.parent_view.cog.imagine(interaction, self.parent_view.resolution, prompt, [image.getvalue()])
