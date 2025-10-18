import time
import asyncio
from typing import Callable
import discord

from simplechess.base import BaseChessGame

MIN_TURN_TIME = 1.0  # seconds
NOT_PLAYING = "You're not playing this game!"


class GameMoveModal(discord.ui.Modal, title="Chess Move"):
    move = discord.ui.Label(text='Move', description="A move in standard notations, such as Nc3 or b1c3", component=discord.ui.TextInput())

    def __init__(self, game: BaseChessGame, parent_interaction: discord.Interaction, view_stop: Callable):
        super().__init__()
        self.game = game
        self.parent_interaction = parent_interaction
        self.view_stop = view_stop

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.move.component, discord.ui.TextInput)
        move = self.move.component.value
        success, message = await self.game.move_user(move)
        if not success:
            return await interaction.response.send_message(message, ephemeral=True)

        self.view_stop()
        await interaction.response.defer()
        await self.game.update_message(self.parent_interaction)

        if self.game.member(self.game.board.turn).bot and not self.game.is_finished():
            start_time = time.time()
            await self.game.move_engine()
            elapsed = time.time() - start_time
            if elapsed < MIN_TURN_TIME:
                await asyncio.sleep(MIN_TURN_TIME - elapsed)
            await self.game.update_message(self.parent_interaction)


class GameView(discord.ui.View):
    def __init__(self, game: BaseChessGame):
        super().__init__(timeout=None)
        self.game = game
        self.move_button = discord.ui.Button(custom_id=f"simplechess {game.channel.id} move", emoji="♟️", label="Enter Move", style=discord.ButtonStyle.success)
        self.bump_button = discord.ui.Button(custom_id=f"simplechess {game.channel.id} bump", emoji="⬇️", label="Bump", style=discord.ButtonStyle.primary)
        self.end_button = discord.ui.Button(custom_id=f"simplechess {game.channel.id} end", emoji="🏳️", label="Surrender", style=discord.ButtonStyle.danger)
        self.move_button.callback = self.move
        self.bump_button.callback = self.bump
        self.end_button.callback = self.end
        self.add_item(self.move_button)
        self.add_item(self.bump_button)
        self.add_item(self.end_button)

    async def move(self, interaction: discord.Interaction):
        if interaction.user not in self.game.players:
            return await interaction.response.send_message(NOT_PLAYING, ephemeral=True)
        if interaction.user != self.game.member(self.game.board.turn):
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)
        await interaction.response.send_modal(GameMoveModal(self.game, interaction, self.stop))

    async def bump(self, interaction: discord.Interaction):
        assert interaction.message
        if interaction.user not in self.game.players:
            return await interaction.response.send_message(NOT_PLAYING, ephemeral=True)
        self.stop()
        await self.game.update_message()

    async def end(self, interaction: discord.Interaction):
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message(NOT_PLAYING, ephemeral=True)
        self.stop()
        await self.game.cancel(interaction.user)
        await self.game.update_message()
