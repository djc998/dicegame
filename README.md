# Dice Game Bot 🎲

A powerful, feature-rich Telegram Bot designed to facilitate a customizable dice game for groups. The bot allows users to roll a combination of an "Action" and a "Subject", and then reply with photo/video/audio/text submissions based on the roll. Other users can then rate these submissions out of 10.

## Features

- **Multi-Group Support**: A single instance of the bot can be added to countless groups.
- **Ownership Model**: The first user to run `/start` in a group becomes the registered owner.
- **Customizable Dice**: Owners and admins can add or remove Actions and Subjects.
- **Monetization (Premium Tier)**: Supports Telegram Stars (XTR) payments for Group Licenses or global Account Licenses, unlocking premium features like unlimited game time and custom dice.
- **Direct Message Settings**: Owners can configure their groups, manage dice via Bulk Import/Export, and check stats privately via `/settings`.
- **Global Admin Dashboard**: A designated super-admin can view platform-wide stats and export a CSV of all groups.

## Commands

These are the commands supported by the bot. To ensure autocomplete works properly, register these with `@BotFather`:

```text
start - Start the bot and register as owner
settings - Configure the bot (Run in Private Message)
playdicegame - Start a new game
stopdicegame - End the current game early
roll - Roll the dice
listdice - View all custom actions and subjects
addaction - Add a new action (Premium)
removeaction - Remove an action (Premium)
addsubject - Add a new subject (Premium)
removesubject - Remove a subject (Premium)
upgrade - Unlock Premium features
botstats - View your bot statistics
```

## Setup & Installation

This project is fully containerized using Docker.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/djc998/dicegame.git
   cd dicegame
   ```

2. **Configure Environment Variables:**
   Create a `.env` file in the root directory and populate it with the following:
   ```env
   # Your Telegram Bot Token from @BotFather
   BOT_TOKEN=your_bot_token_here

   # Cost in Telegram Stars (XTR)
   GROUP_UPGRADE_COST=200
   ACCOUNT_UPGRADE_COST=1000

   # Optional: Bypass code to unlock premium without paying
   UPGRADE_BYPASS_CODE=your_secret_code

   # Your personal Telegram User ID for global admin stats
   GLOBAL_ADMIN_ID=your_id_here
   ```

3. **Run the Bot:**
   ```bash
   docker-compose up -d --build
   ```
   The database will be automatically created in the `/data` directory and persisted as a Docker volume.

## Tech Stack
- **Python 3.10**
- **python-telegram-bot (v20+)**
- **aiosqlite**
- **Docker & Docker Compose**
