# fluxer-py

A Python API wrapper for [Fluxer](https://fluxer.app). Build bots and interact with the Fluxer platform in a simple and elegant way.

## Quick example

A dead simple bot with a ping command:

```py
import fluxer

bot = fluxer.Bot(command_prefix="!", intents=fluxer.Intents.default())


@bot.event
async def on_ready():
    print(f"Bot is ready! Logged in as {bot.user.username}")


@bot.command()
async def ping(ctx):
    await ctx.reply("Pong!")


if __name__ == "__main__":
    TOKEN = "your_bot_token"
    bot.run(TOKEN)
```

## Getting started to contribute

You'll need [uv](https://docs.astral.sh/uv/) installed, then:

```sh
git clone https://github.com/your-username/fluxer-py.git
cd fluxer-py
uv sync --dev
```

That's it, you're sorted. Uv will handle the `.venv` and dependecies without conflicts, like a traditional package manager!
