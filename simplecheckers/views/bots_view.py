import time
import asyncio
import discord
import draughts

from simplecheckers.base import BaseCheckersGame
from simplecheckers.views.thinking_view import ThinkingView

MIN_TURN_TIME = 1.5  # seconds


class BotsView(discord.ui.View):
    def __init__(self, game: BaseCheckersGame):
        super().__init__(timeout=None)
        self.game = game
        emoji = "🔴" if game.board.turn == draughts.WHITE else "⚫"
        self.move_button = discord.ui.Button(custom_id=f"simplecheckers {game.channel.id} move", emoji=emoji, label="Next Move", style=discord.ButtonStyle.success)
        self.bump_button = discord.ui.Button(custom_id=f"simplecheckers {game.channel.id} bump", emoji="⬇️", label="Bump", style=discord.ButtonStyle.primary)
        self.end_button = discord.ui.Button(custom_id=f"simplecheckers {game.channel.id} end", emoji="🏳️", label="End", style=discord.ButtonStyle.danger)
        self.move_button.callback = self.move
        self.bump_button.callback = self.bump
        self.end_button.callback = self.end
        self.add_item(self.move_button)
        self.add_item(self.bump_button)
        self.add_item(self.end_button)

    async def move(self, interaction: discord.Interaction):
        self.stop()
        await interaction.response.edit_message(view=ThinkingView(self.game))
        start_time = time.time()
        await self.game.move_engine()
        elapsed = time.time() - start_time
        if elapsed < MIN_TURN_TIME:
            await asyncio.sleep(MIN_TURN_TIME - elapsed)
        await self.game.update_message(interaction)

    async def bump(self, interaction: discord.Interaction):
        self.stop()
        await self.game.update_message()
        
    async def end(self, interaction: discord.Interaction):
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        self.stop()
        await self.game.cancel(interaction.user)
        await self.game.update_message()
