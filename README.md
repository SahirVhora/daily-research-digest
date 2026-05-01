# daily-research-digest

Daily AI, SAP & Science research digest delivered to Telegram via GitHub Actions.

Runs every day at 7:20 UTC (8:20 AM BST) and sends a single digest message covering:

- 🤖 AI Tools & Models (OpenAI, Anthropic, HuggingFace, DeepMind, Verge, MIT TR, VentureBeat, HN)
- 🏢 SAP & Enterprise (SAP News, Google News)
- 🔬 Science & Research (arXiv cs.AI/LG/CL/CV papers + Nature + ScienceDaily)

## Setup

Add these secrets to the repo (Settings > Secrets > Actions):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

## Manual trigger

Use the Actions tab > Daily Research Digest > Run workflow.
