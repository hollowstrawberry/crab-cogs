import discord

from easychess.base import BaseChessGame


class GameMoveModal(discord.ui.Modal, title="Chess Move"):
    move = discord.ui.Label(text='Move', description="A move in standard notations, such as Nc3 or b1c3", component=discord.ui.TextInput())

    def __init__(self, game: BaseChessGame):
        super().__init__()
        self.game = game

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.pong()
        assert isinstance(self.move.component, discord.ui.TextInput)
        success, message = self.game.move_user(self.move.component.value)
        if not success:
            return await interaction.response.send_message(message, ephemeral=True)
        await self.game.update_message()

        if self.game.member(self.game.board.turn).bot and not self.game.is_finished():
            await self.game.move_engine()
            await self.game.update_message()


class GameView(discord.ui.View):
    def __init__(self, game: BaseChessGame):
        super().__init__(timeout=None)
        self.game = game

    discord.ui.button(emoji="♟️", label="Enter Move", style=discord.ButtonStyle.success)
    async def move(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GameMoveModal(self.game))

    discord.ui.button(emoji="⬇️", label="Bump", style=discord.ButtonStyle.primary)
    async def bump(self, interaction: discord.Interaction):
        assert interaction.message
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        await interaction.response.pong()
        await self.game.update_message()
        
    discord.ui.button(emoji="🏳️", label="End", style=discord.ButtonStyle.danger)
    async def end(self, interaction: discord.Interaction):
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players and not interaction.channel.permissions_for(interaction.user).manage_messages:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        self.game.cancel(interaction.user)
        self.stop()
        await interaction.response.pong()
        await self.game.update_message()
