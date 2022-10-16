# crab-cogs

My Red Discord bot modules.

## EmojiSteal

Steals emojis sent by other people and optionally uploads them to your own server.

![emojisteal](https://media.discordapp.net/attachments/541768631445618689/1031335118926782484/unknown.png)

## Simulator

Designates a channel that will send automated messages mimicking your friends using Markov chains. They will have your friends' avatars and nicknames too!
It will learn from messages from configured channels, and only from users with the configured role. Will only support a single guild set by the bot owner.

After configuring it with `[p]simulatorset`, you may manually feed past messages using `[p]feedsimulator [days]`. This takes around 1 minute per 5,000 messages, so be patient! When the feeding is finished or interrupted, it will send the summary in the same channel.

While the simulator is running, a conversation will occur every so many minutes, during which comments will be sent every so many seconds. Trying to type in the output channel will delete the message and trigger a conversation.

A user may permanently exclude themselves from their messages being read and analyzed by using the `[p]dontsimulateme` command. This will also delete all their data.

Inspired by /r/SubredditSimulator and similar concepts.

![simulator](https://media.discordapp.net/attachments/541768631445618689/1031334469904384100/unknown.png)

## Crab

A few fun commands, including:

* `rate` will give a random but unique rating to anything you ask  
* `pp` will give you a random but unique pp size  
* `draw` will take someone's avatar and apply a paint filter  
* `donut` will give you a donut. Your donut score is persistent. `donut set` will set a list of emojis to choose from (Images in the repo)
