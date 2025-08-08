"""Telethon userbot client for Instagram video processing."""

import asyncio
import os
import glob
from typing import Optional, Tuple
from telethon import TelegramClient
from telethon.types import Message, MessageMediaDocument, InputMediaUploadedPhoto, InputMediaUploadedDocument
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.errors.rpcerrorlist import AuthKeyDuplicatedError
from loguru import logger
from config import Config


class DownloaderUserbot:
    """Userbot client for processing Instagram and YouTube videos."""
    
    def __init__(self):
        """Initialize the userbot client."""
        self.client = TelegramClient(
            Config.SESSION_NAME,
            Config.API_ID,
            Config.API_HASH
        )
        self.keepmedia_bot_username = Config.TIKTOK_BOT_USERNAME  # Using KeepMediaBot for both Instagram and TikTok
        self.youtube_bot_username = Config.YOUTUBE_BOT_USERNAME
        self.facebook_bot_username = Config.FACEBOOK_BOT_USERNAME
        self.twitter_bot_username = Config.TWITTER_BOT_USERNAME
        self.storage_channel_id = Config.STORAGE_CHANNEL_ID
        self.is_authenticated = False
        
        # Storage for YouTube format callbacks
        self.format_callbacks = {}  # button_index -> (url, callback_data)
        self.youtube_requests = {}  # user_id -> (url, format_message)
        
        # Storage for Twitter format selections per user
        # user_id -> (url, format_message, {idx: (callback_data, button_text)})
        self.twitter_requests = {}
    
    async def start(self) -> bool:
        """
        Start the userbot client with proper state synchronization.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            self.client = TelegramClient(
                Config.SESSION_NAME, 
                Config.API_ID, 
                Config.API_HASH, 
                flood_sleep_threshold=120,
                # Disable update handling to prevent "very new message" warnings
                receive_updates=False
            )
            
            logger.info("Starting userbot...")
            await self.client.start()

            if not await self.client.is_user_authorized():
                logger.error("User not authorized. Please run `setup.py` first.")
                return False
            
            me = await self.client.get_me()
            username = f"@{me.username}" if me.username else "(no username)"
            logger.info(f"Userbot started successfully as {me.first_name} {username}")
            self.is_authenticated = True
            return True
            
        except FloodWaitError as e:
            logger.error(f"FloodWait from Telegram. Please wait {e.seconds} seconds.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during userbot startup: {type(e).__name__} - {e}")
            return False
    
    async def stop(self):
        """Stop the userbot client."""
        if self.client.is_connected():
            await self.client.disconnect()
            logger.info("Userbot stopped")
    
    async def authenticate_interactive(self, phone=None, code=None, password=None) -> bool:
        """
        Interactive authentication for first-time setup.
        
        Returns:
            True if authenticated successfully, False otherwise
        """
        try:
            await self.client.start()
            
            if not await self.client.is_user_authorized():
                if not phone:
                    phone = input("Telefon raqamingizni kiriting (mamlakat kodi bilan, masalan, +998901234567): ")
                await self.client.send_code_request(phone)
                
                if not code:
                    code = input("Qabul qilingan tasdiqlash kodini kiriting: ")
                try:
                    await self.client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    if not password:
                        password = input("2FA parolingizni kiriting: ")
                    await self.client.sign_in(password=password)
                
                me = await self.client.get_me()
                logger.info(f"Successfully authenticated as {me.first_name} (@{me.username})")
                return True
            else:
                me = await self.client.get_me()
                logger.info(f"Already authenticated as {me.first_name} (@{me.username})")
                return True
                
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False
    
    async def process_instagram_url(self, url: str, max_wait_time: int = 60) -> Optional[int]:
        """
        Process Instagram URL through @KeepMediaBot and upload to storage channel.
        
        Args:
            url: Instagram URL to process
            max_wait_time: Maximum time to wait for response in seconds
            
        Returns:
            Message ID of the uploaded media in storage channel, or None if failed
        """
        if not self.is_authenticated:
            logger.error("Userbot is not authenticated")
            return None
        
        max_retries = 2  # Try up to 2 times
        retry_delay = 10  # Wait 10 seconds before retry
        
        for attempt in range(max_retries):
            try:
                # First send /start command to @KeepMediaBot to ensure proper session
                logger.info(f"Sending /start command to @{self.keepmedia_bot_username} (attempt {attempt + 1}/{max_retries})")
                start_message = await self.client.send_message(self.keepmedia_bot_username, "/start")
                
                # Wait a moment for the start command to be processed
                await asyncio.sleep(2)
                
                # Send URL to @KeepMediaBot
                logger.info(f"Sending Instagram URL to @{self.keepmedia_bot_username}: {url} (attempt {attempt + 1}/{max_retries})")
                sent_message = await self.client.send_message(self.keepmedia_bot_username, url)
                
                # Wait for response with media (video or photo) - get all media messages for Instagram posts with multiple images
                media_messages = await self._wait_for_video_response(
                    self.keepmedia_bot_username, 
                    sent_message.id,
                    retry_delay,  # Wait only 10 seconds for initial response
                    return_all=True  # Get all media messages for Instagram carousel posts
                )
                
                if media_messages:
                    # Check if we have multiple media messages for Instagram carousel
                    if len(media_messages) > 1:
                        # Upload as media group for multiple images
                        storage_message_id = await self._upload_media_group_to_storage_channel(media_messages)
                        
                        if storage_message_id:
                            logger.info(f"Successfully processed Instagram {url} -> uploaded {len(media_messages)} media files as group (attempt {attempt + 1})")
                            return storage_message_id
                        else:
                            logger.error("Failed to upload media group to storage channel")
                            return None
                    else:
                        # Upload single media message
                        storage_message_id = await self._upload_to_storage_channel(media_messages[0])
                        
                        if storage_message_id:
                            logger.info(f"Successfully processed Instagram {url} -> uploaded single media file (attempt {attempt + 1})")
                            return storage_message_id
                        else:
                            logger.error("Failed to upload media to storage channel")
                            return None
                else:
                    logger.warning(f"No media response received from @{self.keepmedia_bot_username} on attempt {attempt + 1}")
                    if attempt < max_retries - 1:  # Don't wait after the last attempt
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    
            except FloodWaitError as e:
                logger.warning(f"Rate limited, need to wait {e.seconds} seconds")
                return None
            except Exception as e:
                logger.error(f"Error processing Instagram URL {url} on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        logger.error(f"Failed to process Instagram URL {url} after {max_retries} attempts")
        return None
    
    async def process_youtube_url(self, url: str, callback_data: str = None, max_wait_time: int = 60) -> Optional[int]:
        """
        Process YouTube URL through @SaveYoutubeBot and upload to storage channel.
        
        Args:
            url: YouTube URL to process
            callback_data: Callback data from inline button click (for format selection)
            max_wait_time: Maximum time to wait for response in seconds
            
        Returns:
            Message ID of the uploaded video in storage channel, or None if failed
        """
        if not self.is_authenticated:
            logger.error("Userbot is not authenticated")
            return None
        
        try:
            # First send /start command to @SaveYoutubeBot to ensure proper session
            logger.info(f"Sending /start command to @{self.youtube_bot_username}")
            start_message = await self.client.send_message(self.youtube_bot_username, "/start")
            
            # Wait a moment for the start command to be processed
            await asyncio.sleep(2)
            
            # Send URL to @SaveYoutubeBot
            logger.info(f"Sending URL to @{self.youtube_bot_username}: {url}")
            sent_message = await self.client.send_message(self.youtube_bot_username, url)
            
            if callback_data:
                # If callback_data is provided, we need to click an inline button
                # Wait for the format selection message first
                format_message = await self._wait_for_format_message(
                    self.youtube_bot_username,
                    sent_message.id,
                    max_wait_time
                )
                
                if not format_message:
                    logger.error("No format selection message received")
                    return None
                
                # Click the inline button
                clicked = await self._click_inline_button(format_message, callback_data)
                if not clicked:
                    logger.error("Failed to click inline button")
                    return None
            
            # Wait for response with video (give YouTube bot more time)
            video_message = await self._wait_for_video_response(
                self.youtube_bot_username,
                sent_message.id,
                30  # Wait up to 30 seconds for YouTube video processing
            )
            
            if not video_message:
                logger.error("No video response received from @SaveYoutubeBot")
                return None
            
            # Upload video to storage channel
            storage_message_id = await self._upload_to_storage_channel(video_message)
            
            if storage_message_id:
                logger.info(f"Successfully processed {url} -> storage message {storage_message_id}")
                return storage_message_id
            else:
                logger.error("Failed to upload video to storage channel")
                return None
                
        except FloodWaitError as e:
            logger.warning(f"Rate limited, need to wait {e.seconds} seconds")
            return None
        except Exception as e:
            logger.error(f"Error processing YouTube URL {url}: {e}")
            return None
    
    async def process_tiktok_url(self, url: str, max_wait_time: int = 60) -> Optional[int]:
        """
        Process TikTok URL through @KeepMediaBot and upload to storage channel.
        
        Args:
            url: TikTok URL to process
            max_wait_time: Maximum time to wait for response in seconds
            
        Returns:
            Message ID of the uploaded video in storage channel, or None if failed
        """
        if not self.is_authenticated:
            logger.error("Userbot is not authenticated")
            return None
        
        try:
            # First send /start command to @KeepMediaBot to ensure proper session
            logger.info(f"Sending /start command to @{self.keepmedia_bot_username}")
            start_message = await self.client.send_message(self.keepmedia_bot_username, "/start")
            
            # Wait a moment for the start command to be processed
            await asyncio.sleep(2)
            
            # Send TikTok URL to @KeepMediaBot
            logger.info(f"Sending TikTok URL to @{self.keepmedia_bot_username}: {url}")
            sent_message = await self.client.send_message(self.keepmedia_bot_username, url)
            
            # Wait for response with video
            video_message = await self._wait_for_video_response(
                self.keepmedia_bot_username, 
                sent_message.id,
                max_wait_time
            )
            
            if not video_message:
                logger.error(f"No video response received from @{self.keepmedia_bot_username}")
                return None
            
            # Upload video to storage channel
            storage_message_id = await self._upload_to_storage_channel(video_message)
            
            if storage_message_id:
                logger.info(f"Successfully processed TikTok {url} -> storage message {storage_message_id}")
                return storage_message_id
            else:
                logger.error("Failed to upload TikTok video to storage channel")
                return None
                
        except FloodWaitError as e:
            logger.warning(f"Rate limited, need to wait {e.seconds} seconds")
            return None
        except Exception as e:
            logger.error(f"Error processing TikTok URL {url}: {e}")
            return None
    
    async def process_facebook_url(self, url: str, max_wait_time: int = 60) -> Optional[int]:
        """
        Process Facebook URL through @FacebookAsBot and upload to storage channel.
        
        Args:
            url: Facebook URL to process
            max_wait_time: Maximum time to wait for response in seconds
            
        Returns:
            Message ID of the uploaded video in storage channel, or None if failed
        """
        if not self.is_authenticated:
            logger.error("Userbot is not authenticated")
            return None
        
        try:
            # First send /start command to @FacebookAsBot to ensure proper session
            logger.info(f"Sending /start command to @{self.facebook_bot_username}")
            start_message = await self.client.send_message(self.facebook_bot_username, "/start")
            
            # Wait a moment for the start command to be processed
            await asyncio.sleep(2)
            
            # Send Facebook URL to the configured bot (e.g., @VideoAsBot)
            logger.info(f"Sending Facebook URL to @{self.facebook_bot_username}: {url}")
            sent_message = await self.client.send_message(self.facebook_bot_username, url)
            
            # Wait for responses and collect all media messages (video/audio/photo)
            media_messages = await self._wait_for_video_response(
                self.facebook_bot_username,
                sent_message.id,
                max_wait_time,
                return_all=True
            )
            
            if not media_messages:
                logger.error(f"No media response received from @{self.facebook_bot_username}")
                return None
            
            # From newest to oldest, pick the last available MP4 video if exists, else fall back to latest media
            chosen_message = None
            for m in reversed(media_messages):
                try:
                    is_video = bool(m.video) or (m.document and hasattr(m.document, 'mime_type') and m.document.mime_type.startswith('video/'))
                    if is_video:
                        chosen_message = m
                        break
                except Exception:
                    continue
            if not chosen_message:
                # No video found, fall back to the newest media (may be audio/photo)
                chosen_message = media_messages[-1]
            
            # Upload chosen media to storage channel
            storage_message_id = await self._upload_to_storage_channel(chosen_message)
            
            if storage_message_id:
                logger.info(f"Successfully processed Facebook {url} -> storage message {storage_message_id}")
                return storage_message_id
            else:
                logger.error("Failed to upload Facebook video to storage channel")
                return None
                
        except AuthKeyDuplicatedError as e:
            logger.error("Userbot session is duplicated across different IPs. Attempting to reconnect once...")
            try:
                await self._recover_session()
                # Retry once without sending /start again to minimize traffic
                logger.info(f"Retrying Facebook URL after session recovery: {url}")
                sent_message = await self.client.send_message(self.facebook_bot_username, url)
                media_messages = await self._wait_for_video_response(
                    self.facebook_bot_username,
                    sent_message.id,
                    max_wait_time,
                    return_all=True
                )
                if not media_messages:
                    logger.error(f"No media response received from @{self.facebook_bot_username} after recovery")
                    return None
                chosen_message = None
                for m in reversed(media_messages):
                    try:
                        is_video = bool(m.video) or (m.document and hasattr(m.document, 'mime_type') and m.document.mime_type.startswith('video/'))
                        if is_video:
                            chosen_message = m
                            break
                    except Exception:
                        continue
                if not chosen_message:
                    chosen_message = media_messages[-1]
                storage_message_id = await self._upload_to_storage_channel(chosen_message)
                if storage_message_id:
                    logger.info(f"Successfully processed Facebook {url} -> storage message {storage_message_id} (after recovery)")
                    return storage_message_id
                return None
            except Exception as rec_e:
                logger.error(f"Session recovery failed: {rec_e}")
                return None
        except FloodWaitError as e:
            logger.warning(f"Rate limited, need to wait {e.seconds} seconds")
            return None
        except Exception as e:
            # Detect duplicated auth by message text in case specific class isn't raised
            if "authorization key" in str(e).lower() and "two different ip" in str(e).lower():
                logger.error("Detected duplicated auth key by error text. Attempting to reconnect once...")
                try:
                    await self._recover_session()
                    logger.info(f"Retrying Facebook URL after session recovery: {url}")
                    sent_message = await self.client.send_message(self.facebook_bot_username, url)
                    media_messages = await self._wait_for_video_response(
                        self.facebook_bot_username,
                        sent_message.id,
                        max_wait_time,
                        return_all=True
                    )
                    if not media_messages:
                        logger.error(f"No media response received from @{self.facebook_bot_username} after recovery")
                        return None
                    chosen_message = None
                    for m in reversed(media_messages):
                        try:
                            is_video = bool(m.video) or (m.document and hasattr(m.document, 'mime_type') and m.document.mime_type.startswith('video/'))
                            if is_video:
                                chosen_message = m
                                break
                        except Exception:
                            continue
                    if not chosen_message:
                        chosen_message = media_messages[-1]
                    storage_message_id = await self._upload_to_storage_channel(chosen_message)
                    if storage_message_id:
                        logger.info(f"Successfully processed Facebook {url} -> storage message {storage_message_id} (after recovery)")
                        return storage_message_id
                    return None
                except Exception as rec_e:
                    logger.error(f"Session recovery failed: {rec_e}")
                    return None
            logger.error(f"Error processing Facebook URL {url}: {e}")
            return None
    
    async def process_twitter_url(self, url: str, callback_data: str = None, max_wait_time: int = 60, pre_sent_message_id: int = None) -> Optional[int]:
        """
        Process Twitter/X URL through @twittervid_bot and upload to storage channel.
        
        Args:
            url: Twitter/X URL to process
            callback_data: optional callback data to click a specific format
            max_wait_time: Maximum time to wait for response in seconds
            pre_sent_message_id: If provided, DO NOT resend the URL. Reuse this message id to wait for responses.
            
        Returns:
            Message ID of the uploaded media in storage channel, or None if failed
        """
        if not self.is_authenticated:
            logger.error("Userbot is not authenticated")
            return None
        
        try:
            # Optionally reuse an already-sent request to avoid duplicate sends
            if pre_sent_message_id is not None:
                sent_message_id = pre_sent_message_id
                logger.info(f"Reusing existing Twitter request (message_id={sent_message_id}) for URL: {url}")
            else:
                logger.info(f"Sending Twitter URL to @{self.twitter_bot_username}: {url}")
                sent_message = await self.client.send_message(self.twitter_bot_username, url)
                sent_message_id = sent_message.id
            
            # If a specific format was selected, wait for the keyboard then click
            if callback_data:
                format_message = await self._wait_for_format_message(
                    self.twitter_bot_username,
                    sent_message_id,
                    60
                )
                if not format_message:
                    logger.error("No format selection message received from twitter bot")
                    return None
                clicked = await self._click_inline_button(format_message, callback_data)
                if not clicked:
                    logger.error("Failed to click selected Twitter format button")
                    return None
            
            # Wait for response(s) with media (video or photo) and caption
            media_messages = await self._wait_for_twitter_response(
                self.twitter_bot_username, 
                sent_message_id,
                max_wait_time,
                return_all=True,
                poll_interval=5
            )
            
            if not media_messages:
                logger.error(f"No media response received from @{self.twitter_bot_username}")
                return None
            
            # Prefer video, otherwise take latest photo
            chosen_message = None
            try:
                for m in reversed(media_messages):
                    is_video = bool(m.video) or (m.document and hasattr(m.document, 'mime_type') and m.document.mime_type.startswith('video/'))
                    if is_video:
                        chosen_message = m
                        break
            except Exception:
                pass
            if not chosen_message:
                chosen_message = media_messages[-1]
            
            # Upload media to storage channel with modified caption
            storage_message_id = await self._upload_twitter_to_storage_channel(chosen_message)
            
            if storage_message_id:
                logger.info(f"Successfully processed Twitter {url} -> storage message {storage_message_id}")
                return storage_message_id
            else:
                logger.error("Failed to upload Twitter media to storage channel")
                return None
                
        except FloodWaitError as e:
            logger.warning(f"Rate limited, need to wait {e.seconds} seconds")
            return None
        except Exception as e:
            logger.error(f"Error processing Twitter URL {url}: {e}")
            return None
    
    async def _wait_for_twitter_response(self, bot_username: str, sent_message_id: int, max_wait_time: int, return_all: bool = False, poll_interval: int = 5):
        """
        Wait for media response from Twitter bot. If return_all is True, return all media messages newer than sent_message_id.
        poll_interval controls how often to poll (seconds). Default 5s as requested.
        """
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
            try:
                messages = await self.client.get_messages(bot_username, limit=20)
                media_messages = []
                text_messages = []  # To store text-only responses
                
                for message in messages:
                    if message.id > sent_message_id:
                        # Check for actual media files
                        is_video = message.video or (message.document and hasattr(message.document, 'mime_type') and message.document.mime_type.startswith('video/'))
                        is_photo = message.photo or (message.document and hasattr(message.document, 'mime_type') and message.document.mime_type.startswith('image/'))
                        
                        # Skip MessageMediaWebPage - this indicates text-only or link preview
                        from telethon.tl.types import MessageMediaWebPage
                        if isinstance(message.media, MessageMediaWebPage):
                            logger.debug(f"Skipping MessageMediaWebPage (text-only post) from message {message.id}")
                            continue
                            
                        if is_video or is_photo:
                            media_messages.append(message)
                        elif message.message and not message.media:
                            # Check for text responses that might indicate no media available
                            text_content = message.message.lower()
                            if any(keyword in text_content for keyword in ['no media', 'not found', 'error', 'failed', 'no video', 'no photo']):
                                text_messages.append(message)
                                
                if media_messages:
                    media_messages.sort(key=lambda m: m.id)
                    if return_all:
                        logger.info(f"Found {len(media_messages)} twitter media message(s). Returning all.")
                        return media_messages
                    chosen = media_messages[-1]
                    mtype = 'video' if (chosen.video or (chosen.document and chosen.document.mime_type.startswith('video/'))) else 'photo'
                    logger.info(f"Found Twitter {mtype} message ID: {chosen.id}")
                    return chosen
                elif text_messages:
                    # Check if there's an error message indicating no media
                    logger.warning(f"Twitter bot responded with text message: {text_messages[-1].message[:100]}...")
                    return None  # Indicate no media available
                    
            except Exception as e:
                logger.error(f"Error while waiting for Twitter response: {e}")
            await asyncio.sleep(poll_interval)
            
        logger.warning(f"Timeout waiting for Twitter media response from @{bot_username} after {max_wait_time} seconds")
        return None
    
    async def _upload_twitter_to_storage_channel(self, media_message: Message) -> Optional[int]:
        """
        Upload Twitter media to storage channel with modified caption.
        
        Args:
            media_message: Message containing the Twitter media
            
        Returns:
            Message ID in storage channel or None if failed
        """
        try:
            # Check if this is a MessageMediaWebPage (text-only post)
            from telethon.tl.types import MessageMediaWebPage
            if isinstance(media_message.media, MessageMediaWebPage):
                logger.warning("Cannot upload MessageMediaWebPage - this is a text-only Twitter post")
                return None
            
            # Get original caption from Twitter bot
            original_caption = media_message.message or ""
            
            # Modify caption - replace bot name at the end with our bot name
            modified_caption = self._modify_twitter_caption(original_caption)
            
            file_type = "Media"
            
            # Determine file type based on message content
            if media_message.photo:
                file_type = "Photo"
            elif media_message.video:
                file_type = "Video"
            elif media_message.document:
                if hasattr(media_message.document, 'mime_type'):
                    if media_message.document.mime_type.startswith('video/'):
                        file_type = "Video"
                    elif media_message.document.mime_type.startswith('image/'):
                        file_type = "Photo"
                    else:
                        file_type = "Document"
            else:
                # No recognizable media type
                logger.warning(f"Twitter message has unsupported media type: {type(media_message.media)}")
                return None
            
            logger.info(f"Uploading Twitter {file_type.lower()} to storage channel with modified caption...")
            
            # Prefer the raw media object first
            media_obj = None
            if media_message.photo:
                media_obj = media_message.photo
            elif media_message.video:
                media_obj = media_message.video
            elif media_message.document:
                media_obj = media_message.document
            elif media_message.media:
                # Try using media attribute directly
                if not isinstance(media_message.media, MessageMediaWebPage):
                    media_obj = media_message.media
            
            if not media_obj:
                logger.warning("Twitter media message has no uploadable media object; attempting to download and re-send...")
                try:
                    downloaded = await self.client.download_media(media_message)
                    if downloaded:
                        media_obj = downloaded
                    else:
                        logger.error("Failed to download Twitter media")
                        return None
                except Exception as dl_error:
                    logger.error(f"Error downloading Twitter media: {dl_error}")
                    return None
            
            # Send the media file directly with modified caption
            sent_message = await self.client.send_file(
                self.storage_channel_id,
                media_obj,
                caption=modified_caption
            )
            
            if sent_message:
                storage_message_id = sent_message.id
                logger.info(f"Twitter {file_type} uploaded to storage channel with message ID: {storage_message_id}")
                return storage_message_id
            else:
                logger.error(f"Failed to upload Twitter {file_type.lower()} to storage channel")
                return None
                
        except Exception as e:
            logger.error(f"Error uploading Twitter media to storage channel: {e}")
            return None
    
    def _modify_twitter_caption(self, original_caption: str) -> str:
        """
        Modify Twitter caption by replacing bot name with our bot name.
        
        Args:
            original_caption: Original caption from @twittervid_bot
            
        Returns:
            Modified caption with our bot name
        """
        if not original_caption:
            return "📥 @BittadaBot tomonidan yuklab olindi"
        
        # Split caption into lines
        lines = original_caption.split('\n')
        
        # Find and replace the last line if it contains a bot name
        if lines:
            last_line = lines[-1].strip()
            
            # Check if the last line contains a bot mention or channel name
            # Common patterns: @botname, via @botname, by @botname, etc.
            if '@' in last_line or 'via' in last_line.lower() or 'by' in last_line.lower():
                # Replace the last line with our bot name
                lines[-1] = "\n📥 @BittadaBot tomonidan yuklab olindi"
            else:
                # Add our bot name to the end
                lines.append("\n📥 @BittadaBot tomonidan yuklab olindi")
        else:
            # If no caption, just add our bot name
            lines = ["📥 @BittadaBot tomonidan yuklab olindi"]
        
        return '\n'.join(lines)
    
    async def _wait_for_video_response(self, bot_username: str, sent_message_id: int, max_wait_time: int, return_all: bool = False) -> Optional[Message]:
        """
        Waits for a media response (video, photo, or audio) from a bot, checking the last few messages.

        Args:
            bot_username: Username of the bot.
            sent_message_id: ID of the message sent to the bot.
            max_wait_time: Maximum time to wait in seconds.
            return_all: If True, return all media messages; if False, return only the latest one.

        Returns:
            The selected Message object with the media (or list of messages if return_all=True), or None.
        """
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
            try:
                # Check the last 10 messages to account for multiple media files
                messages = await self.client.get_messages(bot_username, limit=10)
                
                media_messages = []
                for message in messages:
                    if message.id > sent_message_id:
                        # Check if the message contains any media
                        is_video = message.video or (message.document and hasattr(message.document, 'mime_type') and message.document.mime_type.startswith('video/'))
                        is_photo = message.photo or (message.document and hasattr(message.document, 'mime_type') and message.document.mime_type.startswith('image/'))
                        is_audio = message.audio or (message.document and hasattr(message.document, 'mime_type') and message.document.mime_type.startswith('audio/'))
                        
                        # For YouTube bot, prioritize video and audio over images (thumbnails)
                        if bot_username == self.youtube_bot_username:
                            # Only accept video or audio files from YouTube bot, ignore images (thumbnails)
                            if is_video or is_audio:
                                pass  # This is what we want
                            else:
                                continue  # Skip images/photos
                        
                        if is_video or is_photo or is_audio:
                            if is_video:
                                media_type = 'video'
                            elif is_audio:
                                media_type = 'audio'
                            else:
                                media_type = 'photo'
                            
                            logger.info(f"Found {media_type} message ID: {message.id}")
                            media_messages.append(message)
                
                # If any media messages were found, process them
                if media_messages:
                    # Sort messages by ID to ensure they are in chronological order
                    media_messages.sort(key=lambda m: m.id)
                    
                    if return_all:
                        logger.info(f"Found {len(media_messages)} media message(s). Returning all.")
                        return media_messages
                    else:
                        # Take the latest media message
                        chosen_message = media_messages[-1]
                        
                        # Determine media type for logging
                        if chosen_message.video or (chosen_message.document and chosen_message.document.mime_type.startswith('video/')):
                            media_type = 'video'
                        elif chosen_message.audio or (chosen_message.document and chosen_message.document.mime_type.startswith('audio/')):
                            media_type = 'audio'
                        else:
                            media_type = 'photo'
                        
                        logger.info(f"Found {len(media_messages)} media message(s). Selected {media_type} message ID: {chosen_message.id}")
                        return chosen_message

            except Exception as e:
                logger.error(f"Error while waiting for media response: {e}")
            
            # Wait before the next check
            await asyncio.sleep(3)

        logger.warning(f"Timeout waiting for media response from @{bot_username} after {max_wait_time} seconds")
        return None
    
    async def _wait_for_format_message(self, bot_username: str, sent_message_id: int, max_wait_time: int) -> Optional[Message]:
        """
        Wait for format selection message from a bot (YouTube/Twitter).
        Only returns a message if it has inline buttons with callback data.
        
        Args:
            bot_username: Username of the bot
            sent_message_id: ID of the sent message
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            Message with inline keyboard or None if timeout/error
        """
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
            try:
                # Get recent messages from the bot
                messages = await self.client.get_messages(bot_username, limit=10)
                
                for message in messages:
                    # Check if this is a response with inline keyboard and at least one button with data
                    if (message.id > sent_message_id and 
                        message.reply_markup and 
                        hasattr(message.reply_markup, 'rows')):
                        try:
                            has_data_button = False
                            for row in message.reply_markup.rows:
                                for btn in getattr(row, 'buttons', []):
                                    if getattr(btn, 'data', None):
                                        has_data_button = True
                                        break
                                if has_data_button:
                                    break
                            if has_data_button:
                                logger.info(f"Received valid format selection message from @{bot_username}")
                                return message
                        except Exception:
                            pass
                
                # Wait before checking again
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error while waiting for format message: {e}")
                await asyncio.sleep(2)
        
        logger.warning(f"Timeout waiting for format message after {max_wait_time} seconds")
        return None

    async def _upload_media_group_to_storage_channel(self, media_messages: list) -> Optional[int]:
        """
        Upload media messages as a single media group to the storage channel.
        
        Args:
            media_messages: List of messages containing media (video, photo, or audio)
            
        Returns:
            Message ID of the last uploaded media in the group or None if failed
        """
        try:
            custom_caption = "📥 @BittadaBot tomonidan yuklab olindi"
            media_files = []

            for i, message in enumerate(media_messages):
                # For Telethon, we can use the media attribute directly
                if message.media:
                    media_files.append(message.media)

            # Ensure we have something to upload
            if not media_files:
                logger.error("No media files found for upload")
                return None

            # Limit to maximum 10 media items per album (Telegram limit)
            if len(media_files) > 10:
                media_files = media_files[:10]

            logger.info(f"Uploading media group to storage channel with {len(media_files)} items...")

            # Use send_file with multiple files to create a media group
            sent_messages = await self.client.send_file(
                self.storage_channel_id,
                media_files,
                caption=custom_caption
            )

            if sent_messages:
                # If single message returned, wrap in list
                if not isinstance(sent_messages, list):
                    sent_messages = [sent_messages]
                    
                last_storage_message_id = sent_messages[-1].id
                logger.info(f"Media group uploaded to storage channel with last message ID: {last_storage_message_id}")
                return last_storage_message_id

            logger.error("Failed to upload media group to storage channel")
            return None

        except Exception as e:
            logger.error(f"Error uploading media group to storage channel: {e}")
            return None
    
    async def _click_inline_button(self, message: Message, callback_data: str) -> bool:
        """
        Click an inline button on a message.
        
        Args:
            message: Message with inline keyboard
            callback_data: Callback data to find and click
            
        Returns:
            True if button was clicked, False otherwise
        """
        try:
            if not message.reply_markup or not hasattr(message.reply_markup, 'rows'):
                logger.error("Message has no inline keyboard")
                return False
            
            # Find the button with matching callback data
            for row_index, row in enumerate(message.reply_markup.rows):
                for button_index, button in enumerate(row.buttons):
                    if hasattr(button, 'data') and button.data:
                        button_data = button.data.decode() if isinstance(button.data, bytes) else str(button.data)
                        if button_data == callback_data:
                            logger.info(f"Clicking button with callback_data: {callback_data}")
                            await message.click(row_index, button_index)
                            return True
            
            logger.error(f"Button with callback_data '{callback_data}' not found")
            return False
            
        except Exception as e:
            logger.error(f"Error clicking inline button: {e}")
            return False
    
    async def _upload_to_storage_channel(self, media_message: Message) -> Optional[int]:
        """
        Upload video/photo/audio to storage channel with custom caption.
        
        Args:
            media_message: Message containing the media (video, photo, or audio)
            
        Returns:
            Message ID in storage channel or None if failed
        """
        try:
            custom_caption = "📥 @BittadaBot tomonidan yuklab olindi"
            file_type = "Media"
            
            # Determine file type based on message content
            if media_message.photo:
                file_type = "Photo"
            elif media_message.video:
                file_type = "Video"
            elif media_message.document:
                if hasattr(media_message.document, 'mime_type'):
                    if media_message.document.mime_type.startswith('video/'):
                        file_type = "Video"
                    elif media_message.document.mime_type.startswith('audio/'):
                        file_type = "Audio"
                    elif media_message.document.mime_type.startswith('image/'):
                        file_type = "Photo"
                    else:
                        file_type = "Document"
            
            logger.info(f"Uploading {file_type.lower()} to storage channel...")
            
            # Prefer the raw media object first
            media_obj = media_message.media or media_message.document or media_message.photo or media_message.video
            if not media_obj:
                logger.warning("Message has no direct media object; attempting to download and re-send...")
                downloaded = await self.client.download_media(media_message)
                media_obj = downloaded
            
            # Send the media file directly with custom caption
            sent_message = await self.client.send_file(
                self.storage_channel_id,
                media_obj,
                caption=custom_caption
            )
            
            if sent_message:
                storage_message_id = sent_message.id
                logger.info(f"{file_type} uploaded to storage channel with message ID: {storage_message_id}")
                return storage_message_id
            else:
                logger.error(f"Failed to upload {file_type.lower()} to storage channel")
                return None
                
        except Exception as e:
            logger.error(f"Error uploading to storage channel: {e}")
            return None
    
    async def get_video_from_storage(self, message_id: int) -> Optional[Message]:
        """
        Get video message from storage channel.
        
        Args:
            message_id: Message ID in storage channel
            
        Returns:
            Message object or None if not found
        """
        try:
            message = await self.client.get_messages(self.storage_channel_id, ids=message_id)
            if message and message.media:
                return message
            return None
        except Exception as e:
            logger.error(f"Error getting video from storage: {e}")
            return None
    
    async def store_format_callback(self, url: str, button_index: int, callback_data: bytes) -> None:
        """Store format callback data for later use.
        
        Args:
            url: YouTube URL
            button_index: Index of the button
            callback_data: Original callback data from YouTube bot
        """
        # Convert bytes to string if needed
        if isinstance(callback_data, bytes):
            callback_data = callback_data.decode()
        
        self.format_callbacks[button_index] = (url, callback_data)
        logger.info(f"Stored format callback {button_index}: {url[:50]}...")
    
    async def get_stored_format_callback(self, button_index: int) -> Optional[Tuple[str, str]]:
        """Get stored format callback data.
        
        Args:
            button_index: Index of the button
            
        Returns:
            Tuple of (url, callback_data) or None if not found
        """
        return self.format_callbacks.get(button_index)
    
    async def store_youtube_request(self, user_id: int, url: str, format_message: Message) -> None:
        """Store YouTube request data per user.
        
        Args:
            user_id: The user's Telegram ID
            url: YouTube URL
            format_message: Format selection message from bot
        """
        self.youtube_requests[user_id] = (url, format_message)
        logger.info(f"Stored YouTube request for user {user_id}: {url[:50]}...")
    
    async def get_stored_youtube_request(self, user_id: int) -> Optional[Tuple[str, Message]]:
        """Get stored YouTube request data for a user.
        
        Args:
            user_id: The user's Telegram ID
            
        Returns:
            A tuple of (url, format_message) or None if not found
        """
        return self.youtube_requests.get(user_id)
    
    async def find_matching_format_callback(self, format_message: Message, desired_format: str) -> Optional[str]:
        """Find the best matching format callback data from SaveYoutubeBot message.
        
        Args:
            format_message: Message with inline keyboard from SaveYoutubeBot
            desired_format: Desired format (360p, 480p, 720p, mp3)
            
        Returns:
            Callback data string for the best matching button or None
        """
        try:
            if not format_message.reply_markup or not hasattr(format_message.reply_markup, 'rows'):
                logger.error("Format message has no inline keyboard")
                return None
            
            # Format mapping patterns to look for in button text
            format_patterns = {
                '360p': ['360', '360p'],
                '480p': ['480', '480p'], 
                '720p': ['720', '720p', 'hd'],
                'mp3': ['mp3', 'audio', 'звук']
            }
            
            patterns = format_patterns.get(desired_format.lower(), [])
            if not patterns:
                logger.error(f"Unknown format: {desired_format}")
                return None
            
            # Search through all buttons for matching format
            best_match = None
            for row in format_message.reply_markup.rows:
                for button in row.buttons:
                    if hasattr(button, 'data') and button.data and hasattr(button, 'text'):
                        button_text = button.text.lower()
                        button_data = button.data.decode() if isinstance(button.data, bytes) else str(button.data)
                        
                        # Check if any pattern matches the button text
                        for pattern in patterns:
                            if pattern.lower() in button_text:
                                logger.info(f"Found matching format button: '{button.text}' for {desired_format}")
                                return button_data
            
            # If no exact match found, try fallback logic
            if desired_format.lower() == 'mp3':
                # For MP3, look for audio-related buttons
                for row in format_message.reply_markup.rows:
                    for button in row.buttons:
                        if hasattr(button, 'data') and button.data and hasattr(button, 'text'):
                            button_text = button.text.lower()
                            if any(word in button_text for word in ['аудио', 'audio', 'звук', 'mp3']):
                                button_data = button.data.decode() if isinstance(button.data, bytes) else str(button.data)
                                logger.info(f"Found fallback audio button: '{button.text}'")
                                return button_data
            else:
                # For video formats, try to find closest resolution
                target_res = int(desired_format.replace('p', ''))
                closest_button = None
                closest_diff = float('inf')
                
                for row in format_message.reply_markup.rows:
                    for button in row.buttons:
                        if hasattr(button, 'data') and button.data and hasattr(button, 'text'):
                            button_text = button.text.lower()
                            # Look for resolution numbers in button text
                            import re
                            res_match = re.search(r'(\d{3,4})p?', button_text)
                            if res_match:
                                button_res = int(res_match.group(1))
                                diff = abs(button_res - target_res)
                                if diff < closest_diff:
                                    closest_diff = diff
                                    closest_button = button
                
                if closest_button:
                    button_data = closest_button.data.decode() if isinstance(closest_button.data, bytes) else str(closest_button.data)
                    logger.info(f"Found closest resolution button: '{closest_button.text}' for {desired_format}")
                    return button_data
            
            logger.warning(f"No matching format found for {desired_format}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding matching format: {e}")
            return None

    async def store_twitter_request(self, user_id: int, url: str, format_message: Message) -> list[str]:
        """Store Twitter request data per user and return mirrored button texts.
        Builds a button map of index -> (callback_data, button_text).
        """
        button_texts = []
        button_map = {}
        try:
            if not getattr(format_message, 'reply_markup', None) or not hasattr(format_message.reply_markup, 'rows'):
                logger.error("Twitter format message has no inline keyboard")
                self.twitter_requests[user_id] = (url, format_message, button_map)
                return button_texts
            idx = 0
            for row in format_message.reply_markup.rows:
                for button in row.buttons:
                    if hasattr(button, 'data') and button.data and hasattr(button, 'text'):
                        text = button.text
                        data = button.data.decode() if isinstance(button.data, bytes) else str(button.data)
                        button_texts.append(text)
                        button_map[idx] = (data, text)
                        idx += 1
            self.twitter_requests[user_id] = (url, format_message, button_map)
            logger.info(f"Stored Twitter request for user {user_id} with {len(button_map)} buttons")
            return button_texts
        except Exception as e:
            logger.error(f"Error storing Twitter request: {e}")
            self.twitter_requests[user_id] = (url, format_message, button_map)
            return button_texts

    async def get_stored_twitter_request(self, user_id: int) -> Optional[Tuple[str, Message, dict]]:
        """Get stored Twitter request data for a user: (url, format_message, button_map)."""
        return self.twitter_requests.get(user_id)
    
    async def _recover_session(self) -> None:
        """Attempt to quickly recover the Telethon session by reconnecting."""
        try:
            if self.client.is_connected():
                await self.client.disconnect()
            await asyncio.sleep(1)
            await self.client.connect()
            if not await self.client.is_user_authorized():
                # If not authorized anymore, mark unauthenticated so operator can re-run setup
                self.is_authenticated = False
                logger.error("Userbot session not authorized after recovery. Please re-run setup.")
            else:
                logger.info("Userbot session reconnected successfully.")
        except Exception as e:
            logger.error(f"Reconnection attempt failed: {e}")
            raise

    async def test_connection(self) -> bool:
        """
        Test connection to Telegram, @instagrambot, @SaveYoutubeBot and @KeepMediaBot.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            # Ensure client is connected and authenticated
            if not self.client.is_connected():
                await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.error("User not authorized")
                return False
            
            # Test basic connection
            me = await self.client.get_me()
            logger.info(f"Connection test: authenticated as {me.first_name}")
            
            # Test access to storage channel
            try:
                channel_info = await self.client.get_entity(self.storage_channel_id)
                logger.info(f"Storage channel access: OK ({channel_info.title})")
            except Exception as e:
                logger.error(f"Cannot access storage channel: {e}")
                return False
            
            # Test @KeepMediaBot availability (used for Instagram and TikTok)
            try:
                bot_info = await self.client.get_entity(self.keepmedia_bot_username)
                logger.info(f"@{self.keepmedia_bot_username} access: OK (used for Instagram and TikTok)")
            except Exception as e:
                logger.error(f"Cannot access @{self.keepmedia_bot_username}: {e}")
                return False
            
            # Test YouTube bot availability
            try:
                bot_info = await self.client.get_entity(self.youtube_bot_username)
                logger.info(f"@{self.youtube_bot_username} access: OK")
            except Exception as e:
                logger.error(f"Cannot access @{self.youtube_bot_username}: {e}")
                return False
            
            # Test Facebook bot availability
            try:
                bot_info = await self.client.get_entity(self.facebook_bot_username)
                logger.info(f"@{self.facebook_bot_username} access: OK")
            except Exception as e:
                logger.error(f"Cannot access @{self.facebook_bot_username}: {e}")
                return False
            
            # Test Twitter bot availability
            try:
                bot_info = await self.client.get_entity(self.twitter_bot_username)
                logger.info(f"@{self.twitter_bot_username} access: OK")
            except Exception as e:
                logger.error(f"Cannot access @{self.twitter_bot_username}: {e}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
