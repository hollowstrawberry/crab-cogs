# crab-cogs

This is an addon for [Red bot](https://github.com/Cog-Creators/Red-DiscordBot) for Discord, with features that I developed for my own friend group (called crab).

### Installation

To add one of these cogs to your instance of Red, send the following commands one by one (`[p]` is your prefix):
```
[p]load downloader
[p]repo add crab-cogs https://github.com/orchidalloy/crab-cogs
[p]cog install crab-cogs [emojisteal/simulator/crab]
[p]load [emojisteal/simulator/crab]
```

You may be prompted to respond with "I agree" after the second line.

## 😶 EmojiSteal

Steals emojis sent by other people and optionally uploads them to your own server.

![emojisteal](https://media.discordapp.net/attachments/541768631445618689/1031335118926782484/unknown.png)

## 🧠 Simulator

Designates a channel that will send automated messages mimicking your friends using Markov chains. They will have your friends' avatars and nicknames too! Inspired by /r/SubredditSimulator and similar concepts.

🧠 It will learn from messages from configured channels, and only from users with the configured role. Will only support a single guild set by the bot owner.

⚙ After configuring it with `[p]simulator set`, you may manually feed past messages using `[p]feedsimulator [days]`. This takes around 1 minute per 5,000 messages, so be patient! When the feeding is finished or interrupted, it will send the summary in the same channel.

♻ While the simulator is running, a conversation will occur every so many minutes, during which comments will be sent every so many seconds. Trying to type in the output channel will delete the message and trigger a conversation.

⚠ A user may permanently exclude themselves from their messages being read and analyzed by using the `[p]dontsimulateme` command. This will also delete all their data.

![simulator](https://media.discordapp.net/attachments/541768631445618689/1031334469904384100/unknown.png)

### ⚠ Usage Warning

This cog will store and analyze messages sent by participating users. With your permission it may also download a lot of existing message data, following Discord ratelimits. It will then store a model in memory whose approximate RAM usage is 60 MB per 100,000 messages analyzed.

## 🦀 Crab

A few fun commands, including:

* `autoreact` lets you configure emojis that will be added to any message containing a specific text.  
* `donut` will give you a donut. Your donut score is persistent. `donut set` will set a list of emojis to choose from. [Some donut emojis here](https://imgur.com/a/9hW2RRf)  
* `rate` will give a random but unique rating to anything you ask  
* `pp` will give you a random but unique pp size  

## 🖌️ Draw

A couple fun image filters for your friends' avatars.