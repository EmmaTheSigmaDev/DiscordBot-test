Ready-to-deploy Discord bot (Render)

This folder is set up to be deployed to Render with Root Directory = `bot`.

Quick steps for Render

1. In Render, create a new Web Service and connect your GitHub repo.
2. Set Root Directory to `bot`.
3. Start Command: `python bot.py`
4. Environment variables (on Render -> Environment -> Environment Variables):
   - `BOT_TOKEN` = your bot token (recommended)
   - Alternatively `DISCORD_TOKEN` will also be accepted.
5. Render will install dependencies from `requirements.txt` and run the Start Command.

Local development

1. Create a virtual environment (recommended):

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1  # PowerShell

2. Install requirements:

   pip install -r requirements.txt

3. Copy `.env.example` to `.env` and fill in your token:

   copy .env.example .env
   # Edit .env and add your token

4. Run locally:

   python bot.py

Notes

- Do NOT commit your `.env` file or bot token to version control.
- If you change the Root Directory in Render, update the setting to `bot` when you deploy.
- If the bot fails to start on Render, check the service logs for `Logged in as <BotName>` or login errors.
