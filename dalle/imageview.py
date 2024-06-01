import re
import discord
from discord.ui import View


class ImageView(View):
    def __init__(self, cog, message: discord.Message, prompt: str, simple: bool):
        super().__init__(timeout=300)
        self.cog = cog
        self.prompt = prompt
        self.simple = simple
        self.message = message
        self.deleted = False

    @discord.ui.button(emoji="♻", style=discord.ButtonStyle.grey)
    async def recycle(self, ctx: discord.Interaction, btn: discord.Button):
        btn.disabled = True
        await ctx.message.edit(view=self)
        await self.cog.imagine(ctx=ctx,
                               prompt=self.prompt,
                               simple=self.simple)
        if not self.deleted and not self.is_finished():
            btn.disabled = False
            await ctx.message.edit(view=self)

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.grey)
    async def delete(self, ctx: discord.Interaction, _: discord.Button):
        if ctx.message.interaction:
            original_user_id = ctx.message.interaction.user.id
        elif m := re.search(r"([0-9]+)", ctx.message.content):
            original_user_id = int(m.group(1))
        else:
            original_user_id = 0
        if not ctx.guild or ctx.user.id == original_user_id or ctx.channel.permissions_for(ctx.user).manage_messages:
            self.deleted = True
            self.stop()
            imagelog = self.cog.bot.get_cog("ImageLog")
            if imagelog:
                imagelog.manual_deleted_by[ctx.message.id] = ctx.user.id
            await ctx.message.delete()
        else:
            await ctx.response.send_message("Only a moderator or the user who requested the image may delete it.", ephemeral=True)

    async def on_timeout(self) -> None:
        if self.message and not self.deleted:
            await self.message.edit(view=None)
