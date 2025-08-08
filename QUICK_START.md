# 🚀 Quick Start Guide - Majburiy Obuna Bot

## Taxminiy vaqt: 10-15 daqiqa

### 1️⃣ Kerakli ma'lumotlar tayyorlang

**Bot uchun:**
- Telegram Bot Token (@BotFather dan)
- API_ID va API_HASH (my.telegram.org dan)

**Kanallar uchun:**
- Storage kanali (bot admin bo'lishi kerak) 
- Majburiy obuna kanallari (ixtiyoriy)

### 2️⃣ Fayl konfiguratsiyasi

`.env` faylini yarating:
```env
# Bot konfiguratsiyasi
BOT_TOKEN=1234567890:ABCdefGhIjKlMnOpQrStUvWxYz
API_ID=1234567
API_HASH=abcdef1234567890abcdef1234567890

# Storage kanal (-100 bilan boshlangan ID)
STORAGE_CHANNEL_ID=-1001234567890

# Admin IDs (vergul bilan ajratilgan)
ADMIN_IDS=123456789,987654321
```

### 3️⃣ Ishga tushirish

```bash
# Dependencies o'rnatish
pip install -r requirements.txt

# Botni ishga tushirish
python main.py
```

### 4️⃣ Test qilish

1. **Botni shaxsiy chatda test qiling:**
   - Instagram/YouTube/TikTok havolasi yuboring
   - Formatni tanlag (YouTube uchun)

2. **Guruhda test qiling:**
   - Botni guruhga admin qilib qo'shing
   - Havola yuboring va javobni kuting

### 5️⃣ Majburiy obuna qo'shish

1. Botga `/admin` buyrug'ini yuboring
2. "🔒 Majburiy Obuna" tugmasini bosing
3. "➕ Yangi kanal qo'shish" ni tanlang
4. Kanal turini tanlang (ochiq yoki yopiq)
5. Kanal ma'lumotlarini kiriting

## ✅ Tayyor!

Endi bot:
- Foydalanuvchi link yuborganida 👀 reaktsiya qo'yadi (vizual ko'rsatkich)
- Majburiy obunani DARHOL tekshiradi
- Obuna bo'lmagan foydalanuvchilarga "Obunani tekshirish" tugmasini ko'rsatadi
- Obuna bo'lsa - videoni DARHOL yuklab beradi
- YouTube videolar uchun format tanlash sahifasini ko'rsatadi

### 🎯 Qanday ishlaydi:
1. **Siz link yuborasiz** → Bot darhol obuna tekshiradi va 👀 qo'yadi
2. **Obuna bo'lsangiz** → Video avtomatik yuklanadi
3. **Obuna bo'lmasangiz** → "Obunani tekshirish" tugmasi

### ℹ️ Muhim eslatma:
- Endi reaktsiya bosish shart emas!
- Bot avtomatik ravishda video yuklab beradi
- 👀 reaktsiya faqat vizual ko'rsatkich

## 🔧 Masalalar hal qilish

### Bot javob bermasa:
- Bot tokenini tekshiring
- Storage kanal ID to'g'ri ekanligini tasdiqlang
- Botni storage kanaliga admin qilib qo'shganingizni tekshiring

### Obuna tekshiruvi ishlamasa:
- Kanal ID to'g'ri kiritilganini tekshiring
- Bot kanal a'zosi bo'lishi kerak (tekshirish uchun)

### Xatolik loglarini ko'rish:
- `logs/bot.log` faylini tekshiring
- Console outputda xatoliklarni kuzating

## 📞 Yordam

Agar muammo bo'lsa:
1. Loglarni tekshiring
2. Konfiguratsiyani qayta ko'rib chiqing
3. Botni qayta ishga tushiring
