import logging
import discord
from io import BytesIO
from base64 import b64encode, b64decode
from typing import Any, Awaitable, Callable, Optional
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red

from openai import AsyncOpenAI

log = logging.getLogger("red.crab-cogs.nanobanana")


def make_image_content(image: bytes) -> dict:
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{b64encode(image).decode()}"
        },
    }


class RemixModal(discord.ui.Modal):
    def __init__(self, generate: Callable[..., Awaitable[Any]], attachments: list[discord.Attachment]):
        super().__init__(title="Remix Image")
        self.generate = generate
        self.attachments = attachments
        self.prompt = discord.ui.Label(
            text="Prompt",
            description="What you want to change in the image.",
            component=discord.ui.TextInput(
                style=discord.TextStyle.long,
                default="",
                min_length=4
            )
        )
        self.add_item(self.prompt)
        
    async def on_submit(self, interaction: discord.Interaction):
        assert interaction.message and interaction.message.attachments and isinstance(self.prompt.component, discord.ui.TextInput)
        await interaction.response.defer(thinking=True)
        fp = [BytesIO() for _ in self.attachments]
        try:
            for i in range(len(self.attachments)):
                await self.attachments[i].save(fp[i], seek_begin=True)
            images = [b.read() for b in fp]
            await self.generate(interaction, self.prompt.component.value, images)
        except Exception:  # catch everything and show something to the user
            await interaction.followup.send("There was a problem generating your image. Contact the bot owner for more information.")
            log.exception("Remixing an image", exc_info=True)


class NanoBanana(commands.Cog):
    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.openrouter_client: AsyncOpenAI | None = None
        self.config = Config.get_conf(self, identifier=1947582011)
        self.config.register_global(**{
            "prompt": "Create an image following the user's prompt as closely as possible while also being creative.",
            "roles": [],
            "users": [],
        })
        self.remix_context_menu = app_commands.ContextMenu(name='Remix', type=discord.AppCommandType.message, callback=self.remix_app_command)
        self.bot.tree.add_command(self.remix_context_menu)

    async def cog_load(self):
        await self.initialize_openrouter_client()

    async def cog_unload(self):
        if self.openrouter_client:
            await self.openrouter_client.close()
        self.bot.tree.remove_command(self.remix_context_menu.name, type=self.remix_context_menu.type)

    async def initialize_openrouter_client(self):
        api_key = (await self.bot.get_shared_api_tokens("openrouter")).get("api_key")
        if not api_key:
            return
        self.openrouter_client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, _):
        if service_name == "openrouter":
            await self.initialize_openrouter_client()


    @app_commands.command(name="nanobanana")
    @app_commands.describe(prompt="What you want the AI to make.",
                           reference1="A possible input image for the AI to use.",
                           reference2="A possible input image for the AI to use.",
                           reference3="A possible input image for the AI to use.")
    async def nanobanana_app_command(self,
                                     interaction: discord.Interaction,
                                     prompt: str,
                                     reference1: Optional[discord.Attachment],
                                     reference2: Optional[discord.Attachment],
                                     reference3: Optional[discord.Attachment]):
        """Generate an image with nanobanana. Approved users only."""
        assert isinstance(interaction.user, discord.Member)

        user_ids = await self.config.users()
        role_ids = await self.config.roles()
        if interaction.user.id not in user_ids and all(interaction.user.get_role(rid) is None for rid in role_ids):
            return await interaction.response.send_message("You are not authorized by the bot owner to use this feature.", ephemeral=True)
        
        references = [ref for ref in [reference1, reference2, reference3] if ref is not None]
        for ref in references:
            if not ref.content_type or "image" not in ref.content_type:
                return await interaction.response.send_message("One of the references you uploaded is not an image.", ephemeral=True)
        
        await interaction.response.defer(thinking=True)

        fp = [BytesIO() for _ in references]
        for i in range(len(references)):
            await references[i].save(fp[i], seek_begin=True)
        images = [b.read() for b in fp]

        try:
            await self.generate_nanobanana(interaction, prompt, images)
        except Exception:  # catch everything and show something to the user
            await interaction.followup.send("There was a problem generating your image. Contact the bot owner for more information.")
            log.exception("Generating an image", exc_info=True)


    # context menu added in __init__
    async def remix_app_command(self, interaction: discord.Interaction, message: discord.Message):
        """Edits an image with nanobanana. Approved users only."""
        assert interaction.message
        assert isinstance(interaction.user, discord.Member)

        user_ids = await self.config.users()
        role_ids = await self.config.roles()
        if interaction.user.id not in user_ids and all(interaction.user.get_role(rid) is None for rid in role_ids):
            return await interaction.response.send_message("You are not authorized by the bot owner to use this feature.", ephemeral=True)

        attachments = [att for att in message.attachments if att.content_type and "image" in att.content_type]
        if not attachments:
            return await interaction.response.send_message("This message doesn't have an image to remix.", ephemeral=True)
        
        await interaction.response.send_modal(RemixModal(self.generate_nanobanana, attachments[:3]))


    async def generate_nanobanana(self, interaction: discord.Interaction, prompt: str, input_images: list[bytes]):
        if not self.openrouter_client:
            await self.initialize_openrouter_client()
        if not self.openrouter_client:
            return await interaction.followup.send("OpenRouter is not initialized in the bot. Contact the bot owner.", ephemeral=True)
        
        messages = [
            {
                "role": "system",
                "content": await self.config.prompt()
            },
        ]
        if input_images:
            image_contents = [make_image_content(img) for img in input_images]
            messages.append({
                "role": "user",
                "content": [{"type": "text", "text": prompt}, *image_contents],
            })
        else:
            messages.append({
                "role": "user",
                "content": prompt,
            })

        response = await self.openrouter_client.chat.completions.create(
            model="google/gemini-3-pro-image-preview",
            messages=messages,  # type: ignore
            extra_body={"modalities": ["image", "text"]}
        )

        response = response.choices[0].message
        if hasattr(response, "images"):
            image_base64 = response.images[0]['image_url']['url'].split(',')[1]  # type: ignore
            image = BytesIO(b64decode(image_base64))
            await interaction.followup.send(file=discord.File(image, filename=f"nanobanana_output_{interaction.id}.png"))
        else:
            await interaction.followup.send(f"`The remix was rejected.`")


    @commands.group(name="nanobananaset")  # type: ignore
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def nanobananaset(self, _: commands.Context):
        """Configuration settings for nanobanana."""
        pass

    @nanobananaset.command(name="system_prompt", aliases=["prompt"])
    async def command_system_prompt(self, ctx: commands.Context, *, prompt: Optional[str]):
        """Views or sets the system prompt for nanobanana."""
        if prompt:
            await self.config.prompt.set(prompt)
            await ctx.reply("New system prompt for nanobanana set.")
        else:
            prompt = await self.config.prompt()
            assert prompt
            await ctx.reply(f"The current system prompt for nanobanana is: ```\n{prompt.replace('```', '`')}```")


    @nanobananaset.group(name="roles", aliases=["role"])
    async def command_roles(self, _: commands.Context):
        """Manage allowed roles."""
        pass

    @command_roles.command(name="add")
    @commands.is_owner()
    async def command_roles_add(self, ctx: commands.Context, *, role: discord.Role):
        """Add a role to the allowed list."""
        assert ctx.guild
        async with self.config.roles() as roles:
            if role.id not in roles:
                roles.append(role.id)
                await ctx.reply(f"Added {role.name} to the allowed roles for nanobanana.")
            else:
                await ctx.reply("That role is already in the list.")

    @command_roles.command(name="remove")
    @commands.is_owner()
    async def command_roles_remove(self, ctx: commands.Context, *, role: discord.Role):
        """Remove a role from the allowed list."""
        assert ctx.guild
        async with self.config.roles() as roles:
            if role.id in roles:
                roles.remove(role.id)
                await ctx.reply(f"Removed {role.name} from the allowed roles for nanobanana.")
            else:
                await ctx.reply("That role was not in the list.")

    @command_roles.command(name="list")
    async def command_roles_list(self, ctx: commands.Context):
        """List all allowed roles."""
        assert ctx.guild
        roles_ids = await self.config.roles()
        if not roles_ids:
            return await ctx.reply("No roles are currently configured.")
        
        await ctx.reply(f"Allowed roles for nanobanana: {', '.join([f'<@&{rid}>' for rid in roles_ids])}", allowed_mentions=discord.AllowedMentions.none())

    @nanobananaset.group(name="users", aliases=["user"])
    async def command_users(self, ctx: commands.Context):
        """Manage allowed users."""
        pass

    @command_users.command(name="add")
    @commands.is_owner()
    async def command_users_add(self, ctx: commands.Context, *, user: discord.Member):
        """Add a user to the allowed list."""
        assert ctx.guild
        async with self.config.users() as users:
            if user.id not in users:
                users.append(user.id)
                await ctx.reply(f"Added {user.display_name} to the allowed users for nanobanana.")
            else:
                await ctx.reply("That user is already in the list.")

    @command_users.command(name="remove")
    @commands.is_owner()
    async def command_users_remove(self, ctx: commands.Context, *, user: discord.Member):
        """Remove a user from the allowed list."""
        assert ctx.guild
        async with self.config.users() as users:
            if user.id in users:
                users.remove(user.id)
                await ctx.reply(f"Removed {user.display_name} from the allowed users for nanobanana.")
            else:
                await ctx.reply("That user was not in the list.")

    @command_users.command(name="list")
    async def command_users_list(self, ctx: commands.Context):
        """List all allowed users."""
        assert ctx.guild
        user_ids = await self.config.users()
        if not user_ids:
            return await ctx.reply("No users are currently configured.")
        
        await ctx.reply(f"Allowed users for nanobanana (separate from allowed roles): {', '.join([f'<@{u}>' for u in user_ids])}", allowed_mentions=discord.AllowedMentions.none())
