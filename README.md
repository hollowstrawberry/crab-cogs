# 🦀 crab-cogs

This is an addon for [Red Discord Bot](https://github.com/Cog-Creators/Red-DiscordBot), with features that I developed for my own servers.

These require Red 3.5, which uses the newer Discord interaction features.

### Installation

To add one of these cogs to your instance of Red, send the following commands one by one (`[p]` is your prefix):
```
[p]load downloader
[p]repo add crab-cogs https://github.com/hollowstrawberry/crab-cogs
[p]cog install crab-cogs [cog name]
[p]load [cog name]
```

You may be prompted to respond with "I agree" after the second command.

# Utility cogs

These may prove the most useful to most people.

### 🎵 AudioSlash

Converts many Audio cog commands into slash commands. The fun part is it will autocomplete YouTube search results as well as available playlists. It will also offer convenient options such as making `bumpplay` a setting of `/play` and offering shuffle with `/playlist play`.

![demonstration](https://i.imgur.com/EDJybmH.png)

### 😶 EmojiSteal

Lets anyone steal emojis and stickers sent by other people, and lets moderators upload them to the current server instantly. Supports context menus. Specially useful if you're on mobile as the Discord app doesn't let you copy emoji links or upload stickers, but this cog has commands for those. Animated stickers are annoying but there's a workaround.

![demonstration](https://i.imgur.com/Mj4jbGo.png)

### 🎌 EasyTranslate

A simple and unobtrusive translation cog with support for context menus and autocomplete. Choose your primary language with `/setmylanguage` then right click any message to find the Translate button. Alternatively use `/translate` to send a message in a different language. Heavily modified version of the translate cog from ob13-cogs.

![demonstration](https://i.imgur.com/zlc5BVJ.gif)

# Game cogs

Interactive games for your users, with economy support. Only one game of each type may be active per channel, but it works in threads, and inactive games may be ended by any user. Chess and Checkers games persist after a bot restart.

### 🕹️ Minigames

Features **Connect 4** and **Tic-Tac-Toe**, which you can play against your friends or the bot itself. Configure payouts and let users bet against each other. The AI is simple and can be beaten with practice.

![demonstration](https://i.imgur.com/llfbOG6.png)

### ♟️ SimpleChess

Play Chess against your friends or the bot itself. Configure payouts and let users bet against each other. You can also make your bots play together. Uses [Sunfish](https://github.com/thomasahle/sunfish) as the chess engine (AI), which has an ELO of around 1900, but the difficulty can be lowered when using the slash command.

![demonstration](https://i.imgur.com/6IleFWa.png)

### 🔴 SimpleCheckers

Play Checkers/Draughts against your friends or the bot itself. Configure payouts and let users bet against each other. You can also make your bots play together. The only variant available right now is English Draughts (also known as American Checkers). Note that capturing pieces is mandatory in the rules of this game. The checkers AI used here is a simple minimax algorithm, but it may still pose a challenge to most people.

![demonstration](https://i.imgur.com/bhhBB5d.png)

# Other cogs

### 🎤 VoiceLog

Logs users joining and leaving voicechat, inside the text chat embedded in the voicechat channel itself. Finally gives a use to those things.

![demonstration](https://i.imgur.com/CAzmA9R.png)

### 🎐 ImageLog

Logs and stores deleted images in a designated moderation channel. Useful for moderating servers with image boards or similar.

**⚠️ Usage Warning:** Content saved by this method is NOT usable for reporting users to Discord. You also may be liable for keeping content that breaks Discord TOS.

### 📜 Logs

Developer cog that opens an interactive view of your bot's console output within Discord. Can also send the entire log file. These are sent to your DMs by default. Useful if you're not currently in a position to access the host machine.

### 🗣 TTS

Plays text to speech in voice chat, intended as an accessibility feature. Detects the language automatically. The voice cannot be changed for now. Unfortunately will override music if it is playing.

### 🟫 Minecraft

A guild owner may associate a specific Minecraft server to their Discord server. Based on a cog from Dav-Cogs. This has 3 main features:

* Users can check server status and online players without needing to open the game.
* Admins can execute commands remotely.
* Users can whitelist themselves. Then, if they leave the Discord server, they will automatically be removed from the Minecraft server's whitelist.

### ⛩ Booru

Grab images from Gelbooru that match specific tags. The slash command version features smart tag suggestions/autocompletion. It will also avoid sending the same image in the same channel twice until absolutely necessary (within 24 hours).

**⚠️ Usage Warning:** This cog is allowed to display NSFW material in channels marked as NSFW.

![demonstration](https://i.imgur.com/KxD7pKq.png)

### 🎲 Randomness

A couple fun hybrid commands involving random seeds, including:

* `donut` will give you a random dessert and keep track of your score. `donutset` will set a list of emojis to choose from, so you could technically alias this command as anything. [Some donut emojis here](https://imgur.com/a/9hW2RRf)  
* `rate` will give a unique rating from 1 to 10 to anything you ask. The bot won't change its mind!  
* `pp` will evaluate your pp size. You can't change it, just like real life.  

### 🖌️ Draw

A couple fun hybrid commands with image filters for you and your friends' avatars. Also includes an avatar command and an avatar context menu. May take a minute to install due to the image processing libraries (opencv and Pillow).

### ⏺ Autoreact

You can give a chance for the bot to copy someone else's reactions, making it seem more interactive in everyday conversations.

Another feature is for the bot owner to set regex patterns that will cause the bot to react with a specific emoji. You may be able to think of useful or funny uses for this.

**⚠️ Usage Warning:** Some regex patterns have the possibility of running infinitely, freezing the entire bot. Please research catastrophic backtracking. Only the bot owner can set regex patterns.

### 📢 GameAlert

Sends a configured message when a guild member starts playing a specific game or has been playing for some time. The purpose is to alert friends or just to be silly.

### 🖼 GPTimage

Connects to OpenAI's Dall-E 3 and newer models to generate images. Requires an api key and ongoing monetary cost. Configurable cooldown per user, with an option to add VIP users that skip the cooldown.

### 🖼 NovelAI

Connects to this AI anime generation service to generate images with novelai3. If you want it updated let me know. Most parameters are available, as well as img2img. Requires a subscription. Connects with ImageScanner and ImageLog.

**⚠️ Usage Warning:** This cog is capable of generating NSFW content. Be mindful.

### 📎 ImageScanner

Lets you view basic information about other people's images with a context menu. Its real purpose is to view AI image generation metadata (Stable Diffusion and NovelAI). Additionally it can scan all images sent in specified channels and put a magnifying glass reaction button on AI images; the bot will DM the results to the users who use the magnifying glass.
