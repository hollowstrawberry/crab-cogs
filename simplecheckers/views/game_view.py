import discord
import draughts

from simplecheckers.base import BaseCheckersGame
from simplecheckers.constants import INSTRUCTIONS


class GameMoveModal(discord.ui.Modal, title="Checkers Move"):
    move = discord.ui.Label(text='Move', description="The piece you want to move and every jump after, separated by spaces. Example: 22 13 6", component=discord.ui.TextInput())

    def __init__(self, game: BaseCheckersGame, parent_interaction: discord.Interaction):
        super().__init__()
        self.game = game
        self.parent_interaction = parent_interaction

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.move.component, discord.ui.TextInput)
        move = self.move.component.value.replace(",", " ").replace("-", " ").replace("x", " ").strip()
        success, message = await self.game.move_user(move)
        if not success:
            return await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.response.defer()

        await self.game.update_message(self.parent_interaction)

        if self.game.member(self.game.board.turn).bot:
            await self.game.move_engine()
            await self.game.update_message(self.parent_interaction)


class GameView(discord.ui.View):
    def __init__(self, game: BaseCheckersGame):
        super().__init__(timeout=None)
        self.game = game
        emoji = "🔴" if game.board.turn == draughts.WHITE else "⚫"
        self.move_button = discord.ui.Button(custom_id=f"simplecheckers {game.channel.id} move", emoji=emoji, label="Enter Move", style=discord.ButtonStyle.success)
        self.help_button = discord.ui.Button(custom_id=f"simplecheckers {game.channel.id} help", emoji="❓", label="Instructions", style=discord.ButtonStyle.secondary)
        self.bump_button = discord.ui.Button(custom_id=f"simplecheckers {game.channel.id} bump", emoji="⬇️", label="Bump", style=discord.ButtonStyle.primary)
        self.end_button = discord.ui.Button(custom_id=f"simplecheckers {game.channel.id} end", emoji="🏳️", label="Surrender", style=discord.ButtonStyle.danger)
        self.move_button.callback = self.move
        self.help_button.callback = self.help
        self.bump_button.callback = self.bump
        self.end_button.callback = self.end
        self.add_item(self.move_button)
        self.add_item(self.help_button)
        self.add_item(self.bump_button)
        self.add_item(self.end_button)

    async def move(self, interaction: discord.Interaction):
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        if interaction.user != self.game.member(self.game.board.turn):
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)
        await interaction.response.send_modal(GameMoveModal(self.game, interaction))

    async def help(self, interaction: discord.Interaction):
        instructions = INSTRUCTIONS[self.game.board.variant]
        embed = discord.Embed(title="⛃ Checkers Rules", description=instructions, color=0xDD2E44)
        embed.add_field(name="Move notation", value="A move is separated by spaces, starting with the piece you want to move and listing every jump along its path." +
                        "\n__Examples:__ `12 16` (single move forward), `22 13 6` (capture two pieces)", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
