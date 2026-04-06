import discord
import discord.ui as ui

from gelbooru.constants import TAG_BLACKLIST
from gelbooru.image_view import ImageView
from gelbooru.utils import is_nsfw


class EditModal(ui.Modal):
    def __init__(self, parent_view: ImageView):
        super().__init__(title="Search Booru Posts")
        self.booru = parent_view.booru
        query = parent_view.query

        for tag in TAG_BLACKLIST: # cleanup, gets added back later
            query = query.replace(f"-{tag}", "").strip()

        self.query_edit = ui.Label(
            text="Tags",
            component=ui.TextInput(
                style=discord.TextStyle.long,
                default=query,
                min_length=3
            )
        )
        self.add_item(self.query_edit)
        
    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.query_edit.component, discord.ui.TextInput)
        query = self.query_edit.component.value
        await interaction.response.defer(thinking=True)
        await self.booru(interaction, query)
