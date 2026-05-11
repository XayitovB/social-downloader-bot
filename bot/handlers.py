"""Aiogram message handlers for the Telegram bot."""

import asyncio
import re
from aiogram import Router, F
from aiogram.types import Message, InlineQuery, InlineQueryResultCachedVideo, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger
from db.database import Database
from userbot.client import DownloaderUserbot
from bot.utils import URLValidator
from config import Config

# Global processing queue and lock
processing_queue = asyncio.Queue()
processing_lock = asyncio.Lock()
current_processing_user = None
processing_workers_started = False

# Safe callback query answer wrapper
async def safe_answer_callback_query(callback_query: CallbackQuery, text: str = None, show_alert: bool = False):
    """Safely answer callback query with error handling."""
    try:
        await callback_query.answer(text, show_alert=show_alert)
    except Exception as e:
        logger.warning(f"Could not answer callback query (probably expired): {e}")

# Queue item structure
class ProcessingRequest:
    def __init__(self, user_id: int, message: Message, url: str, url_type: str, userbot: 'DownloaderUserbot', db: 'Database'):
        self.user_id = user_id
        self.message = message
        self.url = url
        self.url_type = url_type
        self.userbot = userbot
        self.db = db
        self.completed = asyncio.Event()
        self.result = None
        self.error = None


# Initialize router
router = Router()

# FSM states for conversation
class Form(StatesGroup):
    url_submission = State()

# Admin FSM states
class AdminForm(StatesGroup):
    viewing_users = State()
    user_page = State()
    waiting_broadcast = State()
    
    # Mandatory subscription states
    mandatory_channels = State()
    add_channel_type = State()
    add_public_channel = State()
    add_private_channel_id = State()
    add_private_channel_link = State()
    
    # Instagram profile bypass states
    instagram_bypass = State()
    add_instagram_profile = State()


# --- Message Handlers ---

@router.message(F.text.startswith("/start"))
async def handle_start(message: Message, db: Database):
    """Handle /start command"""
    logger.info(f"Start command received: user={message.from_user.id}, chat={message.chat.id}, chat_type={message.chat.type}")
    
    # Handle /start command in both private chats and groups
    # In groups, send a simple welcome message
    if message.chat.type in ['group', 'supergroup']:
        await message.reply(
            f"✋ Salom {message.from_user.first_name}! Men video yuklovchi botman.\n\n"
            "📝 Instagram, YouTube, TikTok, Facebook yoki Twitter havolasini yuboring va men sizga videoni yuklab beraman!\n\n"
            "ℹ️ To'liq ma'lumot olish uchun menga shaxsiy xabar yuboring: /start"
        )
        return
    
    # Check mandatory subscription before showing welcome message
    mandatory_channels = await db.get_mandatory_channels()
    instagram_profiles = await db.get_instagram_mandatory_profiles()
    
    if mandatory_channels or instagram_profiles:
        user_id = message.from_user.id
        chat_id = message.chat.id
        unsubscribed_channels = []
        
        # Always check Telegram channels subscription status
        for channel_data in mandatory_channels:
            channel_id = channel_data[1]
            channel_type = channel_data[2]
            channel_username = channel_data[3]
            channel_title = channel_data[4]
            invite_link = channel_data[5]
            
            try:
                # Check if user is subscribed to the channel
                member = await message.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    unsubscribed_channels.append({
                        'id': channel_id,
                        'type': channel_type,
                        'username': channel_username,
                        'title': channel_title,
                        'invite_link': invite_link
                    })
            except Exception as e:
                logger.warning(f"Could not check subscription for channel {channel_id}: {e}")
                unsubscribed_channels.append({
                    'id': channel_id,
                    'type': channel_type,
                    'username': channel_username,
                    'title': channel_title,
                    'invite_link': invite_link
                })
        
        # Only show Instagram mandatory profiles if user hasn't seen them before
        has_seen_subscription_check = await db.has_shown_subscription_check(user_id, chat_id)
        if not has_seen_subscription_check and instagram_profiles:
            # Add Instagram mandatory profiles to unsubscribed list (shown only once)
            for profile in instagram_profiles:
                profile_id, username, profile_url, profile_title = profile
                unsubscribed_channels.append({
                    'id': profile_url,
                    'type': 'instagram',
                    'username': username,
                    'title': profile_title or f"@{username}",
                    'invite_link': profile_url
                })
        
        if unsubscribed_channels:
            unsubscribe_text = "🔒 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n\n"
            keyboard_buttons = []
            
            for channel in unsubscribed_channels:
                if channel['type'] == 'instagram':
                    # Instagram profile
                    unsubscribe_text += f"• 📸 {channel['title']} (Instagram)\n"
                    keyboard_buttons.append([InlineKeyboardButton(
                        text=f"📸 {channel['title']}",
                        url=channel['invite_link']
                    )])
                elif channel['username']:
                    # Telegram channel with username
                    unsubscribe_text += f"• @{channel['username']}\n"
                    keyboard_buttons.append([InlineKeyboardButton(
                        text=f"📢 {channel['title']}", 
                        url=f"https://t.me/{channel['username']}"
                    )])
                else:
                    # Telegram channel with invite link
                    unsubscribe_text += f"• {channel['title']}\n"
                    keyboard_buttons.append([InlineKeyboardButton(
                        text=f"📢 {channel['title']}", 
                        url=channel['invite_link']
                    )])
            
            keyboard_buttons.append([InlineKeyboardButton(
                text="✅ Obunani tekshirish", 
                callback_data="check_subscription"
            )])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            if instagram_profiles and not has_seen_subscription_check:
                unsubscribe_text += "\n📸 Instagram profillarga obuna manual tekshiriladi.\n"
            unsubscribe_text += "\n👆 Obunadan so'ng, 'Obunani tekshirish' tugmasini bosing."
            
            # Mark subscription check as shown if Instagram profiles are displayed
            if instagram_profiles and not has_seen_subscription_check:
                await db.mark_subscription_check_shown(user_id, chat_id)
            
            await message.reply(unsubscribe_text, reply_markup=keyboard)
            return
    
    # Get bot info for the add to group button
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username
    
    welcome_text = (
        "🎉 <b>Instagram, YouTube, TikTok, Facebook va Twitter Video Yuklovchi Botga xush kelibsiz!</b>\n\n"
        "📱 <b>Qo'llab-quvvatlanadigan platformalar:</b>\n"
        "• Instagram (Reels, Posts, IGTV)\n"
        "• YouTube (Videos, Shorts)\n"
        "• TikTok (Videos, Reels)\n"
        "• Facebook (Videos, Reels)\n"
        "• Twitter/X (Videos, GIF)\n\n"
        "🚀 <b>Foydalanish:</b>\n"
        "1. Instagram, YouTube, TikTok, Facebook yoki Twitter havolasini yuboring\n"
        "2. YouTube uchun format tanlang (360p/480p/720p/MP3)\n"
        "3. Videoni qabul qiling!\n\n"
        "⚡️ <b>Tezkor xizmat:</b> E'tiborli bo'ling - bir marta yuklangan videolar keshda saqlanadi va keyingi safar darhol yuboriladi!\n\n"
        "💡 <b>Maslahat:</b> Havola yuborishdan oldin to'g'ri formatda ekanligiga ishonch hosil qiling.\n\n"
        "👥 <b>Guruhga qo'shish:</b> Botni guruhga qo'shib, u yerda ham video yuklay olasiz!"
    )
    
    # Create keyboard with add to group button
    keyboard_buttons = [
        [InlineKeyboardButton(
            text="➕ Botni guruhga qo'shish", 
            url=f"https://t.me/{bot_username}?startgroup=true"
        )],
        [InlineKeyboardButton(
            text="ℹ️ Yordam", 
            callback_data="show_help"
        )]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.reply(welcome_text, reply_markup=keyboard)

@router.message(F.text.regexp(r'^(/help(@\w+)?|yordam|Yordam)$'))
async def handle_help(message: Message):
    """Handle help command"""
    logger.info(f"Help command received: user={message.from_user.id}, chat={message.chat.id}, chat_type={message.chat.type}")
    
    help_text = (
        "🆘 <b>Yordam</b>\n\n"
        "📋 <b>Qo'llab-quvvatlanadigan formatlar:</b>\n\n"
        "<b>Instagram:</b>\n"
        "• https://instagram.com/p/ABC123/\n"
        "• https://instagram.com/reel/XYZ789/\n"
        "• https://www.instagram.com/tv/DEF456/\n\n"
        "<b>YouTube:</b>\n"
        "• https://youtube.com/watch?v=ABC123\n"
        "• https://youtu.be/XYZ789\n"
        "• https://youtube.com/shorts/DEF456\n\n"
        "<b>TikTok:</b>\n"
        "• https://tiktok.com/@username/video/123456789\n"
        "• https://vm.tiktok.com/ABC123/\n"
        "• https://vt.tiktok.com/XYZ789/\n\n"
        "<b>Facebook:</b>\n"
        "• https://facebook.com/watch/?v=123456789\n"
        "• https://facebook.com/share/r/ABC123/\n"
        "• https://fb.watch/XYZ789/\n\n"
        "<b>Twitter/X:</b>\n"
        "• https://twitter.com/username/status/123456789\n"
        "• https://x.com/username/status/123456789\n"
        "• https://t.co/ABC123\n\n"
        "🎯 <b>YouTube formatlar:</b>\n"
        "• 360p - Past sifat (tez yuklash)\n"
        "• 480p - O'rta sifat\n"
        "• 720p - Yuqori sifat (HD)\n"
        "• MP3 - Faqat audio\n\n"
        "❓ <b>Muammo yuz berdimi?</b>\n"
        "• Havolani qayta tekshiring\n"
        "• Bir necha daqiqa kutib, qayta urinib ko'ring\n"
        "• Video mavjudligini tekshiring"
    )
    await message.reply(help_text)

@router.message(F.text == "/admin")
async def handle_admin(message: Message, state: FSMContext, db: Database):
    """Handle admin command to show admin panel"""
    if message.from_user.id not in Config.ADMIN_IDS:
        return await message.reply("🚫 Ushbu buyruq faqat adminlar uchun mavjud.")

    # Goto admin panel
    await state.set_state(AdminForm.viewing_users)
    await state.update_data(user_offset=0)
    await show_admin_panel(message, db)


# --- Broadcast Handler ---

# Handle admin channel input states
@router.message(AdminForm.add_public_channel, F.text)
async def handle_add_public_channel_input(message: Message, state: FSMContext, db: Database):
    """Handle public channel username input."""
    if message.from_user.id not in Config.ADMIN_IDS:
        return await message.reply("🚫 Ruxsat berilmagan!")
    
    # Handle cancel command
    if message.text == "/cancel":
        await state.clear()
        await message.reply("❌ Bekor qilindi.")
        return
    
    # Clean username input
    username = message.text.strip().replace('@', '')
    
    if not username:
        await message.reply("❌ Username bo'sh bo'lishi mumkin emas. Qaytadan kiriting:")
        return
    
    try:
        # Try to get channel info
        chat = await message.bot.get_chat(f"@{username}")
        
        # Add to database
        success = await db.add_mandatory_channel(
            channel_id=chat.id,
            channel_type='public',
            channel_username=username,
            channel_title=chat.title or chat.first_name or username,
            invite_link=None
        )
        
        if success:
            await state.clear()
            await message.reply(
                f"✅ Ochiq kanal muvaffaqiyatli qo'shildi!\n\n"
                f"📢 Kanal: {chat.title}\n"
                f"👤 Username: @{username}\n"
                f"🆔 ID: {chat.id}"
            )
        else:
            await message.reply("❌ Kanalni qo'shishda xatolik yuz berdi. Bu kanal allaqachon mavjud bo'lishi mumkin.")
    
    except Exception as e:
        logger.error(f"Error adding public channel: {e}")
        await message.reply(
            f"❌ Kanal topilmadi yoki xatolik yuz berdi.\n\n"
            f"Iltimos, to'g'ri username kiriting yoki kanalning ochiq ekanligiga ishonch hosil qiling."
        )

@router.message(AdminForm.add_private_channel_id, F.text)
async def handle_add_private_channel_id_input(message: Message, state: FSMContext, db: Database):
    """Handle private channel ID input."""
    if message.from_user.id not in Config.ADMIN_IDS:
        return await message.reply("🚫 Ruxsat berilmagan!")
    
    # Handle cancel command
    if message.text == "/cancel":
        await state.clear()
        await message.reply("❌ Bekor qilindi.")
        return
    
    # Validate channel ID format
    try:
        channel_id = int(message.text.strip())
        if channel_id >= 0:
            await message.reply("❌ Channel ID manfiy son bo'lishi kerak. Misol: -1001234567890")
            return
    except ValueError:
        await message.reply("❌ Noto'g'ri format. Channel ID son bo'lishi kerak. Misol: -1001234567890")
        return
    
    # Store channel ID and ask for invite link
    await state.update_data(private_channel_id=channel_id)
    await state.set_state(AdminForm.add_private_channel_link)
    
    await message.reply(
        "📝 <b>Endi bu kanal uchun taklif havolasini yuboring:</b>\n\n"
        "Misol: https://t.me/+AbCdEfGhIjKlMnOp\n\n"
        "❌ Bekor qilish uchun /cancel yuboring"
    )

@router.message(AdminForm.add_private_channel_link, F.text)
async def handle_add_private_channel_link_input(message: Message, state: FSMContext, db: Database):
    """Handle private channel invite link input."""
    if message.from_user.id not in Config.ADMIN_IDS:
        return await message.reply("🚫 Ruxsat berilmagan!")
    
    # Handle cancel command
    if message.text == "/cancel":
        await state.clear()
        await message.reply("❌ Bekor qilindi.")
        return
    
    invite_link = message.text.strip()
    
    # Basic validation for Telegram invite link
    if not (invite_link.startswith("https://t.me/+") or invite_link.startswith("https://t.me/joinchat/")):
        await message.reply(
            "❌ Noto'g'ri havola formati.\n\n"
            "To'g'ri format: https://t.me/+AbCdEfGhIjKlMnOp\n"
            "yoki: https://t.me/joinchat/AbCdEfGhIjKlMnOp"
        )
        return
    
    # Get stored channel ID
    data = await state.get_data()
    channel_id = data.get('private_channel_id')
    
    if not channel_id:
        await state.clear()
        await message.reply("❌ Sessiya muddati tugadi. Qaytadan boshlang.")
        return
    
    try:
        # Try to get channel info
        chat = await message.bot.get_chat(channel_id)
        
        # Add to database
        success = await db.add_mandatory_channel(
            channel_id=channel_id,
            channel_type='private',
            channel_username=None,
            channel_title=chat.title or "Yopiq kanal",
            invite_link=invite_link
        )
        
        if success:
            await state.clear()
            await message.reply(
                f"✅ Yopiq kanal muvaffaqiyatli qo'shildi!\n\n"
                f"📢 Kanal: {chat.title}\n"
                f"🆔 ID: {channel_id}\n"
                f"🔗 Havola: {invite_link[:50]}..."
            )
        else:
            await message.reply("❌ Kanalni qo'shishda xatolik yuz berdi. Bu kanal allaqachon mavjud bo'lishi mumkin.")
    
    except Exception as e:
        logger.error(f"Error adding private channel: {e}")
        await message.reply(
            f"❌ Kanal topilmadi yoki xatolik yuz berdi.\n\n"
            f"Iltimos, to'g'ri Channel ID va havola kiritganingizga ishonch hosil qiling."
        )

@router.message(AdminForm.add_instagram_profile, F.text)
async def handle_add_instagram_profile_input(message: Message, state: FSMContext, db: Database):
    """Handle Instagram profile username input."""
    if message.from_user.id not in Config.ADMIN_IDS:
        return await message.reply("🚫 Ruxsat berilmagan!")
    
    # Handle cancel command
    if message.text == "/cancel":
        await state.clear()
        await message.reply("❌ Bekor qilindi.")
        return
    
    # Clean username input
    username = message.text.strip().replace('@', '').lower()
    
    if not username:
        await message.reply("❌ Username bo'sh bo'lishi mumkin emas. Qaytadan kiriting:")
        return
    
    # Validate Instagram username format
    import re
    if not re.match(r'^[a-zA-Z0-9_.]{1,30}$', username):
        await message.reply(
            "❌ Noto'g'ri Instagram username formati.\n\n"
            "To'g'ri format: username yoki @username\n"
            "Misol: john_doe yoki @john_doe"
        )
        return
    
    try:
        # Add to database
        success = await db.add_instagram_mandatory_profile(username)
        
        if success:
            await state.clear()
            await message.reply(
                f"✅ Instagram majburiy profil muvaffaqiyatli qo'shildi!\n\n"
                f"📸 Profil: @{username}\n"
                f"🎯 Endi foydalanuvchilar bu profilga obuna bo'lgandan keyin video yuklay oladilar."
            )
        else:
            await message.reply("❌ Instagram profilni qo'shishda xatolik yuz berdi. Bu profil allaqachon mavjud bo'lishi mumkin.")
    
    except Exception as e:
        logger.error(f"Error adding Instagram mandatory profile: {e}")
        await message.reply(
            "❌ Instagram profilni qo'shishda xatolik yuz berdi.\n\n"
            "Iltimos, qaytadan urinib ko'ring."
        )

@router.message(F.text.startswith("/reset_subscription_check"))
async def handle_reset_subscription_check(message: Message, db: Database):
    """Admin command to reset subscription check notification for a user"""
    if message.from_user.id not in Config.ADMIN_IDS:
        return await message.reply("🚫 Ushbu buyruq faqat adminlar uchun mavjud.")
    
    # Parse user ID from command
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply(
                "📝 **Foydalanish:** `/reset_subscription_check <user_id>`\n\n"
                "Misol: `/reset_subscription_check 123456789`\n\n"
                "Bu buyruq foydalanuvchi uchun Instagram majburiy obuna tekshiruvini qayta ko'rsatishga imkon beradi."
            )
            return
        
        user_id = int(parts[1])
        success = await db.reset_subscription_check_for_user(user_id)
        
        if success:
            await message.reply(
                f"✅ Foydalanuvchi {user_id} uchun obuna tekshiruvi muvaffaqiyatli qayta tiklandi.\n\n"
                "Endi bu foydalanuvchi /start buyrug'ini bosganida Instagram majburiy obunalari qayta ko'rsatiladi."
            )
        else:
            await message.reply(
                f"⚠️ Foydalanuvchi {user_id} uchun obuna tekshiruvi topilmadi yoki allaqachon qayta tiklanmagan."
            )
            
    except ValueError:
        await message.reply("❌ User ID raqam bo'lishi kerak. Misol: `/reset_subscription_check 123456789`")
    except Exception as e:
        logger.error(f"Error resetting subscription check: {e}")
        await message.reply("❌ Obuna tekshiruvini qayta tiklashda xatolik yuz berdi.")

@router.message(AdminForm.waiting_broadcast, F.content_type.in_(["text", "photo", "video", "audio", "document"]))
async def handle_broadcast_message(message: Message, state: FSMContext, db: Database):
    """Handle broadcast message from admin"""
    if message.from_user.id not in Config.ADMIN_IDS:
        return await message.reply("🚫 Ruxsat berilmagan!")
    
    # Reset state
    await state.clear()
    
    # Get all users
    all_users = await db.get_all_users()
    total_users = len(all_users)
    
    if total_users == 0:
        return await message.reply("👥 Hech qanday foydalanuvchi topilmadi.")
    
    # Ask for confirmation
    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, yuborish", callback_data="broadcast_confirm"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="broadcast_cancel")
        ]
    ])
    
    await message.reply(
        f"📢 <b>Xabar tafsilotlari:</b>\n\n"
        f"📊 Jami {total_users} ta foydalanuvchiga yuboriladi\n"
        f"📄 Xabar turi: {get_message_type(message)}\n\n"
        f"<b>Xabarni tasdiqlaysizmi?</b>",
        reply_markup=confirm_keyboard
    )
    
    # Store broadcast message for later sending
    await state.update_data(broadcast_message=message.message_id)


@router.callback_query(F.data.startswith("broadcast_"))
async def handle_broadcast_callback(callback_query: CallbackQuery, state: FSMContext, db: Database):
    """Handle broadcast confirmation callbacks"""
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        return await safe_answer_callback_query(callback_query, "ЁЯЪл Ruxsat berilmagan!", show_alert=True)
    
    action = callback_query.data.split("_")[1]
    
    if action == "confirm":
        await callback_query.answer("📤 Xabar yuborilmoqda...")
        
        # Get stored message ID
        data = await state.get_data()
        broadcast_message_id = data.get('broadcast_message')
        
        if not broadcast_message_id:
            return await callback_query.message.edit_text("❌ Xabar topilmadi. Qaytadan urinib ko'ring.")
        
        # Start broadcast
        await start_broadcast(callback_query.message, db, broadcast_message_id)
        
    elif action == "cancel":
        await callback_query.answer("❌ Bekor qilindi")
        await callback_query.message.edit_text("❌ Xabar yuborish bekor qilindi.")
    
    await state.clear()


@router.message(F.text)
async def handle_text(message: Message, state: FSMContext, db: Database, userbot: DownloaderUserbot):
    """Handle incoming text messages containing Instagram, YouTube and TikTok URLs."""
    # Check current FSM state
    current_state = await state.get_state()
    
    # Debug logging with more details
    logger.info(f"handle_text called: user={message.from_user.id} ({message.from_user.first_name}), chat={message.chat.id}, chat_type={message.chat.type}, text='{message.text[:100]}...', current_state='{current_state}'")
    
    # Check if message starts with / command but it's not a URL
    if message.text.startswith('/') and 'http' not in message.text:
        logger.info(f"Command received: {message.text}, skipping URL processing")
        return
    
    # Skip URL processing if admin is in any admin FSM state (only in private chats)
    if message.chat.type == 'private' and message.from_user.id in Config.ADMIN_IDS and current_state:
        admin_states = [
            AdminForm.waiting_broadcast,
            AdminForm.add_public_channel,
            AdminForm.add_private_channel_id,
            AdminForm.add_private_channel_link,
            AdminForm.add_instagram_profile
        ]
        if current_state in admin_states:
            logger.info(f"Admin in FSM state {current_state}, skipping URL processing")
            # These states will be handled by their respective handlers
            return
    
    # Extract URLs from text
    urls = URLValidator.extract_urls_from_text(message.text)
    
    if not urls:
        # In groups, don't reply if no URLs found to avoid spam
        if message.chat.type == 'private':
            await message.reply("Iltimos, yaroqli Instagram, YouTube, TikTok, Facebook yoki Twitter havolasini yuboring.")
        return
    
    # Log found URLs for debugging
    logger.info(f"Found {len(urls)} URL(s) in message from user {message.from_user.id} in chat {message.chat.id}: {urls}")
    
    # Process first URL
    url = urls[0]
    url_type = URLValidator.get_url_type(url)
    
    # Check if user is subscribed to mandatory channels and Instagram profiles
    mandatory_channels = await db.get_mandatory_channels()
    instagram_profiles = await db.get_instagram_mandatory_profiles()
    
    if mandatory_channels or instagram_profiles:
        user_id = message.from_user.id
        unsubscribed_channels = []
        
        logger.info(f"Checking mandatory subscription for user {user_id} in chat {message.chat.id} (type: {message.chat.type}), found {len(mandatory_channels)} channels and {len(instagram_profiles)} Instagram profiles")
        
        for channel_data in mandatory_channels:
            channel_id = channel_data[1]
            channel_type = channel_data[2]
            channel_username = channel_data[3]
            channel_title = channel_data[4]
            invite_link = channel_data[5]
            
            try:
                # Check if user is subscribed to the channel
                member = await message.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    logger.info(f"User {user_id} is NOT subscribed to channel {channel_id} (@{channel_username}), status: {member.status}")
                    unsubscribed_channels.append({
                        'id': channel_id,
                        'type': channel_type,
                        'username': channel_username,
                        'title': channel_title,
                        'invite_link': invite_link
                    })
                else:
                    logger.debug(f"User {user_id} is subscribed to channel {channel_id} (@{channel_username}), status: {member.status}")
            except Exception as e:
                logger.warning(f"Could not check subscription for channel {channel_id}: {e}")
                unsubscribed_channels.append({
                    'id': channel_id,
                    'type': channel_type,
                    'username': channel_username,
                    'title': channel_title,
                    'invite_link': invite_link
                })
        
        # Add Instagram mandatory profiles (always show as unsubscribed since we can't check Instagram subscriptions via Telegram API)
        for profile in instagram_profiles:
            profile_id, username, profile_url, profile_title = profile
            unsubscribed_channels.append({
                'id': profile_url,  # Use URL as ID for Instagram profiles
                'type': 'instagram',
                'username': username,
                'title': profile_title or f"@{username}",
                'invite_link': profile_url
            })
        
        if unsubscribed_channels:
            logger.info(f"User {user_id} is not subscribed to {len(unsubscribed_channels)} channels, blocking access in chat {message.chat.id} (type: {message.chat.type})")
            # In groups, send a concise subscription reminder with buttons
            if message.chat.type in ['group', 'supergroup']:
                logger.info(f"Sending subscription reminder to user {user_id} in group {message.chat.id}")
                # Create inline buttons for channels
                keyboard_buttons = []
                unsubscribe_text = f"🔒 {message.from_user.first_name}, video olish uchun avval quyidagi kanallarga obuna bo'ling:\n\n"
                
                for channel in unsubscribed_channels:
                    if channel['type'] == 'instagram':
                        # Instagram profile
                        unsubscribe_text += f"• 📸 {channel['title']} (Instagram)\n"
                        keyboard_buttons.append([InlineKeyboardButton(
                            text=f"📸 {channel['title']}",
                            url=channel['invite_link']
                        )])
                    elif channel['username']:
                        # Telegram channel with username
                        unsubscribe_text += f"• @{channel['username']}\n"
                        keyboard_buttons.append([InlineKeyboardButton(
                            text=f"📢 {channel['title']}", 
                            url=f"https://t.me/{channel['username']}"
                        )])
                    else:
                        # Telegram channel with invite link
                        unsubscribe_text += f"• {channel['title']}\n"
                        if channel['invite_link']:
                            keyboard_buttons.append([InlineKeyboardButton(
                                text=f"📢 {channel['title']}", 
                                url=channel['invite_link']
                            )])
                
                # Add subscription check button with URL for auto-processing
                # Encode URL in base64 to avoid callback data limits
                import base64
                url_encoded = base64.b64encode(urls[0].encode()).decode()[:50] if urls else "nourl"
                keyboard_buttons.append([InlineKeyboardButton(
                    text="✅ Obunani tekshirish", 
                    callback_data=f"check_sub_{user_id}_{url_encoded[:20]}" # Limit to avoid callback data size limits
                )])
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                if instagram_profiles:
                    unsubscribe_text += "\n📸 Instagram profillarga obuna manual tekshiriladi.\n"
                unsubscribe_text += "\n👆 Obunadan so'ng, 'Obunani tekshirish' tugmasini bosing."
                await message.reply(unsubscribe_text, reply_markup=keyboard)
            else:
                logger.info(f"Sending subscription message with buttons to user {user_id} in private chat")
                # In private chat, show full subscription message with buttons
                unsubscribe_text = "🔒 Iltimos, quyidagi kanallarga obuna bo'ling:\n\n"
                keyboard_buttons = []
                
                for channel in unsubscribed_channels:
                    if channel['type'] == 'instagram':
                        # Instagram profile
                        unsubscribe_text += f"• 📸 {channel['title']} (Instagram)\n"
                        keyboard_buttons.append([InlineKeyboardButton(
                            text=f"📸 {channel['title']}",
                            url=channel['invite_link']
                        )])
                    elif channel['username']:
                        # Telegram channel with username
                        unsubscribe_text += f"• @{channel['username']}\n"
                        keyboard_buttons.append([InlineKeyboardButton(
                            text=f"📢 {channel['title']}", 
                            url=f"https://t.me/{channel['username']}"
                        )])
                    else:
                        # Telegram channel with invite link
                        unsubscribe_text += f"• {channel['title']}\n"
                        keyboard_buttons.append([InlineKeyboardButton(
                            text=f"📢 {channel['title']}", 
                            url=channel['invite_link']
                        )])
                
                # Add subscription check button with URL for auto-processing
                import base64
                url_encoded = base64.b64encode(urls[0].encode()).decode()[:50] if urls else "nourl"
                keyboard_buttons.append([InlineKeyboardButton(
                    text="✅ Obunani tekshirish", 
                    callback_data=f"check_subscription_{url_encoded[:20]}"
                )])
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                if instagram_profiles:
                    unsubscribe_text += "\n📸 Instagram profillarga obuna manual tekshiriladi.\n"
                unsubscribe_text += "\n👆 Obunadan so'ng, 'Obunani tekshirish' tugmasini bosing."
                await message.reply(unsubscribe_text, reply_markup=keyboard)
            return

    # User passed subscription check or no mandatory channels configured
    if not mandatory_channels:
        logger.info(f"✅ User {message.from_user.id} proceeding (no mandatory channels configured) in chat {message.chat.id} (type: {message.chat.type})")
    else:
        logger.info(f"✅ User {message.from_user.id} passed subscription check, proceeding with URL processing in chat {message.chat.id} (type: {message.chat.type})")
    
    # Add user to database
    await db.add_or_update_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    # In groups, show that bot is processing the URL
    if message.chat.type in ['group', 'supergroup']:
        logger.info(f"Automatically processing URL from user {message.from_user.id} in group {message.chat.id}")
    
    # Process the URL (already extracted above)
    normalized_url = URLValidator.normalize_url(url)
    
    if not normalized_url:
        error_msg = "Taqdim etilgan havola yaroqsiz."
        if message.chat.type == 'private':
            await message.reply(error_msg)
        else:
            await message.reply(f"@{message.from_user.username or message.from_user.first_name}, {error_msg.lower()}")
        return
    
    # Add 👀 reaction to the message (visual indicator only, no functionality)
    try:
        from aiogram.types import ReactionTypeEmoji
        reaction = ReactionTypeEmoji(emoji="👀")
        await message.bot.set_message_reaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[reaction]
        )
        logger.info(f"Added 👀 reaction to message {message.message_id} from user {message.from_user.id}")
    except Exception as e:
        logger.warning(f"Could not add reaction to message: {e}")
    
    # For Instagram, TikTok, Facebook, and Twitter, check normal cache. For YouTube, we'll check format-specific cache later
    if url_type in ['instagram', 'tiktok', 'facebook', 'twitter']:
        existing_video = await db.get_video(normalized_url)
        
        if existing_video:
            channel_message_id, timestamp = existing_video
            logger.info(f"Found existing {url_type} video for {normalized_url} (message_id: {channel_message_id}) in chat {message.chat.id}")
            try:
                # Copy video from storage channel (no "Forwarded from" header)
                copied_msg = await message.bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=Config.STORAGE_CHANNEL_ID,
                    message_id=channel_message_id,
                    reply_to_message_id=message.message_id
                )
                
                # In groups, add a brief caption
                if message.chat.type in ['group', 'supergroup']:
                    logger.info(f"Sent cached {url_type} video to group {message.chat.id} for user {message.from_user.id}")
                    
            except Exception as e:
                logger.error(f"Failed to forward video: {e}")
                error_msg = "Kechirasiz, videoni olib bo'lmadi. U ombordan o'chirilgan bo'lishi mumkin."
                if message.chat.type == 'private':
                    await message.reply(error_msg)
                else:
                    await message.reply(f"{message.from_user.first_name}, {error_msg.lower()}")
            return
    
    # If not found, queue for processing (Instagram, TikTok, Facebook, and Twitter)
    if url_type in ['instagram', 'tiktok', 'facebook', 'twitter']:
        # Add to processing queue
        await queue_processing_request(
            user_id=message.from_user.id,
            message=message,
            url=normalized_url,
            url_type=url_type,
            userbot=userbot,
            db=db
        )
    elif url_type == 'youtube':
        # For YouTube, we need to show format selection first
        logger.info(f"YouTube URL detected: {normalized_url} in chat type {message.chat.type}")
        
        # In groups, automatically process YouTube URLs
        if message.chat.type in ['group', 'supergroup']:
            logger.info(f"Automatically processing YouTube URL in group {message.chat.id} from user {message.from_user.id}")
        
        await show_youtube_formats(message, normalized_url, userbot, db)
    else:
        error_msg = "Kechirasiz, so'rovingizni qayta ishlab bo'lmadi. Iltimos, havolani tekshiring yoki keyinroq qayta urinib ko'ring."
        if message.chat.type == 'private':
            await message.reply(error_msg)
        else:
            await message.reply(f"@{message.from_user.username or message.from_user.first_name}, {error_msg.lower()}")


# Mandatory subscription section

async def list_mandatory_channels(message: Message, db: Database):
    """List all mandatory subscription channels with options to add or remove."""
    channels = await db.get_mandatory_channels()
    
    if not channels:
        text = "🔒 Hozircha hech qanday majburiy kanal yo'q."
    else:
        text = "🔒 \u003cb\u003eMajburiy obuna kanallari:\u003c/b\u003e\n\n"
        for channel in channels:
            text += f"• {channel[4]} (@{channel[3]})\n"
    
    # Add options to add or remove channels
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="add_mandatory_channel")],
        [InlineKeyboardButton(text="❌ Kanalni olib tashlash", callback_data="remove_mandatory_channel")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back")]
    ])
    await message.reply(text, reply_markup=keyboard)

async def show_instagram_mandatory_panel(message: Message, db: Database):
    """Show Instagram mandatory profiles panel with list and options."""
    try:
        mandatory_profiles = await db.get_instagram_mandatory_profiles()
        
        if not mandatory_profiles:
            text = "📸 \u003cb\u003eInstagram Majburiy Profillari:\u003c/b\u003e\n\nHozircha hech qanday majburiy Instagram profil yo'q."
        else:
            text = "📸 \u003cb\u003eInstagram Majburiy Profillari:\u003c/b\u003e\n\n"
            text += "Foydalanuvchilar video yuklash uchun quyidagi Instagram profilearga obuna bo'lishi kerak:\n\n"
            for profile in mandatory_profiles:
                # profile[1] = username, profile[3] = profile_title
                username = profile[1]
                title = profile[3] or f"@{username}"
                text += f"• {title}\n"
        
        # Add options to add or remove profiles
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yangi profil qo'shish", callback_data="add_instagram_mandatory")],
            [InlineKeyboardButton(text="❌ Profilni olib tashlash", callback_data="remove_instagram_mandatory")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back")]
        ])
        
        await message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error showing Instagram mandatory panel: {e}")
        await message.edit_text("❌ Instagram majburiy panel ko'rsatishda xatolik yuz berdi.")


# --- YouTube Format Selection ---

async def show_youtube_formats(message: Message, url: str, userbot: DownloaderUserbot, db: Database):
    """Show predefined YouTube format options with cache info."""
    # Check which formats are already cached
    available_formats = []
    cached_formats = []
    
    for format_name in ['360p', '480p', '720p', 'mp3']:
        cache_key = f"{url}#{format_name}"
        existing_video = await db.get_video(cache_key)
        if existing_video:
            cached_formats.append(format_name)
        else:
            available_formats.append(format_name)
    
    # Get the format selection message from SaveYoutubeBot to map our buttons
    sent_message = await userbot.client.send_message(userbot.youtube_bot_username, url)
    format_message = await userbot._wait_for_format_message(
        userbot.youtube_bot_username,
        sent_message.id,
        max_wait_time=60
    )
    
    if not format_message or not format_message.reply_markup:
        error_msg = "❌ Video formatlarini olishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring."
        if message.chat.type == 'private':
            await message.reply(error_msg)
        else:
            await message.reply(f"@{message.from_user.username or message.from_user.first_name}, {error_msg.lower()}")
        return
    
    # Store the original format message for callback mapping with user ID
    await userbot.store_youtube_request(message.from_user.id, url, format_message)
    
    # Create our custom format buttons with cache indicators
    format_buttons = []
    
    # First row: 360p and 480p
    row1 = []
    for fmt in ['360p', '480p']:
        if fmt in cached_formats:
            text = f"✅ {fmt.upper()}"
        else:
            text = f"📹 {fmt.upper()}"
        row1.append(InlineKeyboardButton(text=text, callback_data=f"yt_{fmt}"))
    format_buttons.append(row1)
    
    # Second row: 720p and MP3
    row2 = []
    for fmt in ['720p', 'mp3']:
        if fmt in cached_formats:
            text = f"✅ {'MP3' if fmt == 'mp3' else fmt.upper()}"
        else:
            text = f"{'🎵' if fmt == 'mp3' else '📹'} {'MP3' if fmt == 'mp3' else fmt.upper()}"
        row2.append(InlineKeyboardButton(text=text, callback_data=f"yt_{fmt}"))
    format_buttons.append(row2)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=format_buttons)
    
    # Create status message
    user_mention = f"{message.from_user.first_name}" if message.chat.type in ['group', 'supergroup'] else ""
    status_text = f"{user_mention + ', ' if user_mention else ''}🍥 <b>YouTube Video Yuklovchi</b>\n\n"
    status_text += "📋 Kerakli formatni tanlang:\n\n"
    
    # Add format descriptions with cache status
    format_descriptions = {
        '360p': '📹 <b>360p</b> - Past sifat (kichik hajm)',
        '480p': '📹 <b>480p</b> - O\'rta sifat',
        '720p': '📹 <b>720p</b> - Yuqori sifat (HD)',
        'mp3': '🎵 <b>MP3</b> - Faqat audio fayl'
    }
    
    for fmt, desc in format_descriptions.items():
        if fmt in cached_formats:
            status_text += f"✅ {desc} <i>(keshda mavjud)</i>\n"
        else:
            status_text += f"{desc}\n"
    
    if cached_formats:
        status_text += "\n✅ <i>Keshda mavjud formatlar darhol yuboriladi</i>"
    
    if message.chat.type == 'private':
        await message.reply(status_text, reply_markup=keyboard)
    else:
        # In groups, reply to the original message
        await message.reply(status_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("yt_"))
async def handle_youtube_format_callback(callback_query: CallbackQuery, userbot, db: Database):
    """Handle YouTube format selection from inline button callback."""
    selected_format = callback_query.data.split("_")[1]  # 360p, 480p, 720p, mp3
    user_id = callback_query.from_user.id
    
    await safe_answer_callback_query(callback_query, f"⏳ {selected_format.upper()} format tanlandi...")
    
    # Get stored URL from userbot
    stored_request = await userbot.get_stored_youtube_request(user_id)
    if not stored_request:
        await callback_query.message.edit_text("❌ Xatolik: Sessiya muddati tugadi. Iltimos, qaytadan urinib ko'ring.")
        return
    
    url, format_message = stored_request
    cache_key = f"{url}#{selected_format}"
    
    # Check if this format is already cached
    existing_video = await db.get_video(cache_key)
    if existing_video:
        channel_message_id, _ = existing_video
        logger.info(f"Found cached YouTube video: {cache_key} (message_id: {channel_message_id})")
        
        if callback_query.message.chat.type == 'private':
            await callback_query.message.edit_text(f"✅ <b>{selected_format.upper()}</b> keshdan topildi! Yuborilmoqda...")
        else:
            await callback_query.message.edit_text(f"@{callback_query.from_user.username or callback_query.from_user.first_name}, ✅ <b>{selected_format.upper()}</b> keshdan topildi! Yuborilmoqda...")
        
        try:
            # In groups, reply to the message, in private send directly
            if callback_query.message.chat.type == 'private':
                await callback_query.message.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=Config.STORAGE_CHANNEL_ID,
                    message_id=channel_message_id,
                )
            else:
                # Find the original message to reply to
                try:
                    # Try to reply to the original URL message if possible
                    await callback_query.message.bot.copy_message(
                        chat_id=callback_query.message.chat.id,
                        from_chat_id=Config.STORAGE_CHANNEL_ID,
                        message_id=channel_message_id,
                    )
                except:
                    # Fallback to just sending without reply
                    await callback_query.message.bot.copy_message(
                        chat_id=callback_query.message.chat.id,
                        from_chat_id=Config.STORAGE_CHANNEL_ID,
                        message_id=channel_message_id,
                    )
        except Exception as e:
            logger.error(f"Failed to send cached video: {e}")
            error_msg = "❌ Fayl keshdan topildi, lekin uni yuborishda xatolik yuz berdi."
            if callback_query.message.chat.type == 'private':
                await callback_query.message.reply(error_msg)
            else:
                await callback_query.message.reply(f"@{callback_query.from_user.username or callback_query.from_user.first_name}, {error_msg.lower()}")
        return
    
    try:
        # Edit message to show processing status
        format_name = {
            '360p': '📹 360p (Past sifat)',
            '480p': '📹 480p (O\'rta sifat)', 
            '720p': '📹 720p (HD sifat)',
            'mp3': '🎵 MP3 (Audio)'
        }.get(selected_format, selected_format)
        
        # Create processing message based on chat type
        if callback_query.message.chat.type == 'private':
            process_text = (
                f"⬇️ <b>{format_name}</b> yuklanmoqda...\n\n"
                f"🔗 <b>URL:</b> {url[:50]}...\n\n"
                f"⏱️ Iltimos kutib turing, bu biroz vaqt olishi mumkin..."
            )
        else:
            process_text = (
                f"@{callback_query.from_user.username or callback_query.from_user.first_name}, "
                f"⬇️ <b>{format_name}</b> yuklanmoqda...\n\n"
                f"⏱️ Iltimos kutib turing, bu biroz vaqt olishi mumkin..."
            )
        
        await callback_query.message.edit_text(process_text)
        
        # Find the best matching button from SaveYoutubeBot
        target_callback_data = await userbot.find_matching_format_callback(
            format_message, selected_format
        )
        
        if not target_callback_data:
            await callback_query.message.edit_text(
                f"❌ {selected_format.upper()} formati topilmadi. "
                "Boshqa formatni tanlashingizni so'raymiz."
            )
            return
        
        # Process the request with the found format
        storage_message_id = await userbot.process_youtube_url(
            url,
            callback_data=target_callback_data
        )
        
        if storage_message_id:
            # Add to database with format suffix for caching different formats
            await db.add_video(cache_key, storage_message_id, platform='youtube')
            
            # Increment user download count
            await db.increment_user_downloads(user_id)
            
            # Edit message to show success
            if callback_query.message.chat.type == 'private':
                await callback_query.message.edit_text(
                    f"✅ <b>{format_name}</b> muvaffaqiyatli yuklandi!\n\n"
                    f"📱 Fayl quyida yuboriladi..."
                )
            else:
                await callback_query.message.edit_text(
                    f"@{callback_query.from_user.username or callback_query.from_user.first_name}, "
                    f"✅ <b>{format_name}</b> muvaffaqiyatli yuklandi!"
                )
            
            # Send video to user
            try:
                if callback_query.message.chat.type == 'private':
                    await callback_query.message.bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=Config.STORAGE_CHANNEL_ID,
                        message_id=storage_message_id,
                    )
                else:
                    # In groups, send to the chat
                    await callback_query.message.bot.copy_message(
                        chat_id=callback_query.message.chat.id,
                        from_chat_id=Config.STORAGE_CHANNEL_ID,
                        message_id=storage_message_id,
                    )
            except Exception as e:
                logger.error(f"Failed to send processed file to user: {e}")
                error_msg = (
                    "❌ Fayl yuklandi, lekin uni yuborishda xatolik yuz berdi. "
                    "Iltimos, qaytadan urinib ko'ring."
                )
                if callback_query.message.chat.type == 'private':
                    await callback_query.message.reply(error_msg)
                else:
                    await callback_query.message.reply(
                        f"@{callback_query.from_user.username or callback_query.from_user.first_name}, {error_msg.lower()}"
                    )
        else:
            await callback_query.message.edit_text(
                f"❌ {format_name} yuklashda xatolik yuz berdi.\n\n"
                "Iltimos, havolani tekshiring yoki qaytadan urinib ko'ring."
            )
            
    except Exception as e:
        logger.error(f"Error in YouTube callback handler: {e}")
        await callback_query.message.edit_text(
            "❌ Kutilmagan xatolik yuz berdi.\n\n"
            "Iltimos, qaytadan urinib ko'ring yoki boshqa formatni tanlang."
        )

# Mandatory subscription callbacks
@router.callback_query(F.data.startswith("add_mandatory_channel"))
async def handle_add_mandatory_channel(callback_query: CallbackQuery, state: FSMContext, db: Database):
    """Handle adding mandatory channel selection."""
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        return await safe_answer_callback_query(callback_query, "ЁЯЪл Ruxsat berilmagan!", show_alert=True)
    
    await callback_query.answer("📝 Kanal turini tanlang...")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Ochiq kanal (Public)", callback_data="add_public_channel")],
        [InlineKeyboardButton(text="🔒 Yopiq kanal (Private)", callback_data="add_private_channel")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_mandatory")]
    ])
    
    await callback_query.message.edit_text(
        "📝 <b>Kanal turini tanlang:</b>\n\n"
        "🌐 <b>Ochiq kanal:</b> @username bilan\n"
        "🔒 <b>Yopiq kanal:</b> Taklif havolasi bilan",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "add_public_channel")
async def handle_add_public_channel(callback_query: CallbackQuery, state: FSMContext, db: Database):
    """Handle adding public channel."""
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        return await safe_answer_callback_query(callback_query, "ЁЯЪл Ruxsat berilmagan!", show_alert=True)
    
    await callback_query.answer("📝 Username kiriting...")
    await state.set_state(AdminForm.add_public_channel)
    
    await callback_query.message.edit_text(
        "📝 <b>Ochiq kanalning @username ni kiriting:</b>\n\n"
        "Misol: @mychannel yoki mychannel\n\n"
        "❌ Bekor qilish uchun /cancel yuboring"
    )

@router.callback_query(F.data == "add_private_channel")
async def handle_add_private_channel(callback_query: CallbackQuery, state: FSMContext, db: Database):
    """Handle adding private channel."""
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        return await safe_answer_callback_query(callback_query, "ЁЯЪл Ruxsat berilmagan!", show_alert=True)
    
    await callback_query.answer("📝 Kanal ID kiriting...")
    await state.set_state(AdminForm.add_private_channel_id)
    
    await callback_query.message.edit_text(
        "📝 <b>Yopiq kanalning ID sini kiriting:</b>\n\n"
        "Misol: -1001234567890\n\n"
        "❌ Bekor qilish uchun /cancel yuboring"
    )

@router.callback_query(F.data == "remove_mandatory_channel")
async def handle_remove_mandatory_channel(callback_query: CallbackQuery, db: Database):
    """Handle removing mandatory channel."""
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        return await safe_answer_callback_query(callback_query, "ЁЯЪл Ruxsat berilmagan!", show_alert=True)
    
    channels = await db.get_mandatory_channels()
    
    if not channels:
        await safe_answer_callback_query(callback_query, "тЭМ Hech qanday kanal topilmadi!", show_alert=True)
        return
    
    keyboard_buttons = []
    for channel in channels:
        channel_id = channel[1]
        channel_title = channel[4] or "Nomsiz kanal"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"❌ {channel_title}",
                callback_data=f"remove_channel_{channel_id}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_mandatory")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback_query.message.edit_text(
        "❌ \u003cb\u003eO'chirish uchun kanalni tanlang:\u003c/b\u003e\n\n"
        "⚠️ Tanlangan kanal majburiy obuna ro'yxatidan o'chiriladi.",
        reply_markup=keyboard
    )
    
    await callback_query.answer("🗑️ O'chirish uchun kanalni tanlang...")

@router.callback_query(F.data == "add_instagram_mandatory")
async def handle_add_instagram_mandatory(callback_query: CallbackQuery, state: FSMContext):
    """Handle adding Instagram mandatory profile."""
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        return await safe_answer_callback_query(callback_query, "ЁЯЪл Ruxsat berilmagan!", show_alert=True)
    
    await callback_query.answer("📝 Username kiriting...")
    await state.set_state(AdminForm.add_instagram_profile)
    
    await callback_query.message.edit_text(
        "📝 \u003cb\u003eInstagram profil username ini kiriting:\u003c/b\u003e\n\n"
        "Misol: username yoki @username\n\n"
        "Bu profil majburiy obuna ro'yxatiga qo'shiladi. Foydalanuvchilar video yuklash uchun bu profilga obuna bo'lishi kerak.\n\n"
        "❌ Bekor qilish uchun /cancel yuboring"
    )

@router.callback_query(F.data == "remove_instagram_mandatory")
async def handle_remove_instagram_mandatory(callback_query: CallbackQuery, db: Database):
    """Handle removing Instagram mandatory profile."""
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        return await safe_answer_callback_query(callback_query, "ЁЯЪл Ruxsat berilmagan!", show_alert=True)
    
    profiles = await db.get_instagram_mandatory_profiles()
    
    if not profiles:
        await safe_answer_callback_query(callback_query, "тЭМ Hech qanday profil topilmadi!", show_alert=True)
        return
    
    keyboard_buttons = []
    for profile in profiles:
        profile_id = profile[0]
        profile_username = profile[1]
        profile_title = profile[3] if len(profile) > 3 else f"@{profile_username}"
        display_text = f"❌ {profile_title}"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=display_text,
                callback_data=f"remove_instagram_profile_{profile_id}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_instagram_mandatory")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback_query.message.edit_text(
        "❌ \u003cb\u003eO'chirish uchun profilni tanlang:\u003c/b\u003e\n\n"
        "⚠️ Tanlangan profil majburiy obuna ro'yxatidan o'chiriladi.",
        reply_markup=keyboard
    )
    
    await callback_query.answer("🗑️ O'chirish uchun profilni tanlang...")

@router.callback_query(F.data.startswith("remove_channel_"))
async def handle_remove_channel_confirm(callback_query: CallbackQuery, db: Database):
    """Handle channel removal confirmation."""
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        return await safe_answer_callback_query(callback_query, "ЁЯЪл Ruxsat berilmagan!", show_alert=True)
    
    channel_id = callback_query.data.split("_", 2)[2]
    
    success = await db.remove_mandatory_channel(channel_id)
    
    if success:
        await callback_query.answer("✅ Kanal muvaffaqiyatli o'chirildi!")
        await list_mandatory_channels(callback_query.message, db)
    else:
        await safe_answer_callback_query(callback_query, "тЭМ Kanalni o'chirishda xatolik yuz berdi!", show_alert=True)

@router.callback_query(F.data.startswith("remove_instagram_profile_"))
async def handle_remove_instagram_profile_confirm(callback_query: CallbackQuery, db: Database):
    """Handle Instagram mandatory profile removal confirmation."""
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        return await safe_answer_callback_query(callback_query, "ЁЯЪл Ruxsat berilmagan!", show_alert=True)
    
    profile_id = int(callback_query.data.split("_")[-1])
    
    success = await db.remove_instagram_mandatory_profile(profile_id)
    
    if success:
        await callback_query.answer("✅ Instagram majburiy profil muvaffaqiyatli o'chirildi!")
        await show_instagram_mandatory_panel(callback_query.message, db)
    else:
        await safe_answer_callback_query(callback_query, "тЭМ Instagram profilni o'chirishda xatolik yuz berdi!", show_alert=True)

@router.callback_query(F.data == "show_help")
async def handle_show_help(callback_query: CallbackQuery):
    """Handle help button callback."""
    help_text = (
        "🆘 <b>Yordam</b>\n\n"
        "📋 <b>Qo'llab-quvvatlanadigan formatlar:</b>\n\n"
        "<b>Instagram:</b>\n"
        "• https://instagram.com/p/ABC123/\n"
        "• https://instagram.com/reel/XYZ789/\n"
        "• https://www.instagram.com/tv/DEF456/\n\n"
        "<b>YouTube:</b>\n"
        "• https://youtube.com/watch?v=ABC123\n"
        "• https://youtu.be/XYZ789\n"
        "• https://youtube.com/shorts/DEF456\n\n"
        "<b>TikTok:</b>\n"
        "• https://tiktok.com/@username/video/123456789\n"
        "• https://vm.tiktok.com/ABC123/\n"
        "• https://vt.tiktok.com/XYZ789/\n\n"
        "<b>Facebook:</b>\n"
        "• https://facebook.com/watch/?v=123456789\n"
        "• https://facebook.com/share/r/ABC123/\n"
        "• https://fb.watch/XYZ789/\n\n"
        "<b>Twitter/X:</b>\n"
        "• https://twitter.com/username/status/123456789\n"
        "• https://x.com/username/status/123456789\n"
        "• https://t.co/ABC123\n\n"
        "🎯 <b>YouTube formatlar:</b>\n"
        "• 360p - Past sifat (tez yuklash)\n"
        "• 480p - O'rta sifat\n"
        "• 720p - Yuqori sifat (HD)\n"
        "• MP3 - Faqat audio\n\n"
        "👥 <b>Guruhda foydalanish:</b>\n"
        "• Botni guruhga admin sifatida qo'shing\n"
        "• Guruhda video havolalarini yuboring\n"
        "• Bot avtomatik javob beradi (agar obuna bo'lgan bo'lsangiz)\n\n"
        "❓ <b>Muammo yuz berdimi?</b>\n"
        "• Havolani qayta tekshiring\n"
        "• Bir necha daqiqa kutib, qayta urinib ko'ring\n"
        "• Video mavjudligini tekshiring"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_start")]
    ])
    
    await callback_query.message.edit_text(help_text, reply_markup=keyboard)
    await safe_answer_callback_query(callback_query)

@router.callback_query(F.data == "back_to_start")
async def handle_back_to_start(callback_query: CallbackQuery, db: Database):
    """Handle back to start button."""
    # Get bot info for the add to group button
    bot_info = await callback_query.bot.get_me()
    bot_username = bot_info.username
    
    welcome_text = (
        "🎉 <b>Instagram, YouTube, TikTok, Facebook va Twitter Video Yuklovchi Botga xush kelibsiz!</b>\n\n"
        "📱 <b>Qo'llab-quvvatlanadigan platformalar:</b>\n"
        "• Instagram (Reels, Posts, IGTV)\n"
        "• YouTube (Videos, Shorts)\n"
        "• TikTok (Videos, Reels)\n"
        "• Facebook (Videos, Reels)\n"
        "• Twitter/X (Videos, GIF)\n\n"
        "🚀 <b>Foydalanish:</b>\n"
        "1. Instagram, YouTube, TikTok, Facebook yoki Twitter havolasini yuboring\n"
        "2. YouTube uchun format tanlang (360p/480p/720p/MP3)\n"
        "3. Videoni qabul qiling!\n\n"
        "⚡️ <b>Tezkor xizmat:</b> E'tiborli bo'ling - bir marta yuklangan videolar keshda saqlanadi va keyingi safar darhol yuboriladi!\n\n"
        "💡 <b>Maslahat:</b> Havola yuborishdan oldin to'g'ri formatda ekanligiga ishonch hosil qiling.\n\n"
        "👥 <b>Guruhga qo'shish:</b> Botni guruhga qo'shib, u yerda ham video yuklay olasiz!"
    )
    
    # Create keyboard with add to group button
    keyboard_buttons = [
        [InlineKeyboardButton(
            text="➕ Botni guruhga qo'shish", 
            url=f"https://t.me/{bot_username}?startgroup=true"
        )],
        [InlineKeyboardButton(
            text="ℹ️ Yordam", 
            callback_data="show_help"
        )]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback_query.message.edit_text(welcome_text, reply_markup=keyboard)
    await safe_answer_callback_query(callback_query)

@router.callback_query(F.data.startswith(("check_subscription", "check_sub")))
async def handle_check_subscription(callback_query: CallbackQuery, db: Database, userbot):
    """Handle subscription check - both general and user-specific."""
    # Extract components from callback data
    callback_parts = callback_query.data.split("_")
    target_user_id = callback_query.from_user.id  # Default to callback sender
    stored_url = None
    
    logger.info(f"Subscription check callback: {callback_query.data}")
    
    # Parse different callback formats:
    # check_subscription - general check
    # check_subscription_<url_encoded> - private chat with URL
    # check_sub_<user_id>_<url_encoded> - group with user ID and URL
    # check_sub_reaction_<user_id>_<url_encoded> - reaction-based group check
    # check_subscription_reaction_<url_encoded> - reaction-based private check
    
    if callback_parts[0] == "check" and callback_parts[1] == "sub":
        # Format: check_sub_<user_id>_<url_encoded> or check_sub_reaction_<user_id>_<url_encoded>
        if len(callback_parts) >= 3:
            if callback_parts[2] == "reaction":
                # Reaction-based group check: check_sub_reaction_<user_id>_<url_encoded>
                if len(callback_parts) >= 4 and callback_parts[3].isdigit():
                    target_user_id = int(callback_parts[3])
                    # Only allow the target user to check their own subscription
                    if callback_query.from_user.id != target_user_id:
                        await safe_answer_callback_query(callback_query, "ЁЯЪл Bu tekshiruv faqat sizning uchun emas!", show_alert=True)
                        return
                    
                    # Try to find the original URL from the reaction message storage
                    if callback_query.message.reply_to_message:
                        stored_message = await db.get_reaction_message(
                            callback_query.message.reply_to_message.message_id,
                            callback_query.message.chat.id,
                            target_user_id
                        )
                        if stored_message:
                            stored_url, url_type = stored_message
                            logger.info(f"Found stored URL for reaction: {stored_url}")
            elif callback_parts[2].isdigit():
                # Normal group check: check_sub_<user_id>_<url_encoded>
                target_user_id = int(callback_parts[2])
                # Only allow the target user to check their own subscription
                if callback_query.from_user.id != target_user_id:
                    await safe_answer_callback_query(callback_query, "ЁЯЪл Bu tekshiruv faqat sizning uchun emas!", show_alert=True)
                    return
                
                # Extract URL from callback data if present
                if len(callback_parts) >= 4:
                    try:
                        # Try to find the original URL in the message
                        if callback_query.message.reply_to_message:
                            urls = URLValidator.extract_urls_from_text(callback_query.message.reply_to_message.text or "")
                            if urls:
                                stored_url = urls[0]
                                logger.info(f"Found URL in original message: {stored_url}")
                    except Exception as e:
                        logger.warning(f"Could not decode URL from callback data: {e}")
    
    elif callback_parts[0] == "check" and callback_parts[1] == "subscription":
        # Format: check_subscription, check_subscription_<url_encoded>, or check_subscription_reaction_<url_encoded>
        if len(callback_parts) >= 3:
            if callback_parts[2] == "reaction":
                # Reaction-based private check: check_subscription_reaction_<url_encoded>
                # Try to find the original URL from the reaction message storage
                if callback_query.message.reply_to_message:
                    stored_message = await db.get_reaction_message(
                        callback_query.message.reply_to_message.message_id,
                        callback_query.message.chat.id,
                        callback_query.from_user.id
                    )
                    if stored_message:
                        stored_url, url_type = stored_message
                        logger.info(f"Found stored URL for private reaction: {stored_url}")
            else:
                # Normal private check with URL: check_subscription_<url_encoded>
                try:
                    # This is from private chat, find URL in reply message
                    if callback_query.message.reply_to_message:
                        urls = URLValidator.extract_urls_from_text(callback_query.message.reply_to_message.text or "")
                        if urls:
                            stored_url = urls[0]
                            logger.info(f"Found URL in private chat message: {stored_url}")
                except Exception as e:
                    logger.warning(f"Could not process URL from private chat: {e}")
    
    # Get mandatory channels (Instagram profiles are always "passed" since we can't check them via Telegram API)
    mandatory_channels = await db.get_mandatory_channels()
    instagram_profiles = await db.get_instagram_mandatory_profiles()
    
    if not mandatory_channels and not instagram_profiles:
        await safe_answer_callback_query(callback_query, "✅ Majburiy kanallar yo'q, botdan foydalanishingiz mumkin!")
        return
    elif not mandatory_channels and instagram_profiles:
        # Only Instagram profiles exist - automatically pass since we can't check Instagram subscriptions
        await safe_answer_callback_query(callback_query, "✅ Instagram profillari uchun tekshiruv o'tkazib yuborildi!")
        
        # Delete the subscription message and proceed with video processing
        try:
            await callback_query.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete subscription message: {e}")
            # If deletion fails, edit the message to show success
            try:
                await callback_query.message.edit_text(
                    f"✅ {callback_query.from_user.first_name}, Instagram obuna tekshiruvi o'tkazib yuborildi!\n\n"
                    f"🎉 Endi botdan to'liq foydalanishingiz mumkin. Video havolasini qayta yuboring!"
                )
            except:
                pass
        return
    
    unsubscribed_channels = []
    
    logger.info(f"Checking subscription for user {target_user_id} (requested by {callback_query.from_user.id})")
    
    for channel_data in mandatory_channels:
        channel_id = channel_data[1]
        channel_type = channel_data[2]
        channel_username = channel_data[3]
        channel_title = channel_data[4]
        invite_link = channel_data[5]
        
        try:
            # Check if user is subscribed to the channel
            member = await callback_query.bot.get_chat_member(chat_id=channel_id, user_id=target_user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                logger.info(f"User {target_user_id} is NOT subscribed to channel {channel_id} (@{channel_username}), status: {member.status}")
                unsubscribed_channels.append({
                    'id': channel_id,
                    'type': channel_type,
                    'username': channel_username,
                    'title': channel_title,
                    'invite_link': invite_link
                })
            else:
                logger.debug(f"User {target_user_id} is subscribed to channel {channel_id} (@{channel_username}), status: {member.status}")
        except Exception as e:
            logger.warning(f"Could not check subscription for channel {channel_id} for user {target_user_id}: {e}")
            unsubscribed_channels.append({
                'id': channel_id,
                'type': channel_type,
                'username': channel_username,
                'title': channel_title,
                'invite_link': invite_link
            })
    
    # NOTE: Instagram profiles are NOT added to unsubscribed list during check
    # because we can't verify Instagram subscriptions via Telegram API.
    # They are only shown initially for user awareness, but skipped during verification.
    
    if unsubscribed_channels:
        # Still not subscribed to some channels
        missing_channels_text = "\n".join([f"• {ch['title']}" for ch in unsubscribed_channels[:3]])  # Show first 3
        if len(unsubscribed_channels) > 3:
            missing_channels_text += f"\n... va yana {len(unsubscribed_channels) - 3} ta kanal"
        
        await safe_answer_callback_query(
            callback_query,
            f"❌ {len(unsubscribed_channels)} ta kanalga obuna bo'lmadingiz:\n{missing_channels_text}",
            show_alert=True
        )
        
        # Update the message with fresh subscription info (only for Telegram channels)
        # Filter out Instagram profiles from the list for display
        telegram_only_channels = [ch for ch in unsubscribed_channels if ch.get('type') != 'instagram']
        if telegram_only_channels:
            await update_subscription_message(callback_query, db, telegram_only_channels)
        else:
            # All Telegram channels are subscribed, Instagram profiles are ignored
            logger.info(f"User {target_user_id} passed all Telegram subscription checks (Instagram ignored)")
            await safe_answer_callback_query(callback_query, "✅ Barcha Telegram kanallarga obuna bo'lgansiz! Instagram profillar tekshirilmadi.")
            
            # Delete subscription message and proceed
            try:
                await callback_query.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete subscription message: {e}")
                try:
                    await callback_query.message.edit_text(
                        f"✅ {callback_query.from_user.first_name}, barcha Telegram kanallarga obuna bo'lgansiz!\n\n"
                        f"📸 Instagram profillarga obuna manual tekshiriladi.\n\n"
                        f"🎉 Endi botdan to'liq foydalanishingiz mumkin. Video havolasini qayta yuboring!"
                    )
                except:
                    pass
    else:
        # All Telegram subscriptions are good, Instagram profiles are not checked!
        logger.info(f"User {target_user_id} passed all Telegram subscription checks")
        await safe_answer_callback_query(callback_query, "✅ Barcha Telegram kanallarga obuna bo'lgansiz!")
        
        # Now automatically process the video that was blocked by subscription check
        try:
            # Use stored URL if available, otherwise try to find in reply message
            original_url = stored_url
            original_message = None
            
            # Check if this is a reply to a message with URL
            if (callback_query.message.reply_to_message and 
                callback_query.message.reply_to_message.text):
                original_message = callback_query.message.reply_to_message
                if not original_url:
                    urls = URLValidator.extract_urls_from_text(original_message.text)
                    if urls:
                        original_url = urls[0]
            
            # If we found the original URL and message, process it
            if original_url and original_message:
                logger.info(f"Auto-processing video after subscription check: {original_url} for user {target_user_id}")
                
                # Delete the subscription message since user is now subscribed
                try:
                    await callback_query.message.delete()
                except Exception as e:
                    logger.warning(f"Could not delete subscription message: {e}")
                
                # Process the video automatically
                if userbot:
                    await process_video_with_userbot(
                        original_message, original_url, callback_query.from_user.id, db, userbot
                    )
                else:
                    await process_video_after_subscription_check(
                        original_message, original_url, callback_query.from_user.id, db
                    )
            else:
                # No original URL found, just show success message
                try:
                    await callback_query.message.delete()
                except Exception as e:
                    logger.warning(f"Could not delete subscription message: {e}")
                    # If deletion fails, edit the message to show success
                    try:
                        await callback_query.message.edit_text(
                            f"✅ {callback_query.from_user.first_name}, siz barcha kanallarga obuna bo'lgansiz!\n\n"
                            f"🎉 Endi botdan to'liq foydalanishingiz mumkin. Video havolasini yuboring!"
                        )
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Error in auto-processing after subscription check: {e}")
            # Fallback to success message
            try:
                await callback_query.message.edit_text(
                    f"✅ {callback_query.from_user.first_name}, siz barcha kanallarga obuna bo'lgansiz!\n\n"
                    f"🎉 Endi botdan to'liq foydalanishingiz mumkin. Video havolasini qayta yuboring!"
                )
            except:
                pass

async def update_subscription_message(callback_query: CallbackQuery, db: Database, unsubscribed_channels: list):
    """Update subscription message with current status (only Telegram channels)."""
    try:
        # Filter to show only Telegram channels (Instagram profiles are not re-checked)
        telegram_channels = [ch for ch in unsubscribed_channels if ch.get('type') != 'instagram']
        
        if not telegram_channels:
            # No Telegram channels to show, user passed all checks
            logger.info(f"No Telegram channels left to check for user {callback_query.from_user.id}")
            try:
                await callback_query.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete subscription message: {e}")
            return
        
        # Recreate subscription message with updated buttons (only Telegram channels)
        if callback_query.message.chat.type in ['group', 'supergroup']:
            # Group message format
            unsubscribe_text = f"🔒 {callback_query.from_user.first_name}, video olish uchun quyidagi Telegram kanallarga obuna bo'ling:\n\n"
        else:
            # Private chat format
            unsubscribe_text = "🔒 Iltimos, quyidagi Telegram kanallarga obuna bo'ling:\n\n"
        
        keyboard_buttons = []
        
        for channel in telegram_channels:
            if channel['username']:
                # Telegram channel with username
                unsubscribe_text += f"• @{channel['username']}\n"
                keyboard_buttons.append([InlineKeyboardButton(
                    text=f"📢 {channel['title']}", 
                    url=f"https://t.me/{channel['username']}"
                )])
            else:
                # Telegram channel with invite link
                unsubscribe_text += f"• {channel['title']}\n"
                if channel['invite_link']:
                    keyboard_buttons.append([InlineKeyboardButton(
                        text=f"📢 {channel['title']}", 
                        url=channel['invite_link']
                    )])
        
        # Add check subscription button
        if callback_query.message.chat.type in ['group', 'supergroup']:
            # User-specific check for groups
            keyboard_buttons.append([InlineKeyboardButton(
                text="✅ Obunani tekshirish", 
                callback_data=f"check_sub_{callback_query.from_user.id}_refresh"
            )])
        else:
            # General check for private chats
            keyboard_buttons.append([InlineKeyboardButton(
                text="✅ Obunani tekshirish", 
                callback_data="check_subscription_refresh"
            )])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        unsubscribe_text += "\n👆 Obunadan so'ng, 'Obunani tekshirish' tugmasini bosing."
        
        await callback_query.message.edit_text(unsubscribe_text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Failed to update subscription message: {e}")

async def process_video_after_subscription_check(original_message, url, user_id, db):
    """Process video automatically after user passes subscription check."""
    try:
        # Import userbot from the message context
        from userbot.client import DownloaderUserbot
        
        # Get userbot instance - we need to access the global instance
        # This is a workaround since we don't have direct access to userbot here
        logger.info(f"Starting auto-processing for user {user_id} with URL: {url}")
        
        # Normalize URL
        normalized_url = URLValidator.normalize_url(url)
        if not normalized_url:
            await original_message.reply(
                f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                "havola yaroqsiz."
            )
            return
        
        # Get URL type
        url_type = URLValidator.get_url_type(url)
        if not url_type:
            await original_message.reply(
                f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                "qo'llab-quvvatlanmaydigan havola."
            )
            return
        
        # Add user to database
        await db.add_or_update_user(
            user_id=user_id,
            username=original_message.from_user.username,
            first_name=original_message.from_user.first_name,
            last_name=original_message.from_user.last_name
        )
        
        # For non-YouTube URLs, check cache and process
        if url_type in ['instagram', 'tiktok', 'facebook', 'twitter']:
            existing_video = await db.get_video(normalized_url)
            
            if existing_video:
                channel_message_id, timestamp = existing_video
                logger.info(f"Found existing {url_type} video for {normalized_url} (message_id: {channel_message_id})")
                try:
                    # Copy video from storage channel
                    await original_message.bot.copy_message(
                        chat_id=original_message.chat.id,
                        from_chat_id=Config.STORAGE_CHANNEL_ID,
                        message_id=channel_message_id,
                        reply_to_message_id=original_message.message_id
                    )
                    logger.info(f"Sent cached {url_type} video to chat {original_message.chat.id} for user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to forward cached video: {e}")
                    await original_message.reply(
                        f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                        "video keshdan topildi lekin yuborishda xatolik."
                    )
                return
            
            # Not in cache, need to process - but we don't have userbot access here
            # Send a message asking user to try again
            await original_message.reply(
                f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                "obuna muvaffaqiyatli! Iltimos video havolasini qayta yuboring."
            )
        
        elif url_type == 'youtube':
            # For YouTube, we need format selection - but we can't access userbot here directly
            await original_message.reply(
                f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                "obuna muvaffaqiyatli! YouTube video uchun havolani qayta yuboring va formatni tanlang."
            )
        
    except Exception as e:
        logger.error(f"Error in process_video_after_subscription_check: {e}")
        try:
            await original_message.reply(
                f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                "obuna muvaffaqiyatli! Iltimos video havolasini qayta yuboring."
            )
        except:
            pass

async def process_video_with_userbot(original_message, url, user_id, db, userbot):
    """Process video with userbot after subscription check."""
    try:
        logger.info(f"Processing video with userbot for user {user_id}: {url}")
        
        # Normalize URL
        normalized_url = URLValidator.normalize_url(url)
        if not normalized_url:
            await original_message.reply(
                f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                "havola yaroqsiz."
            )
            return
        
        # Get URL type
        url_type = URLValidator.get_url_type(url)
        if not url_type:
            await original_message.reply(
                f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                "qo'llab-quvvatlanmaydigan havola."
            )
            return
        
        # Add user to database
        await db.add_or_update_user(
            user_id=user_id,
            username=original_message.from_user.username,
            first_name=original_message.from_user.first_name,
            last_name=original_message.from_user.last_name
        )
        
        # For YouTube, show format selection
        if url_type == 'youtube':
            await show_youtube_formats(original_message, normalized_url, userbot, db)
            return
        
        # For other platforms, check cache and process
        if url_type in ['instagram', 'tiktok', 'facebook', 'twitter']:
            existing_video = await db.get_video(normalized_url)
            
            if existing_video:
                channel_message_id, timestamp = existing_video
                logger.info(f"Found existing {url_type} video for {normalized_url} (message_id: {channel_message_id})")
                try:
                    # Copy video from storage channel
                    await original_message.bot.copy_message(
                        chat_id=original_message.chat.id,
                        from_chat_id=Config.STORAGE_CHANNEL_ID,
                        message_id=channel_message_id,
                        reply_to_message_id=original_message.message_id
                    )
                    logger.info(f"Sent cached {url_type} video to chat {original_message.chat.id} for user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to forward cached video: {e}")
                    await original_message.reply(
                        f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                        "video keshdan topildi lekin yuborishda xatolik."
                    )
                return
            
            # Not in cache, queue for processing
            await queue_processing_request(
                user_id=user_id,
                message=original_message,
                url=normalized_url,
                url_type=url_type,
                userbot=userbot,
                db=db
            )
        
    except Exception as e:
        logger.error(f"Error in process_video_with_userbot: {e}")
        try:
            await original_message.reply(
                f"@{original_message.from_user.username or original_message.from_user.first_name}, "
                "xatolik yuz berdi. Iltimos qayta urinib ko'ring."
            )
        except:
            pass

# Reaction processing functions have been removed
# Bot now processes videos directly without reaction storage

async def delete_message_after_delay(message, delay_seconds):
    """Delete message after specified delay."""
    try:
        import asyncio
        await asyncio.sleep(delay_seconds)
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete delayed message: {e}")

# Message Reaction Updated Handler (DISABLED - reaction functionality removed)
# The reaction handler has been disabled to simplify the bot workflow
# Bot now processes videos directly without waiting for user reactions

def create_fake_message_for_reaction(reaction_update, url):
    """Create a fake message object for reaction processing."""
    class FakeMessage:
        def __init__(self, reaction_update, url):
            self.message_id = reaction_update.message_id
            self.chat = reaction_update.chat
            self.from_user = reaction_update.user
            self.text = url
            self.bot = reaction_update.bot
            
        async def reply(self, text, reply_to_message_id=None, reply_markup=None):
            return await self.bot.send_message(
                chat_id=self.chat.id,
                text=text,
                reply_to_message_id=reply_to_message_id or self.message_id,
                reply_markup=reply_markup
            )
    
    return FakeMessage(reaction_update, url)

async def check_user_subscriptions(user_id, mandatory_channels, bot):
    """Check user subscription to mandatory channels."""
    unsubscribed_channels = []
    
    for channel_data in mandatory_channels:
        channel_id = channel_data[1]
        channel_type = channel_data[2]
        channel_username = channel_data[3]
        channel_title = channel_data[4]
        invite_link = channel_data[5]
        
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                unsubscribed_channels.append({
                    'id': channel_id,
                    'type': channel_type,
                    'username': channel_username,
                    'title': channel_title,
                    'invite_link': invite_link
                })
        except Exception as e:
            logger.warning(f"Could not check subscription for channel {channel_id}: {e}")
            unsubscribed_channels.append({
                'id': channel_id,
                'type': channel_type,
                'username': channel_username,
                'title': channel_title,
                'invite_link': invite_link
            })
    
    return unsubscribed_channels

async def send_subscription_message_for_reaction(reaction_update, unsubscribed_channels, url, db):
    """Send subscription message for reaction-triggered processing."""
    try:
        user_id = reaction_update.user.id
        chat_id = reaction_update.chat.id
        
        # Create subscription message
        if reaction_update.chat.type in ['group', 'supergroup']:
            unsubscribe_text = f"🔒 {reaction_update.user.first_name}, video olish uchun avval quyidagi kanallarga obuna bo'ling:\n\n"
        else:
            unsubscribe_text = "🔒 Iltimos, quyidagi kanallarga obuna bo'ling:\n\n"
        
        keyboard_buttons = []
        
        for channel in unsubscribed_channels:
            if channel['username']:
                unsubscribe_text += f"• @{channel['username']}\n"
                keyboard_buttons.append([InlineKeyboardButton(
                    text=f"📢 {channel['title']}", 
                    url=f"https://t.me/{channel['username']}"
                )])
            else:
                unsubscribe_text += f"• {channel['title']}\n"
                if channel['invite_link']:
                    keyboard_buttons.append([InlineKeyboardButton(
                        text=f"📢 {channel['title']}", 
                        url=channel['invite_link']
                    )])
        
        # Add subscription check button with URL for auto-processing after subscription
        import base64
        url_encoded = base64.b64encode(url.encode()).decode()[:20]
        
        if reaction_update.chat.type in ['group', 'supergroup']:
            keyboard_buttons.append([InlineKeyboardButton(
                text="✅ Obunani tekshirish va yuklanishni boshlash", 
                callback_data=f"check_sub_reaction_{user_id}_{url_encoded}"
            )])
        else:
            keyboard_buttons.append([InlineKeyboardButton(
                text="✅ Obunani tekshirish va yuklanishni boshlash", 
                callback_data=f"check_subscription_reaction_{url_encoded}"
            )])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        unsubscribe_text += "\n👆 Obunadan so'ng, 'Obunani tekshirish' tugmasini bosing."
        
        await reaction_update.bot.send_message(
            chat_id=chat_id,
            text=unsubscribe_text,
            reply_to_message_id=reaction_update.message_id,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error sending subscription message for reaction: {e}")

async def process_video_from_reaction(fake_message, url, url_type, user_id, db, userbot, reaction_update):
    """Process video from reaction trigger."""
    try:
        logger.info(f"Processing video from reaction: {url} for user {user_id}")
        
        # Add user to database
        await db.add_or_update_user(
            user_id=user_id,
            username=fake_message.from_user.username,
            first_name=fake_message.from_user.first_name,
            last_name=fake_message.from_user.last_name
        )
        
        # For YouTube, show format selection
        if url_type == 'youtube':
            await show_youtube_formats(fake_message, url, userbot, db)
            return
        
        # For other platforms, check cache and process
        if url_type in ['instagram', 'tiktok', 'facebook', 'twitter']:
            existing_video = await db.get_video(url)
            
            if existing_video:
                channel_message_id, timestamp = existing_video
                logger.info(f"Found existing {url_type} video for {url} (message_id: {channel_message_id})")
                try:
                    # Copy video from storage channel
                    await fake_message.bot.copy_message(
                        chat_id=fake_message.chat.id,
                        from_chat_id=Config.STORAGE_CHANNEL_ID,
                        message_id=channel_message_id,
                        reply_to_message_id=fake_message.message_id
                    )
                    logger.info(f"Sent cached {url_type} video to chat {fake_message.chat.id} for user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to forward cached video: {e}")
                    await fake_message.reply(
                        f"@{fake_message.from_user.username or fake_message.from_user.first_name}, "
                        "video keshdan topildi lekin yuborishda xatolik."
                    )
                return
            
            # Not in cache, queue for processing
            await queue_processing_request(
                user_id=user_id,
                message=fake_message,
                url=url,
                url_type=url_type,
                userbot=userbot,
                db=db
            )
        
    except Exception as e:
        logger.error(f"Error processing video from reaction: {e}")
        try:
            await fake_message.reply(
                f"@{fake_message.from_user.username or fake_message.from_user.first_name}, "
                "xatolik yuz berdi. Iltimos qayta urinib ko'ring."
            )
        except:
            pass

@router.inline_query(F.query)
async def handle_inline_query(inline_query: InlineQuery, db: Database):
    """Handle inline queries for searching videos by URL."""
    query_url = inline_query.query.strip()
    
    if not URLValidator.is_instagram_url(query_url):
        return
    
    normalized_url = URLValidator.normalize_url(query_url)
    if not normalized_url:
        return
    
    # Check if video exists
    existing_video = await db.get_video(normalized_url)
    
    if existing_video:
        channel_message_id, _ = existing_video
        
        # Get message from storage to get file_id
        # Note: This part requires the bot to have access to the storage channel
        try:
            # To get the file_id, we need to fetch the message from the channel
            # This can be slow, so a better approach would be to store file_id in DB
            # For now, we will assume we can cache the video
            cached_video = await inline_query.bot.get_file(channel_message_id)
            video_file_id = cached_video.file_id
            
            result = InlineQueryResultCachedVideo(
                id=str(channel_message_id),
                video_file_id=video_file_id,
                title="Keshdagi Instagram Video",
                description=f"{normalized_url} dan video",
            )
            await inline_query.answer([result], cache_time=3600)
            
        except Exception as e:
            logger.error(f"Failed to get video for inline query: {e}")
    else:
        # Optionally, inform user that the video is not yet processed
        pass


# --- Admin Panel Functions ---

@logger.catch
async def show_admin_panel(message: Message, db: Database):
    """Show admin panel with statistics and options"""
    # Get today's statistics
    today_stats = await db.get_today_stats()
    platform_stats = await db.get_platform_stats()
    total_users = await db.get_total_users_count()
    total_videos = await db.get_video_count()
    
    # Format statistics text
    admin_text = "🔐 <b>Admin Panel</b>\n\n"
    admin_text += "📊 <b>Bugungi statistika:</b>\n"
    admin_text += f"👥 Yangi foydalanuvchilar: {today_stats.get('new_users', 0)}\n"
    admin_text += f"⬇️ Bugungi yuklamalar: {today_stats.get('total_downloads', 0)}\n\n"
    
    admin_text += "🎯 <b>Bugungi platformalar:</b>\n"
    admin_text += f"📸 Instagram: {today_stats.get('instagram_downloads', 0)} ta\n"
    admin_text += f"🎥 YouTube: {today_stats.get('youtube_downloads', 0)} ta\n"
    admin_text += f"🎵 TikTok: {today_stats.get('tiktok_downloads', 0)} ta\n\n"
    
    admin_text += "📈 <b>Barcha vaqt statistikasi:</b>\n"
    for platform, count in platform_stats.items():
        if platform == 'instagram':
            admin_text += f"📸 Instagram: {count} ta\n"
        elif platform == 'youtube':
            admin_text += f"🎥 YouTube: {count} ta\n"
        elif platform == 'tiktok':
            admin_text += f"🎵 TikTok: {count} ta\n"
        else:
            admin_text += f"❓ {platform.title()}: {count} ta\n"
    
    admin_text += f"\n📁 <b>Umumiy ma'lumotlar:</b>\n"
    admin_text += f"👥 Jami foydalanuvchilar: {total_users}\n"
    admin_text += f"🎬 Jami videolar: {total_videos}\n"
    
    # Create admin keyboard
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 Xabar Yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔒 Majburiy Obuna", callback_data="admin_mandatory")],
        [InlineKeyboardButton(text="📸 Instagram Majburiy", callback_data="admin_instagram_mandatory")],
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="admin_refresh")]
    ])
    
    await message.reply(admin_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin_"))
@logger.catch
async def handle_admin_callback(callback_query: CallbackQuery, state: FSMContext, db: Database):
    """Handle admin panel callbacks"""
    logger.info(f"Admin callback received: {callback_query.data} from user {callback_query.from_user.id}")
    
    if callback_query.from_user.id not in Config.ADMIN_IDS:
        logger.warning(f"Unauthorized admin access attempt from user {callback_query.from_user.id}")
        return await safe_answer_callback_query(callback_query, "🚫 Ruxsat berilmagan!", show_alert=True)
    
    action = callback_query.data.split("_")[1]
    logger.info(f"Processing admin action: {action}")
    
    if action == "refresh":
        await safe_answer_callback_query(callback_query, "🔄 Yangilanmoqda...")
        await show_admin_panel_edit(callback_query.message, db)
    
    elif action == "users":
        await safe_answer_callback_query(callback_query, "👥 Foydalanuvchilar ro'yxati...")
        await state.update_data(user_offset=0)
        await show_users_list(callback_query.message, db, 0)
    
    elif action == "broadcast":
        await safe_answer_callback_query(callback_query, "📢 Xabarni kiriting...")
        await state.set_state(AdminForm.waiting_broadcast)
        await callback_query.message.reply("✏️ Yubormoqchi bo'lgan xabaringizni kiriting:")
    
    elif action == "users_page":
        page = int(callback_query.data.split("_")[2])
        offset = page * 10
        await safe_answer_callback_query(callback_query, f"📄 {page + 1}-sahifa...")
        await state.update_data(user_offset=offset)
        await show_users_list_edit(callback_query.message, db, offset)
    
    
    elif action == "mandatory":
        await safe_answer_callback_query(callback_query, "🔒 Majburiy obuna...")
        await list_mandatory_channels(callback_query.message, db)
    elif action == "instagram" and len(callback_query.data.split("_")) > 2 and callback_query.data.split("_")[2] == "mandatory":
        await safe_answer_callback_query(callback_query, "📸 Instagram majburiy...")
        await show_instagram_mandatory_panel(callback_query.message, db)
    elif action == "back":
        await safe_answer_callback_query(callback_query, "⬅️ Orqaga...")
        await show_admin_panel_edit(callback_query.message, db)






@logger.catch
async def show_admin_panel_edit(message: Message, db: Database):
    """Edit admin panel message with new statistics"""
    # Get today's statistics
    today_stats = await db.get_today_stats()
    platform_stats = await db.get_platform_stats()
    total_users = await db.get_total_users_count()
    total_videos = await db.get_video_count()
    
    # Add current timestamp to ensure content is always different
    from datetime import datetime
    current_time = datetime.now().strftime("%H:%M:%S")
    
    # Format statistics text
    admin_text = f"🔐 <b>Admin Panel</b> (🕐 {current_time})\n\n"
    admin_text += "📊 <b>Bugungi statistika:</b>\n"
    admin_text += f"👥 Yangi foydalanuvchilar: {today_stats.get('new_users', 0)}\n"
    admin_text += f"⬇️ Bugungi yuklamalar: {today_stats.get('total_downloads', 0)}\n\n"
    
    admin_text += "🎯 <b>Bugungi platformalar:</b>\n"
    admin_text += f"📸 Instagram: {today_stats.get('instagram_downloads', 0)} ta\n"
    admin_text += f"🎥 YouTube: {today_stats.get('youtube_downloads', 0)} ta\n"
    admin_text += f"🎵 TikTok: {today_stats.get('tiktok_downloads', 0)} ta\n\n"
    
    admin_text += "📈 <b>Barcha vaqt statistikasi:</b>\n"
    for platform, count in platform_stats.items():
        if platform == 'instagram':
            admin_text += f"📸 Instagram: {count} ta\n"
        elif platform == 'youtube':
            admin_text += f"🎥 YouTube: {count} ta\n"
        elif platform == 'tiktok':
            admin_text += f"🎵 TikTok: {count} ta\n"
        else:
            admin_text += f"❓ {platform.title()}: {count} ta\n"
    
    admin_text += f"\n📁 <b>Umumiy ma'lumotlar:</b>\n"
    admin_text += f"👥 Jami foydalanuvchilar: {total_users}\n"
    admin_text += f"🎬 Jami videolar: {total_videos}\n"
    
    # Create admin keyboard
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 Xabar Yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔒 Majburiy Obuna", callback_data="admin_mandatory")],
        [InlineKeyboardButton(text="📸 Instagram Majburiy", callback_data="admin_instagram_mandatory")],
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="admin_refresh")]
    ])
    
    try:
        await message.edit_text(admin_text, reply_markup=keyboard)
    except Exception as e:
        # If editing fails (e.g., content is identical), just ignore the error
        logger.warning(f"Failed to edit admin panel message: {e}")


async def show_users_list(message: Message, db: Database, offset: int = 0):
    """Show users list with pagination"""
    users = await db.get_users_paginated(offset=offset, limit=10)
    total_users = await db.get_total_users_count()
    
    if not users:
        await message.reply("👥 Hech qanday foydalanuvchi topilmadi.")
        return
    
    users_text = f"👥 <b>Foydalanuvchilar ro'yxati</b> ({offset + 1}-{min(offset + 10, total_users)} / {total_users})\n\n"
    
    for user in users:
        user_id, username, first_name, last_name, downloads, first_interaction = user
        
        # Format user display name
        if username:
            user_display = f"@{username}"
        elif first_name:
            user_display = first_name
            if last_name:
                user_display += f" {last_name}"
        else:
            user_display = f"ID: {user_id}"
        
        users_text += f"👤 <a href='tg://user?id={user_id}'>{user_display}</a>\n"
        users_text += f"📊 Yuklashlar: {downloads}\n"
        users_text += f"📅 Birinchi kirgan: {first_interaction[:10]}\n\n"
    
    # Create pagination keyboard
    keyboard_buttons = []
    
    # Navigation buttons
    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"admin_users_page_{(offset - 10) // 10}"))
    
    if offset + 10 < total_users:
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"admin_users_page_{(offset + 10) // 10}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    # Back button
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.reply(users_text, reply_markup=keyboard)


async def show_users_list_edit(message: Message, db: Database, offset: int = 0):
    """Edit users list message with pagination"""
    users = await db.get_users_paginated(offset=offset, limit=10)
    total_users = await db.get_total_users_count()
    
    if not users:
        await message.edit_text("👥 Hech qanday foydalanuvchi topilmadi.")
        return
    
    users_text = f"👥 <b>Foydalanuvchilar ro'yxati</b> ({offset + 1}-{min(offset + 10, total_users)} / {total_users})\n\n"
    
    for user in users:
        user_id, username, first_name, last_name, downloads, first_interaction = user
        
        # Format user display name
        if username:
            user_display = f"@{username}"
        elif first_name:
            user_display = first_name
            if last_name:
                user_display += f" {last_name}"
        else:
            user_display = f"ID: {user_id}"
        
        users_text += f"👤 <a href='tg://user?id={user_id}'>{user_display}</a>\n"
        users_text += f"📊 Yuklashlar: {downloads}\n"
        users_text += f"📅 Birinchi kirgan: {first_interaction[:10]}\n\n"
    
    # Create pagination keyboard
    keyboard_buttons = []
    
    # Navigation buttons
    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"admin_users_page_{(offset - 10) // 10}"))
    
    if offset + 10 < total_users:
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"admin_users_page_{(offset + 10) // 10}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    # Back button
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.edit_text(users_text, reply_markup=keyboard)


# --- Broadcast Helper Functions ---

def get_message_type(message: Message) -> str:
    """Get message content type for display"""
    if message.photo:
        return "📸 Rasm + Matn"
    elif message.video:
        return "🎥 Video + Matn"
    elif message.audio:
        return "🎵 Audio + Matn"
    elif message.document:
        return "📄 Fayl + Matn"
    elif message.text:
        return "📝 Matn"
    else:
        return "❓ Noma'lum"


async def start_broadcast(message: Message, db: Database, broadcast_message_id: int):
    """Start broadcasting message to all users"""
    try:
        # Get all users
        all_users = await db.get_all_users()
        total_users = len(all_users)
        
        if total_users == 0:
            return await message.edit_text("👥 Hech qanday foydalanuvchi topilmadi.")
        
        # Initialize counters
        success_count = 0
        failed_count = 0
        blocked_count = 0
        
        # Update status message
        status_message = await message.edit_text(
            f"📤 <b>Xabar yuborilmoqda...</b>\n\n"
            f"👥 Jami foydalanuvchilar: {total_users}\n"
            f"✅ Yuborildi: {success_count}\n"
            f"❌ Xatolik: {failed_count}\n"
            f"🚫 Bloklagan: {blocked_count}\n\n"
            f"⏳ Jarayon davom etmoqda..."
        )
        
        # Send message to each user
        for i, user in enumerate(all_users):
            user_id = user[0]  # user_id is first column
            
            try:
                # Copy the broadcast message to user
                await message.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=broadcast_message_id
                )
                success_count += 1
                
            except Exception as e:
                error_msg = str(e).lower()
                if "blocked" in error_msg or "user is deactivated" in error_msg:
                    blocked_count += 1
                else:
                    failed_count += 1
                    logger.error(f"Failed to send broadcast to user {user_id}: {e}")
            
            # Update status every 10 users or at the end
            if (i + 1) % 10 == 0 or i == total_users - 1:
                try:
                    await status_message.edit_text(
                        f"📤 <b>Xabar yuborilmoqda...</b>\n\n"
                        f"👥 Jami foydalanuvchilar: {total_users}\n"
                        f"✅ Yuborildi: {success_count}\n"
                        f"❌ Xatolik: {failed_count}\n"
                        f"🚫 Bloklagan: {blocked_count}\n\n"
                        f"📊 Jarayon: {i + 1}/{total_users} ({((i + 1) / total_users * 100):.1f}%)"
                    )
                except:
                    pass  # Ignore edit errors
            
            # Small delay to avoid hitting rate limits
            await asyncio.sleep(0.05)
        
        # Final status update
        await status_message.edit_text(
            f"✅ <b>Xabar yuborish yakunlandi!</b>\n\n"
            f"👥 Jami foydalanuvchilar: {total_users}\n"
            f"✅ Muvaffaqiyatli yuborildi: {success_count}\n"
            f"❌ Xatoliklar: {failed_count}\n"
            f"🚫 Bot bloklaganlar: {blocked_count}\n\n"
            f"📊 Muvaffaqiyat darajasi: {(success_count / total_users * 100):.1f}%"
        )
        
        logger.info(f"Broadcast completed: {success_count}/{total_users} successful")
        
    except Exception as e:
        logger.error(f"Error during broadcast: {e}")
        await message.edit_text(
            f"❌ <b>Xabar yuborishda xatolik yuz berdi!</b>\n\n"
            f"Xatolik: {str(e)}"
        )


# --- Processing Queue Functions ---

async def start_processing_workers():
    """Start background workers to process the queue."""
    global processing_workers_started
    if not processing_workers_started:
        processing_workers_started = True
        # Start a single worker that processes one request at a time
        asyncio.create_task(process_queue_worker())
        logger.info("Processing queue worker started")

async def process_queue_worker():
    """Background worker that processes requests from the queue one by one."""
    global current_processing_user
    
    while True:
        try:
            # Wait for a request from the queue
            request = await processing_queue.get()
            
            # Set current processing user
            async with processing_lock:
                current_processing_user = request.user_id
            
            logger.info(f"Processing request for user {request.user_id}: {request.url}")
            
            try:
                # Process the request
                if request.url_type == 'instagram':
                    storage_message_id = await request.userbot.process_instagram_url(request.url)
                elif request.url_type == 'tiktok':
                    storage_message_id = await request.userbot.process_tiktok_url(request.url)
                elif request.url_type == 'facebook':
                    storage_message_id = await request.userbot.process_facebook_url(request.url)
                elif request.url_type == 'twitter':
                    storage_message_id = await request.userbot.process_twitter_url(request.url)
                else:
                    storage_message_id = None
                
                # Set result
                request.result = storage_message_id
                
                if storage_message_id:
                    # Add to database with platform info
                    await request.db.add_video(request.url, storage_message_id, platform=request.url_type)
                    
                    # Increment user download count
                    await request.db.increment_user_downloads(request.user_id)
                    
                    # Send result to user
                    await send_processed_result(request)
                else:
                    # Send error message
                    if request.message.chat.type == 'private':
                        await request.message.reply(
                            "Kechirasiz, so'rovingizni qayta ishlab bo'lmadi. "
                            "Iltimos, havolani tekshiring yoki keyinroq qayta urinib ko'ring."
                        )
                    else:
                        await request.message.reply(
                            f"{request.message.from_user.first_name}, videoni yuklab bo'lmadi. "
                            "Iltimos, boshqa havola yuboring."
                        )
                
                # Delete loading message if it exists
                if hasattr(request, 'loading_message') and request.loading_message:
                    try:
                        await request.loading_message.delete()
                        logger.info(f"Deleted loading message for user {request.user_id}")
                    except Exception as message_error:
                        logger.warning(f"Failed to delete loading message for user {request.user_id}: {message_error}")
                
            except Exception as e:
                logger.error(f"Error processing request for user {request.user_id}: {e}")
                request.error = str(e)
                if request.message.chat.type == 'private':
                    await request.message.reply(
                        "Kechirasiz, so'rovingizni qayta ishlanayotganda xatolik yuz berdi. "
                        "Iltimos, keyinroq qayta urinib ko'ring."
                    )
                else:
                    await request.message.reply(
                        f"{request.message.from_user.first_name}, xatolik yuz berdi. "
                        "Iltimos, keyinroq qayta urinib ko'ring."
                    )
            
            # Mark as completed
            request.completed.set()
            
            # Clear current processing user
            async with processing_lock:
                current_processing_user = None
                
            logger.info(f"Completed processing for user {request.user_id}")
            
        except Exception as e:
            logger.error(f"Error in queue worker: {e}")
            await asyncio.sleep(1)  # Brief pause before continuing

async def send_processed_result(request: ProcessingRequest):
    """Send the processed result to the user."""
    try:
        # Send single media for all platforms to avoid confusion
        # In groups, reply to the original message
        await request.message.bot.copy_message(
            chat_id=request.message.chat.id,
            from_chat_id=Config.STORAGE_CHANNEL_ID,
            message_id=request.result,
            reply_to_message_id=request.message.message_id
        )
        logger.info(f"Sent {request.url_type} media (message_id: {request.result}) to chat {request.message.chat.id} for user {request.user_id}")
    except Exception as e:
        logger.error(f"Failed to send processed result to user {request.user_id}: {e}")
        error_msg = "Video qayta ishlandi, lekin uni yuborib bo'lmadi. Iltimos, qayta urinib ko'ring."
        if request.message.chat.type == 'private':
            await request.message.reply(error_msg)
        else:
            await request.message.reply(f"{request.message.from_user.first_name}, {error_msg.lower()}")

async def queue_processing_request(user_id: int, message: Message, url: str, url_type: str, userbot, db):
    """Add a processing request to the queue."""
    # Start workers if not started
    await start_processing_workers()
    
    # Create request
    request = ProcessingRequest(user_id, message, url, url_type, userbot, db)
    
    # Check queue size and inform user
    queue_size = processing_queue.qsize()
    
    # Send loading message with emoji immediately
    if message.chat.type == 'private':
        loading_message = await message.answer("⌛️ Yuklanmoqda...")
    else:
        # In groups, reply to the original message with user mention
        loading_message = await message.reply(f"⌛️ {message.from_user.first_name}, video yuklanmoqda...")
    
    # Store loading message ID in request for later deletion
    request.loading_message = loading_message
    
    # Only show queue status if there are other requests waiting and in private chat
    if queue_size > 0 and message.chat.type == 'private':
        # There are other requests in queue
        await message.reply(
            f"Sizning so'rovingiz navbatga qo'shildi. "
            f"Navbatda {queue_size} ta so'rov bor. "
            f"Iltimos, kutib turing..."
        )
    
    # Add to queue
    await processing_queue.put(request)
    
    # Wait for completion (optional - for future use)
    # await request.completed.wait()
    
    return request

