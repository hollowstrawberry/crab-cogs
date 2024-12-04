from difflib import get_close_matches
from redbot.core import commands

from gptmemory.cogbase import GptMemoryCogBase


class GptMemoryCogCommands(GptMemoryCogBase):
    @commands.command()
    async def memory(self, ctx: commands.Context, *, name: str):
        """View a memory by name, for GPT"""
        if ctx.guild.id in self.memory:
            if name not in self.memory[ctx.guild.id]:
                matches = get_close_matches(name, self.memory[ctx.guild.id])
                if matches:
                    name = matches[0]
            if name in self.memory[ctx.guild.id]:
                return await ctx.send(f"`[Memory of {name}]`\n>>> {self.memory[ctx.guild.id][name]}")
        await ctx.send(f"No memory of {name}")
    
    @commands.command()
    async def memories(self, ctx: commands.Context):
        """View a list of memories, for GPT"""
        if ctx.guild.id in self.memory and self.memory[ctx.guild.id]:
            await ctx.send(", ".join(f"`{mem}`" for mem in self.memory[ctx.guild.id].keys()))
        else:
            await ctx.send("No memories...")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def deletememory(self, ctx: commands.Context, *, name):
        """Delete a memory, for GPT"""
        if ctx.guild.id in self.memory and name in self.memory[ctx.guild.id]:
            async with self.config.guild(ctx.guild).memory() as memory:
                del memory[name]
            del self.memory[ctx.guild.id][name]
            await ctx.send("✅")
        else:
            await ctx.send("A memory by that name doesn't exist.")
        
    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setmemory(self, ctx: commands.Context, name, *, content):
        """Overwrite a memory, for GPT"""
        async with self.config.guild(ctx.guild).memory() as memory:
            memory[name] = content
        if ctx.guild.id not in self.memory:
            self.memory[ctx.guild.id] = {}
        self.memory[ctx.guild.id][name] = content
        await ctx.send("✅")
