# 🦀 crab-cogs

This is an addon for [Red Discord Bot](https://github.com/Cog-Creators/Red-DiscordBot), with features that I developed for my own servers.

These require Red 3.5, which uses the newer Discord interaction features.

### Installation

To add one of these cogs to your instance of Red, send the following commands one by one (`[p]` is your prefix):
```
[p]load downloader
[p]repo add crab-cogs https://github.com/orchidalloy/crab-cogs
[p]cog install crab-cogs [cog name]
[p]load [cog name]
```

You may be prompted to respond with "I agree" after the second command.

### 😶 EmojiSteal

Lets anyone steal emojis and stickers sent by other people, and lets moderators upload them to the current server instantly. Supports context menus. Specially useful if you're on mobile as the Discord app doesn't let you copy emoji links or upload stickers, but this cog has commands for those. Animated stickers are annoying but there's a workaround.

![demonstration](https://media.discordapp.net/attachments/541768631445618689/1103728807430590524/Screenshot_20230504-130350_Discord.png)

### 🎌 EasyTranslate

A simple and unobtrusive translation cog with support for context menus and autocomplete. Choose your primary language with `/setmylanguage` then right click any message to find the Translate button. Alternatively use `/translate` to send a message in a different language. Heavily modified version of the translate cog from ob13-cogs.

![demonstration](https://cdn.discordapp.com/attachments/541768631445618689/1103626125520928828/ezgif-1-204db4b118.gif)

### 🎤 VoiceLog

Logs users joining and leaving voicechat, inside the text chat embedded in the voicechat channel itself. Finally gives a use to those things.

![demonstration](https://media.discordapp.net/attachments/541768631445618689/1103627951934820412/Screenshot_20230504-062308_Discord.png)

### 🎐 ImageLog

Logs and stores deleted images in a designated moderation channel. Useful for moderating servers with image boards or similar.

**⚠️ Usage Warning:** You may or may not be liable for keeping content that breaks Discord TOS.

![demonstration](https://media.discordapp.net/attachments/541768631445618689/1103725009794510919/Screenshot_20230504-123424_Discord.png)

### 📜 Logs

Developer cog that opens an interactive view of your bot's console output within Discord. Can also send the entire log file. These are sent to your DMs by default. Useful if you're not currently in a position to access the host machine.

### ⏺ Autoreact

Lets you configure emoji reactions that will be added to any message containing text matching a regex. Can be useful or just for fun. Now also lets you make the bot copy other people's reactions randomly.  

![demonstration](https://media.discordapp.net/attachments/541768631445618689/1103721844072251423/Screenshot_20230504-123621_Discord.png)

### 🎲 Randomness

A couple fun hybrid commands involving random seeds, including:

* `donut` will give you a random dessert and keep track of your score. `donutset` will set a list of emojis to choose from, so you could technically alias this command as anything. [Some donut emojis here](https://imgur.com/a/9hW2RRf)  
* `rate` will give a unique rating from 1 to 10 to anything you ask. The bot won't change its mind!  
* `pp` will evaluate your pp size. You can't change it, just like real life.  

### 🖌️ Draw

A couple fun hybrid commands with image filters for you and your friends' avatars. Also includes an avatar context menu. May take a minute to install due to the image processing libraries (opencv and Pillow).

### 📎 ImageScanner

Lets you view basic information about other people's images with a context menu. Its real purpose is to view AI image generation metadata (Stable Diffusion). Additionally it can scan all images sent in specified channels and put a reaction button on AI images; the bot will DM the results to the users who react.

### 📢 GameAlert

Sends a configured message when a guild member starts playing a specific game or has been playing for some time. The purpose is to alert friends or just to be silly.

### 🧠 Simulator

The "big" cog of this repo, it is limited to 1 server with settings defined by the bot owner.

This used to be more fun before text generation AI became mainstream.

Designates a channel that will send automated messages mimicking your friends through Markov chains. They will have your friends' avatars and nicknames too! Inspired by /r/SubredditSimulator and similar concepts.

🧠 It will learn from new messages sent in configured channels, and only from users with the configured role. It will only support a single guild.

⚙ The bot owner must configure it with `[p]simulator set`, then they may manually feed past messages using `[p]simulator feed [days]`. This takes around 1 minute per 5,000 messages, so be patient! When the feeding is finished or interrupted, it will send the summary in the same channel.

🔄 While the simulator is running, a conversation will occur every so many minutes, during which comments will be sent every so many seconds. Trying to type in the output channel will delete the message and instead trigger a conversation.

👤 A user may permanently exclude themselves from their messages being read and analyzed by using the `[p]dontsimulateme` command. This will also delete all their data.

![demonstration](https://media.discordapp.net/attachments/541768631445618689/1031334469904384100/unknown.png)

**⚠️ Usage Warning:** This cog will store and analyze messages sent by participating users. The bot owner may also make the bot download large amounts of past messages, following Discord ratelimits. It will then store a model in memory whose approximate RAM usage is 60 MB per 100,000 messages analyzed. This data will be stored locally and won't be shared anywhere outside of the target server.
