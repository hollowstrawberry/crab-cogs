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
        success, message = await self.game.move_user(move)
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
        self.move_button = discord.ui.Button(custom_id=f"easychess {game.channel.id} move", emoji="♟️", label="Enter Move", style=discord.ButtonStyle.success)
        self.bump_button = discord.ui.Button(custom_id=f"easychess {game.channel.id} bump", emoji="⬇️", label="Bump", style=discord.ButtonStyle.primary)
        self.end_button = discord.ui.Button(custom_id=f"easychess {game.channel.id} end", emoji="🏳️", label="Surrender", style=discord.ButtonStyle.danger)
        self.move_button.callback = self.move
        self.bump_button.callback = self.bump
        self.end_button.callback = self.end
        self.add_item(self.move_button)
        self.add_item(self.bump_button)
        self.add_item(self.end_button)

    async def move(self, interaction: discord.Interaction):
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        if interaction.user != self.game.member(self.game.board.turn):
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)
        await interaction.response.send_modal(GameMoveModal(self.game, interaction))

    async def bump(self, interaction: discord.Interaction):
        assert interaction.message
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        await self.game.update_message()

    async def end(self, interaction: discord.Interaction):
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        self.stop()
        await self.game.cancel(interaction.user)
        await self.game.update_message()
