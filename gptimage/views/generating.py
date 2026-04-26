import discord
import discord.ui as ui


class GeneratingView(ui.View):
    def __init__(self, prompt: str, embed_color: discord.Color):
        super().__init__(timeout=600)
        self.prompt = prompt
        self.embed_color = embed_color
        self.button_inspect = discord.ui.Button(emoji='🔎')
        self.button_inspect.callback = self.inspect
        self.add_item(self.button_inspect)

    async def inspect(self, interaction: discord.Interaction):
        embed = discord.Embed(color=self.embed_color)
        embed.title = "Image Request"
        embed.description = f"```\n{self.prompt}\n```"
        await interaction.response.send_message(embed=embed, ephemeral=True)
