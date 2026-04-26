import discord
from typing import List
from discord.ui import View

class EphemeralNavigationView(View):
    def __init__(self, timeout: int, pages: List[str], starting_pos: int):
        super().__init__(timeout=timeout)
        self.pages = pages
        if starting_pos < 0 or starting_pos >= len(pages):
            raise ValueError("invalid starting_pos")
        self.current = starting_pos

        self.button_start = discord.ui.Button(emoji="⏮️")
        self.button_start.callback = self.start
        self.button_left = discord.ui.Button(emoji="⬅️")
        self.button_left.callback = self.left
        self.button_left.disabled = True
        self.button_right = discord.ui.Button(emoji="➡️")
        self.button_right.callback = self.right
        self.button_end = discord.ui.Button(emoji="⏭️")
        self.button_end.callback = self.end

        if len(pages) > 2:
            self.add_item(self.button_start)
        if len(pages) > 1:
            self.add_item(self.button_left)
        if len(pages) > 1:
            self.add_item(self.button_right)
        if len(pages) > 2:
            self.add_item(self.button_end)
        self.update_buttons()

    def update_buttons(self):
        self.button_start.disabled = self.current == 0
        self.button_left.disabled = self.current == 0
        self.button_right.disabled = self.current == len(self.pages) - 1
        self.button_end.disabled = self.current == len(self.pages) - 1

    async def start(self, interaction: discord.Interaction):
        self.current = 0
        self.update_buttons()
        await interaction.response.edit_message(content=self.pages[self.current], view=self)

    async def left(self, interaction: discord.Interaction):
        if self.current > 0:
            self.current -= 1
        self.update_buttons()
        await interaction.response.edit_message(content=self.pages[self.current], view=self)

    async def right(self, interaction: discord.Interaction):
        if self.current < len(self.pages) - 1:
            self.current += 1
        self.update_buttons()
        await interaction.response.edit_message(content=self.pages[self.current], view=self)

    async def end(self, interaction: discord.Interaction):
        self.current = len(self.pages) - 1
        self.update_buttons()
        await interaction.response.edit_message(content=self.pages[self.current], view=self)
