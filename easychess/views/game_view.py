import discord

from easychess.base import BaseChessGame


class GameMoveModal(discord.ui.Modal, title="Chess Move"):
    move = discord.ui.Label(text='Move', description="A move in standard notations, such as Nc3 or b1c3", component=discord.ui.TextInput())

    def __init__(self, game: BaseChessGame, parent_interaction: discord.Interaction):
        super().__init__()
        self.game = game
        self.parent_interaction = parent_interaction

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.move.component, discord.ui.TextInput)
        move = self.move.component.value
        success, message = self.game.move_user(move)
        if not success:
            return await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.response.defer()

        await self.game.update_message(self.parent_interaction)

        if self.game.member(self.game.board.turn).bot and not self.game.is_finished():
            await self.game.move_engine()
            await self.game.update_message(self.parent_interaction)


class GameView(discord.ui.View):
    def __init__(self, game: BaseChessGame):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(emoji="♟️", label="Enter Move", style=discord.ButtonStyle.success)
    async def move(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(GameMoveModal(self.game, interaction))

    @discord.ui.button(emoji="⬇️", label="Bump", style=discord.ButtonStyle.primary)
    async def bump(self, interaction: discord.Interaction, _):
        assert interaction.message
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        await self.game.update_message(interaction)
        
    @discord.ui.button(emoji="🏳️", label="Surrender", style=discord.ButtonStyle.danger)
    async def end(self, interaction: discord.Interaction, _):
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        self.game.cancel(interaction.user)
        self.stop()
        await self.game.update_message(interaction)
