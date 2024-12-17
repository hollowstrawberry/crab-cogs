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

### 🎵 AudioSlash

Converts many Audio cog commands into slash commands. The fun part is it will autocomplete YouTube search results as well as available playlists. It will also offer convenient options such as making `bumpplay` a setting of `/play` and offering shuffle with `/playlist play`.

![demonstration](https://i.imgur.com/EDJybmH.png)

### 😶 EmojiSteal

Lets anyone steal emojis and stickers sent by other people, and lets moderators upload them to the current server instantly. Supports context menus. Specially useful if you're on mobile as the Discord app doesn't let you copy emoji links or upload stickers, but this cog has commands for those. Animated stickers are annoying but there's a workaround.

![demonstration](https://i.imgur.com/Mj4jbGo.png)

### 🎌 EasyTranslate

A simple and unobtrusive translation cog with support for context menus and autocomplete. Choose your primary language with `/setmylanguage` then right click any message to find the Translate button. Alternatively use `/translate` to send a message in a different language. Heavily modified version of the translate cog from ob13-cogs.

![demonstration](https://i.imgur.com/zlc5BVJ.gif)

### 🎤 VoiceLog

Logs users joining and leaving voicechat, inside the text chat embedded in the voicechat channel itself. Finally gives a use to those things.

![demonstration](https://i.imgur.com/CAzmA9R.png)

### 🎐 ImageLog

Logs and stores deleted images in a designated moderation channel. Useful for moderating servers with image boards or similar.

**⚠️ Usage Warning:** You may or may not be liable for keeping content that breaks Discord TOS.

![demonstration](https://i.imgur.com/i2glgOA.png)

### 📜 Logs

Developer cog that opens an interactive view of your bot's console output within Discord. Can also send the entire log file. These are sent to your DMs by default. Useful if you're not currently in a position to access the host machine.

### 🗣 TTS

PLays text to speech in voice chat. Detects the language automatically. The voice cannot be changed for now. Unfortunately will override music if it is playing.

### ⏺ Autoreact

Lets you configure emoji reactions that will be added to any message containing text matching a regex. Can be useful or just for fun. Now also lets you make the bot copy other people's reactions randomly.  

![demonstration](https://i.imgur.com/yQ7LJd2.png)

### ⛩ Booru

Grab images from Gelbooru based on tags. The slash command version features smart tag suggestions/autocompletion. It will also avoid sending the same image in the same channel twice until absolutely necessary (within 24 hours).

**⚠️ Usage Warning:** This cog is allowed to display NSFW material in channels marked as NSFW

![demonstration](https://i.imgur.com/KxD7pKq.png)

### 🎲 Randomness

A couple fun hybrid commands involving random seeds, including:

* `donut` will give you a random dessert and keep track of your score. `donutset` will set a list of emojis to choose from, so you could technically alias this command as anything. [Some donut emojis here](https://imgur.com/a/9hW2RRf)  
* `rate` will give a unique rating from 1 to 10 to anything you ask. The bot won't change its mind!  
* `pp` will evaluate your pp size. You can't change it, just like real life.  

### 🖌️ Draw

A couple fun hybrid commands with image filters for you and your friends' avatars. Also includes an avatar command and an avatar context menu. May take a minute to install due to the image processing libraries (opencv and Pillow).

### 🖼 NovelAI

Connects to this AI anime generation service to to generate images with the latest SDXL technology. Most parameters are available, as well as img2img. Requires a subscription. Connects with ImageScanner and ImageLog.

### 🖼 Dalle

Connects to OpenAI's Dall-E 3 to generate images. Requires an api key and ongoing costs.


**⚠️ Usage Warning:** This cog is capable of generating NSFW content. Be mindful.

### 📎 ImageScanner

Lets you view basic information about other people's images with a context menu. Its real purpose is to view AI image generation metadata (Stable Diffusion and NovelAI). Additionally it can scan all images sent in specified channels and put a magnifying glass reaction button on AI images; the bot will DM the results to the users who react.

### 📢 GameAlert

Sends a configured message when a guild member starts playing a specific game or has been playing for some time. The purpose is to alert friends or just to be silly.
