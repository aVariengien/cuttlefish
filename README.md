# 🦑 Cuttlefish Telegram Bot
![Cuttlefish Logo](./cuttlefish.png)


A Telegram bot to use Runware image generation API on mobile, built with Python and can be deployed on Fly.io. This project uses the `python-telegram-bot` library along with other dependencies to provide Telegram bot functionality.

## Prerequisites

- Python 3.11 or higher
- Docker
- Fly.io CLI (`flyctl`)
- A Telegram Bot Token (obtain from [@BotFather](https://t.me/BotFather))
- A [runware.ai](https://runware.ai/) API key

## Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/aVariengien/cuttlefish.git
   cd cuttlefish
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set up your environment variables:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token_here"
   export RUNWARE_API_KEY="your_runware_api_key"
   ```

4. Run the bot locally:
   ```bash
   python bot.py
   ```

## Deployment to Fly.io

1. Install the Fly.io CLI if you haven't already:
   ```bash
   # For macOS
   brew install flyctl
   ```

2. Login to Fly.io:
   ```bash
   flyctl auth login
   ```

3. Launch your app (first time only):
   ```bash
   flyctl launch
   ```
   - Choose a unique app name
   - Select a region close to your users
   - Choose to deploy now

4. Set your secrets:
   ```bash
   flyctl secrets set TELEGRAM_BOT_TOKEN="your_bot_token_here"
   flyctl secrets set RUNWARE_API_KEY="your_runware_api_key"
   ```

5. Deploy your application:
   ```bash
   flyctl deploy
   ```

6. Monitor your application:
   ```bash
   flyctl status
   flyctl logs
   ```

## Project Structure

- `bot.py` - Main bot application code
- `Dockerfile` - Container configuration
- `fly.toml` - Fly.io configuration
- `requirements.txt` - Python dependencies

## License

This project is licensed under the MIT License - see the LICENSE file for details.
