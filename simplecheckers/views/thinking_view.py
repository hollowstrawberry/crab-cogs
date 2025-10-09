import discord
import draughts

from simplecheckers.base import BaseCheckersGame


class ThinkingView(discord.ui.View):
    def __init__(self, game: BaseCheckersGame):
        super().__init__(timeout=0)
        emoji = "🔴" if game.board.turn == draughts.WHITE else "⚫"
        button = discord.ui.Button(emoji=emoji, label="Thinking...", style=discord.ButtonStyle.success, disabled=True)
        button.callback = self.button_callback
        self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        pass