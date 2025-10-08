import discord

from simplecheckers.base import BaseCheckersGame


class GameMoveModal(discord.ui.Modal, title="Checkers Move"):
    move = discord.ui.Label(text='Move', description="The piece you want to move and every jump after, separated by spaces. Example: 22 13 6", component=discord.ui.TextInput())

    def __init__(self, game: BaseCheckersGame, parent_interaction: discord.Interaction):
        super().__init__()
        self.game = game
        self.parent_interaction = parent_interaction

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.move.component, discord.ui.TextInput)
        move = self.move.component.value
        success, message = await self.game.move_user(move.strip())
        if not success:
            return await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.response.defer()

        await self.game.update_message(self.parent_interaction)


class GameView(discord.ui.View):
    def __init__(self, game: BaseCheckersGame):
        super().__init__(timeout=None)
        self.game = game
        self.move_button = discord.ui.Button(custom_id=f"simplecheckers {game.channel.id} move", emoji="♟️", label="Enter Move", style=discord.ButtonStyle.success)
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
        embed = discord.Embed(title="⛃ Checkers Rules", color=0xDD2E44)
        embed.description = "This variant of checkers, often known as English draughts or American checkers, has the following rules:"
        embed.description += "\n1. Players take turns moving their pieces diagonally forward."
        embed.description += "\n2. If you can jump and capture an opponent’s piece by jumping over it, you have to do it."
        embed.description += "\n3. You may also jump over multiple pieces in sequence in a single move."
        embed.description += "\n4. When a piece reaches the far side, it becomes a “king” and can move backwards and forwards."
        embed.description += "\n5. You win after capturing all your opponent's pieces or blocking all of them from moving."
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
