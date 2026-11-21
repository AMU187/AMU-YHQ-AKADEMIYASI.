# YHQ ACADEMY V24 — O‘QITUVCHI VA O‘QUVCHI YAGONA SERVERI

Bu loyiha **Render Web Service (Docker)** uchun, Static Site emas.

## Render.com
1. ZIPni ochib, ichidagi barcha fayllarni GitHub repoga joylang.
2. Render → New → Blueprint → GitHub repo; `render.yaml` ni tanlang.
3. `ADMIN_PASSWORD` ga kamida 12 belgili maxfiy parol kiriting. `ADMIN_LOGIN` standart `admin`.
4. Render xizmatiga **persistent disk** (`/data`) zarur. Render rejasida disk qo‘llab-quvvatlanishini tekshiring. Disk bo‘lmasa SQLite va dars fayllari deploy/restartda yo‘qolishi mumkin.
5. Deploy tugagach `/login` orqali o‘qituvchi sifatida kiring.
6. Eski V24 HTML brauzeridan **Zahira → JSON** eksport qiling. Yangi sayt **Zahira nusxa** bo‘limida eski JSONni serverga import qiling. Import serverdagi jurnalni almashtiradi.
7. **O‘quvchilar** bo‘limidan har bir o‘quvchiga login va parol yarating. O‘quvchi shu saytning `/login` manzilidan kiradi.

## Nima ishlaydi?
- O‘qituvchining V24 jurnal va bosh sahifa interfeysi; jurnal server SQLite bazasiga yoziladi.
- O‘quvchilarni ro‘yxatdan tanlab login yaratish, parol yangilash, bloklash.
- O‘quvchiga faqat o‘z baholari, `Y`, soatlar, darslar va guruhdagi reyting ko‘rinadi. Boshqalarning batafsil baholari API orqali berilmaydi.
- Dars fayllari serverga (15 MB gacha) yuklanadi; o‘quvchi ko‘ra/yuklay oladi.
- Serverdagi jurnal uchun kuniga bir dona aylanma zahira: **shu kundagi birinchi saqlashda** olinadi, eski kun nusxasini almashtiradi. Bu 23:59 ga kafolatlangan rejalashtirilgan vazifa emas.
- O‘quvchi ma’lumotlari sahifa ochilganda, qayta faol bo‘lganda va har 30 soniyada yangilanadi.

## Cheklovlar va muhim ogohlantirishlar
- Eski V24 `file://` brauzer xotirasidagi ma’lumotlar yangi saytga o‘z-o‘zidan o‘tmaydi; JSON import zarur.
- V24 ning ayrim dizayn/sozlama qiymatlari va motivatsion banner rasmlari hali ham o‘qituvchining mahalliy brauzerida saqlanishi mumkin. Boshqa qurilmaga sinxronlanmaydi.
- O‘qituvchining bir nechta qurilmadan **bir vaqtda** tahrir qilishi uchun konfliktni oldini oluvchi revision nazorati yo‘q. Bir o‘qituvchi/bir sessiya bilan ishlating.
- O‘qituvchi interfeysining ayrim eski funksiyalari localStorage ishlatadi; barcha biznes qoidalar server darajasida majburlanmagan. Muhim production foydalanishdan oldin xavfsizlik va funksional audit zarur.
- O‘quvchi parolini o‘qituvchi yaratadi, kamida 8 belgi; parol serverda Argon2 xesh ko‘rinishida.
- `COOKIE_SECURE=true` HTTPS uchun. Lokal HTTP sinovida `false` qo‘ying.
- Server zaxirasi faqat jurnaldagi JSON; dars fayllari SQLite ichida, to‘liq DB disk zahirasini alohida olib boring.
- `render.yaml` dagi disk pullik rejani talab qilishi mumkin; Render tarifini tekshiring.

## V24 o‘quvchi sozlamalari (yangi)
- O‘quvchi Sozlamalar bo‘limidan fon (kunduzgi/tungi/yo‘l), rang, shrift, jurnal masshtabi va menyu ko‘rinishini o‘zgartiradi. Bu ko‘rinish sozlamalari faqat o‘sha brauzerda saqlanadi.
- ID, login va parolni o‘quvchi serverda joriy parolini tasdiqlab yangilashi mumkin; o‘zgarishlar SQLite da bir tranzaksiyada amalga oshadi.
- ID o‘zgarsa, jurnal baholari va baho vaqtlari yangi IDga ko‘chiriladi.
- Hisob o‘zgargandan so‘ng sessiya tugatiladi; o‘quvchi yangi login/parol bilan kiradi.
- O‘qituvchi O‘quvchilar bo‘limida har 5 soniyada serverdagi yangilanishlarni tekshiradi. Internet ishlamay qolsa yoki sahifa yopiq bo‘lsa darhol yangilanish kafolatlanmaydi.
- O‘qituvchi platformasida xavfsizlik uchun parolning o‘zi ko‘rsatilmaydi: u Argon2 xesh sifatida saqlanadi. O‘qituvchi parolni yangilashi mumkin.
- QR-kodda eski login/parol bo‘lsa, hisob o‘zgargach QR-kodni yangidan chiqarish kerak. Bu server paketida avtomatik QR yangilash mavjud emas.
- Bu alohida HTML faylning sinov rejimida haqiqiy hisob o‘zgarishi ishlamaydi. Buning uchun server ZIPini Render Web Service sifatida ishga tushiring.
