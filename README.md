# crab-cogs

This is an addon for [Red bot](https://github.com/Cog-Creators/Red-DiscordBot) for Discord, with features that I developed for my own friend group (called crab).

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

Designates a channel that will send automated messages mimicking your friends using Markov chains. They will have your friends' avatars and nicknames too! Inspired by /r/SubredditSimulator and similar concepts.

🧠 It will learn from new messages sent in configured channels, and only from users with the configured role. It will only support a single guild.

⚙ The bot owner must configure it with `[p]simulator set`, then they may manually feed past messages using `[p]simulator feed [days]`. This takes around 1 minute per 5,000 messages, so be patient! When the feeding is finished or interrupted, it will send the summary in the same channel.

🔄 While the simulator is running, a conversation will occur every so many minutes, during which comments will be sent every so many seconds. Trying to type in the output channel will delete the message and trigger a conversation.

👤 A user may permanently exclude themselves from their messages being read and analyzed by using the `[p]dontsimulateme` command. This will also delete all their data.

![simulator](https://media.discordapp.net/attachments/541768631445618689/1031334469904384100/unknown.png)

### ⚠ Usage Warning

This cog will store and analyze messages sent by participating users. The bot owner may also make the bot download large amounts of past messages, following Discord ratelimits. It will then store a model in memory whose approximate RAM usage is 60 MB per 100,000 messages analyzed. This data will be stored locally and won't be shared anywhere outside of the target server.

## 😶 EmojiSteal

Steals emojis sent by other people, and optionally uploads them to the current server. Supports context menu commands.

![emojisteal](https://media.discordapp.net/attachments/541768631445618689/1031335118926782484/unknown.png)

## 🎌 EasyTranslate

A simple translation cog with support for context menu commands. Based on the translate cog from ob13-cogs

![easy translate](https://cdn.discordapp.com/attachments/930472312317296760/1100933551148503091/Video.Guru_20230426_195111370.mp4)

## 📎 PromptInspector

Used for AI image generation metadata (stable diffusion). It can scan all images sent in specified channels and put a reaction button on valid ones. It also supports context menus.

## 🎤 VoiceLog

Logs users joining and leaving voicechat, inside the text chat embedded in the voicechat channel itself.

## ⏺ Autoreact

Lets you configure emojis that will be added to any message containing text matching a regex. Yes this is silly.  

![Autoreact with the word NOW](https://media.discordapp.net/attachments/541768631445618689/1031957798382207086/unknown.png)

## 📢 GameAlert

Sends a configured message when a user has been playing a specific game for some time. Yes this is silly.

## 🎲 Randomness

A few fun commands involving random seeds, including:

* `donut` will give you a random dessert and keep track of your score. `donut set` will set a list of emojis to choose from, so you could technically alias this command as anything. [Some donut emojis here](https://imgur.com/a/9hW2RRf)  
* `rate` will give a unique rating from 1 to 10 to anything you ask. The bot won't change its mind!  
* `pp` will evaluate your pp size. You can't change it, just like real life.  

## 🖌️ Draw

A couple fun image filters for your friends' avatars. May take a minute to install due to the image processing libraries (opencv and Pillow).
