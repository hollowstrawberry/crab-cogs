import discord
import discord.ui as ui

from gelbooru.image_view import ImageView


class EditModal(ui.Modal):
    def __init__(self, parent_view: ImageView, display_query: str):
        super().__init__(title="Search Booru Posts")
        self.booru = parent_view.booru
        self.query_edit = ui.Label(
            text="Tags",
            description="Tags contain underscores and are separated by spaces",
            component=ui.TextInput(
                style=discord.TextStyle.long,
                default=display_query,
                min_length=3
            )
        )
        self.add_item(self.query_edit)
        
    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.query_edit.component, discord.ui.TextInput)
        await self.booru(interaction, self.query_edit.component.value)
