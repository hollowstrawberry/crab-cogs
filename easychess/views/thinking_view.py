import discord


class ThinkingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=0)

    @discord.ui.button(emoji="♟️", label="Thinking...", style=discord.ButtonStyle.success, disabled=True)
    async def move(self, _, __):
        pass
