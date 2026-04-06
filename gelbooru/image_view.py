import logging
import discord
from typing import Optional, Union
from redbot.core.bot import Red

from gelbooru.base import BooruBase
from gelbooru.constants import EMBED_COLOR, EMBED_ICON, VIEW_TIMEOUT
from gelbooru.utils import display_query

log = logging.getLogger("red.holo-cogs.aimage")


class ImageView(discord.ui.View):
    def __init__(self,
                 cog: BooruBase,
                 channel: discord.abc.Messageable,
                 user: Union[discord.User, discord.Member],
                 query: str,
                 result_tags: Optional[str]
                ):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.bot: Red = cog.bot
        self.config = cog.config
        self.channel = channel
        self.og_user = user
        self.query = query
        self.tags = result_tags or "(none)"
        self.booru = cog.booru
        self.message: Optional[discord.Message] = None
        self.image_url: Optional[str] = None

        self.button_caption = discord.ui.Button(emoji='🔎')
        self.button_caption.callback = self.get_caption
        self.button_reroll = discord.ui.Button(emoji="🔄")
        self.button_reroll.callback = self.reroll_image
        self.button_edit = discord.ui.Button(emoji='📝')
        self.button_edit.callback = self.edit_image
        self.button_delete = discord.ui.Button(emoji='🗑️')
        self.button_delete.callback = self.delete_image

        if result_tags is not None:
            self.add_item(self.button_caption)
            self.add_item(self.button_reroll)
        self.add_item(self.button_edit)
        self.add_item(self.button_delete)

    async def get_caption(self, interaction: discord.Interaction):
        embed = discord.Embed(color=EMBED_COLOR)
        embed.description = f"```{self.tags[:4000]}```"
        embed.set_author(name="Booru Post", icon_url=EMBED_ICON)
        embed.add_field(name="Query", value=f"`{display_query(self.query)}`", inline=False)
        if self.image_url:
            embed.set_thumbnail(url=self.image_url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def reroll_image(self, interaction: discord.Interaction):
        await self.booru(interaction, self.query)

    async def edit_image(self, interaction: discord.Interaction):
        from gelbooru.edit_modal import EditModal
        modal = EditModal(self)
        await interaction.response.send_modal(modal)

    async def delete_image(self, interaction: discord.Interaction):
        assert interaction.message
        if not (await self.check_if_can_delete(interaction)):
            content = ":warning: Only the requester and members with `Manage Messages` permission can delete this image!"
            return await interaction.response.send_message(content, ephemeral=True)
        
        await interaction.message.delete()
        self.stop()
        
        query = display_query(self.query)
        if interaction.user.id == self.og_user.id:
            content = f"{self.og_user.mention} deleted their requested image with query `{query}` and tags: ```{self.tags}```"
        else:
            content = f'{interaction.user.mention} deleted an image requested by {self.og_user.mention} with query `{query}` and tags: ```{self.tags}```'
        await interaction.response.send_message(content, allowed_mentions=discord.AllowedMentions.none(), ephemeral=True)

    async def check_if_can_delete(self, interaction: discord.Interaction):
        is_og_user = interaction.user.id == self.og_user.id

        assert interaction.guild and interaction.channel
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False
        can_delete = await self.bot.is_owner(member) or interaction.channel.permissions_for(member).manage_messages

        return is_og_user or can_delete

    async def on_timeout(self):
        await super().on_timeout()
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
