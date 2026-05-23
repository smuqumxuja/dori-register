# Dori-darmon elektron jurnali

Tibbiy hamshiralar qog'oz jurnal o'rniga bemorlar bo'yicha ishlatilgan dori-darmonlarni elektron shaklda kiritishi uchun lokal web-dastur.

## Imkoniyatlar

- Login/parol bilan kirish.
- Login paytida captcha orqali qo'shimcha tekshiruv.
- Sahifa ochilganda avval login ekrani ko'rsatiladi.
- Super admin uchun statistikadan alohida boshqaruv oynasida korpuslar yaratish va tahrirlash: korpus nomi va izoh.
- Super admin uchun statistikadan alohida boshqaruv oynasida bo'limlar yaratish va tahrirlash: bo'lim nomi, ro'yxatdan tanlangan korpus va izoh.
- Super admin uchun statistikadan alohida boshqaruv oynasida bo'lim va rol biriktirilgan foydalanuvchilar yaratish va tahrirlash.
- Local admin o'z korpusidagi foydalanuvchi, dori va sarf ma'lumotlarini boshqaradi.
- Hamshira faqat o'zi kiritgan dori partiyalari va sarf yozuvlarini ko'radi, tahrirlaydi va export qiladi.
- Kuzatuvchi faqat o'ziga biriktirilgan korpus bo'yicha statistikani ko'radi, ma'lumot kiritmaydi.
- Adminlar uchun boshqaruv oynasida foydalanuvchilar statistikasi va oxirgi amallar log jurnalini ko'rish.
- Bo'lim tanlanadigan maydonlarda qo'lda yozish emas, faqat ma'lumotnomadagi ro'yxatdan tanlash.
- Rollar: super admin, korpus bo'yicha local admin, hamshira va kuzatuvchi.
- Har bir rol uchun ko'rish va tahrirlash huquqlari bazadagi scope bo'yicha cheklanadi.
- Dorilar ro'yxatini alohida oynada shakllantirish: dori nomi, qabul qilingan sana/vaqt, miqdor, shakli va real qoldiq.
- Bemorlar bo'yicha sarfni alohida oynada kiritish; dori qidiruv orqali tanlanadi.
- Dori bemorga ishlatilganda real qoldiq avtomatik kamayadi, sarf yozuvi o'chirilganda qoldiq qaytariladi.
- Yozuvlarni SQLite bazasida saqlash.
- Sana va matn bo'yicha filtrlash.
- Yozuvlar, foydalanuvchilar, bo'limlar, korpuslar va dori partiyalarini ruxsat doirasida tahrirlash.
- Asosiy ekranda monitoring: sarf, bemorlar, dori partiyalari, umumiy qoldiq va kam qolgan dorilar.
- Filtrlangan jurnal, dorilar ro'yxati va statistikani `.xlsx` Excel fayliga export qilish.

## Ishga tushirish

Codex runtime Python bilan:

```powershell
C:\Users\saidovm.2RSCEM\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe app.py
```

Brauzerda ochiladi:

```text
http://127.0.0.1:8000
```

Boshlang'ich super admin akkaunti:

```text
login: superadmin
parol: Admin123!
```

Ma'lumotlar `data/journal.db` SQLite bazasida saqlanadi.

## Keyingi kengaytirishlar

- Parolni foydalanuvchi panelida almashtirish.
- Inventarizatsiya dalolatnomalarini kiritish.
- Tarmoq ichida bir nechta kompyuterdan ishlash uchun markaziy server.
