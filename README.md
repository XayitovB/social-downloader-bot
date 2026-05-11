# 📥 Social Downloader Bot

Telegram bot for downloading videos from Instagram, YouTube, TikTok, Facebook, and Twitter/X.

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-26A5E4?style=flat&logo=telegram&logoColor=white)
![License](https://img.shields.io/github/license/XayitovB/social-downloader-bot?style=flat)

## Supported Platforms
| Platform | Video | Audio |
|----------|-------|-------|
| YouTube | ✅ 360p–720p | ✅ MP3 |
| Instagram | ✅ | — |
| TikTok | ✅ | — |
| Facebook | ✅ | — |
| Twitter/X | ✅ | — |

## Features
- Smart caching — no duplicate downloads
- Queue management and rate limiting
- Subscription enforcement
- Admin panel with statistics and user management

## Quick Start
```bash
cp .env.example .env
pip install -r requirements.txt
python main.py
```

## Stack
`Python 3.8+` · `aiogram 3` · `Telethon` · `SQLite`
