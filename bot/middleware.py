"""Middleware for mandatory subscription checking."""

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from loguru import logger
from db.database import Database
from config import Config


class MandatorySubscriptionMiddleware(BaseMiddleware):
    """Middleware to check mandatory subscription channels."""
    
    def __init__(self, database: Database):
        self.database = database
        super().__init__()
    
    async def __call__(self, handler, event: TelegramObject, data: dict):
        # Skip for admin users
        if hasattr(event, 'from_user') and event.from_user.id in Config.ADMIN_IDS:
            return await handler(event, data)
        
        # Skip for inline queries and callback queries from subscription check
        if hasattr(event, 'data') and isinstance(event, CallbackQuery):
            if event.data.startswith('check_subscription'):
                return await handler(event, data)
        
        # Only check for messages and callback queries
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)
        
        # Get mandatory channels
        mandatory_channels = await self.database.get_mandatory_channels()
        
        if not mandatory_channels:
            return await handler(event, data)
        
        # Check user subscription status for each channel
        bot = data.get('bot') or (event.bot if hasattr(event, 'bot') else None)
        if not bot:
            return await handler(event, data)
        
        user_id = event.from_user.id
        unsubscribed_channels = []
        
        for channel_data in mandatory_channels:
            channel_id = channel_data[1]  # channel_id
            channel_type = channel_data[2]  # channel_type
            channel_username = channel_data[3]  # channel_username
            channel_title = channel_data[4]  # channel_title
            invite_link = channel_data[5]  # invite_link
            
            try:
                # Check if user is subscribed to the channel
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    unsubscribed_channels.append({
                        'id': channel_id,
                        'type': channel_type,
                        'username': channel_username,
                        'title': channel_title,
                        'invite_link': invite_link
                    })
            except (TelegramForbiddenError, TelegramBadRequest) as e:
                logger.warning(f"Could not check subscription for channel {channel_id}: {e}")
                # If we can't check, assume user is not subscribed
                unsubscribed_channels.append({
                    'id': channel_id,
                    'type': channel_type,
                    'username': channel_username,
                    'title': channel_title,
                    'invite_link': invite_link
                })
        
        # If user is not subscribed to all required channels, show subscription message
        if unsubscribed_channels:
            await self.send_subscription_message(event, unsubscribed_channels)
            return  # Don't proceed with the original handler
        
        # User is subscribed to all channels, proceed normally
        return await handler(event, data)
    
    async def send_subscription_message(self, event, unsubscribed_channels):
        """Send mandatory subscription message to user."""
        subscription_text = (
            "🔒 \u003cb\u003eMajburiy obuna!\u003c/b\u003e\n\n"
            "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n\n"
        )
        
        keyboard_buttons = []
        
        for i, channel in enumerate(unsubscribed_channels, 1):
            channel_name = channel['title'] or f"Kanal {i}"
            
            if channel['type'] == 'public' and channel['username']:
                # Public channel with username
                channel_link = f"https://t.me/{channel['username'].lstrip('@')}"
                subscription_text += f"{i}. \u003ca href='{channel_link}'\u003e{channel_name}\u003c/a\u003e\n"
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"📢 {channel_name}",
                        url=channel_link
                    )
                ])
            elif channel['type'] == 'private' and channel['invite_link']:
                # Private channel with invite link
                subscription_text += f"{i}. {channel_name}\n"
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"🔐 {channel_name}",
                        url=channel['invite_link']
                    )
                ])
            else:
                # Fallback
                subscription_text += f"{i}. {channel_name}\n"
        
        subscription_text += "\n✅ Obuna bo'lgandan so'ng pastdagi tugmani bosing:"
        
        # Add check subscription button
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="✅ Obunani tekshirish",
                callback_data="check_subscription"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        if isinstance(event, Message):
            await event.reply(subscription_text, reply_markup=keyboard)
        elif isinstance(event, CallbackQuery):
            await event.message.edit_text(subscription_text, reply_markup=keyboard)
            await event.answer("❌ Avval kanallarga obuna bo'ling!", show_alert=True)

