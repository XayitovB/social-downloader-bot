# 🔍 Bot Debug Guide

## Bot funksiyalarini test qilish

**Eslatma: Reaktsiya funksiyasi o'chirildi! Bot endi avtomatik video yuklab beradi.**

### 1️⃣ Botni test rejimida ishga tushiring

```bash
# Terminal/CMD da
python main.py
```

Loglarni kuzating - quyidagilarni ko'rishingiz kerak:

### 2️⃣ Link yuborishda kutilayotgan loglar

```
INFO | Added 👀 reaction to message 123 from user 456
INFO | User 456 passed subscription check, proceeding with URL processing
INFO | Processing request for user 456: https://instagram.com/...
```

### 3️⃣ Video yuklanishda kutilayotgan loglar

```
INFO | Successfully processed Instagram https://instagram.com/...
INFO | Added video record: https://instagram.com/... -> 27 (instagram)
INFO | Sent instagram media (message_id: 27) to chat 123 for user 456
```

## ❌ Muammolar va yechimlar

### Problem 1: "Could not add reaction to message"
**Sabab:** Bot API da reaction qo'yish ishlamayotgan
**Yechim:** 
- Botni yangi Telegram Bot API versiyasiga yangilang
- Bot admin huquqlarga ega bo'lishini tasdiqlang

### Problem 2: "No stored message found for reaction"
**Sabab:** Database da xabar saqlanmagan
**Yechim:**
- Database faylini tekshiring: `ls db/`
- Loglarni tekshiring reaction storage uchun

### Problem 3: Reaction event kelmayapti
**Sabab:** Aiogram message_reaction handler ishlamayapti
**Yechim:**
- Aiogram versiyasini tekshiring: `pip show aiogram`
- Reaction middleware to'g'ri o'rnatilganini tasdiqlang

## 🧪 Test qadamlari

1. **Bot ishga tushiring**
2. **Instagram/YouTube link yuboring**
3. **Bot 👀 reaktsiya qo'yishini kuting** 
4. **Video avtomatik yuklanishini kuting** (ℹ️ Reaktsiya bosish shart emas!)

## 📋 Log tekshirish buyruqlari

```bash
# So'nggi 50 ta log qatorini ko'rish
tail -50 logs/bot.log

# Reaktsiya loglarini filtrlash
grep -i "reaction" logs/bot.log

# Xatoliklarni ko'rish
grep -i "error" logs/bot.log
```

## 🔧 Agar hech narsa ishlamasa

Reaction funksiyasini vaqtinchalik o'chirib, oddiy rejimga qaytarish:

1. `bot/handlers.py` faylida 614-660 qatorlarni comment qiling
2. Bot avtomatik ravishda eski usulda ishlaydi
3. Muammoni hal qilib, qayta yoqing

## 📞 Yordam uchun

Log faylini (`logs/bot.log`) tekshiring va xatolik xabarlarini qidiring.
