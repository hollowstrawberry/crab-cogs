# crab-cogs

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

## 🧠 Simulator

The "big" cog of this repo, it is limited to 1 server with settings defined by the owner. The other cogs are more versatile.

Designates a channel that will send automated messages mimicking your friends through Markov chains. They will have your friends' avatars and nicknames too! Inspired by /r/SubredditSimulator and similar concepts.

🧠 It will learn from new messages sent in configured channels, and only from users with the configured role. It will only support a single guild.

⚙ The bot owner must configure it with `[p]simulator set`, then they may manually feed past messages using `[p]simulator feed [days]`. This takes around 1 minute per 5,000 messages, so be patient! When the feeding is finished or interrupted, it will send the summary in the same channel.

🔄 While the simulator is running, a conversation will occur every so many minutes, during which comments will be sent every so many seconds. Trying to type in the output channel will delete the message and trigger a conversation.

👤 A user may permanently exclude themselves from their messages being read and analyzed by using the `[p]dontsimulateme` command. This will also delete all their data.

![simulator](https://media.discordapp.net/attachments/541768631445618689/1031334469904384100/unknown.png)

**⚠️ Usage Warning:** This cog will store and analyze messages sent by participating users. The bot owner may also make the bot download large amounts of past messages, following Discord ratelimits. It will then store a model in memory whose approximate RAM usage is 60 MB per 100,000 messages analyzed. This data will be stored locally and won't be shared anywhere outside of the target server.

## 😶 EmojiSteal

Lets anyone steal emojis and stickers sent by other people, and lets moderators upload them to the current server instantly. Supports context menus. Specially useful if you're on mobile as the Discord app doesn't let you copy emoji links or upload stickers, but this cog has commands for those. Converting self-uploaded gifs to stickers is very difficult and not yet supported.

![demonstration](https://media.discordapp.net/attachments/541768631445618689/1103627039656923266/Screenshot_20230504-061921_Discord.png)

## 🎌 EasyTranslate

A simple translation cog with support for context menus and autocomplete. Heavily modified version of the translate cog from ob13-cogs.

![demonstration](https://cdn.discordapp.com/attachments/541768631445618689/1103626125520928828/ezgif-1-204db4b118.gif)

## 📎 ImageScanner

Lets you view information about other people's images with a context menu. It's only really useful for AI image generation metadata (Stable Diffusion). Additionally it can scan all images sent in specified channels and put a reaction button on AI images, and the bot will DM the results.

## 🎐 ImageLog

Logs and stores deleted images in a designated moderation channel. Useful for moderating servers with image boards or similar.

**⚠️ Usage Warning:** You may or may not be liable for keeping content that breaks Discord TOS.

## 🎤 VoiceLog

Logs users joining and leaving voicechat, inside the text chat embedded in the voicechat channel itself. Finally gives a use to those things.

![demonstration](https://media.discordapp.net/attachments/541768631445618689/1103627951934820412/Screenshot_20230504-062308_Discord.png)

## ⏺ Autoreact

Lets you configure emojis that will be added to any message containing text matching a regex. Yes this is silly.  

![Autoreact with the word NOW](https://media.discordapp.net/attachments/541768631445618689/1031957798382207086/unknown.png)

## 📢 GameAlert

Sends a configured message when a user has been playing a specific game for some time. Yes this is silly.

## 🎲 Randomness

A couple fun hybrid commands involving random seeds, including:

* `donut` will give you a random dessert and keep track of your score. `donut set` will set a list of emojis to choose from, so you could technically alias this command as anything. [Some donut emojis here](https://imgur.com/a/9hW2RRf)  
* `rate` will give a unique rating from 1 to 10 to anything you ask. The bot won't change its mind!  
* `pp` will evaluate your pp size. You can't change it, just like real life.  

## 🖌️ Draw

A couple fun hybrid commands with image filters for you and your friends' avatars. May take a minute to install due to the image processing libraries (opencv and Pillow).
