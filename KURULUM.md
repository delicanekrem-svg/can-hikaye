# Günlük Instagram Hikayesi: Can Basımevi & CanWedding

Sistem her sabah **07:00'de (Türkiye saati)** iki hesaba da otomatik hikaye paylaşır.

**Nasıl çalışır?**
1. **Türkiye'de önemli bir gün mü?** (`veri/ozel_gunler.json`) Öyleyse "BUGÜN" tasarımı hazırlanır: milli bayramlarda kırmızı vurgu, anma günlerinde sade tasarım, diğer günlerde marka rengi kullanılır.
2. **Değilse "Geçmişte Bugün":** Türkçe ve İngilizce Vikipedi'den o günün olayları çekilir. Yalnızca **Wikimedia Commons'ta bulunan ve ticari kullanıma izin veren** (kamu malı, CC0, CC BY, CC BY-SA) fotoğrafı olan olaylar aday olur.
3. **Seçim ve metin:** Claude olayları şu sırayla seçer ve Türkiye ile ilgili güzel olayları öne alır:
   - **Sıcak konular:** ilkler, icatlar, kültür, sanat, bilim, spor başarıları.
   - **Nötr konular:** Sıcak bir konu yoksa antlaşmalar, keşif gezileri gibi olaylar.
   - **Zor konular:** Savaş, felaket, ölüm ve siyaset yalnızca o gün başka uygun olay yoksa seçilir; metin sakin ve tarafsız bir dille yazılır.
   - Can Basımevi için genel ilgi çeken olaylar seçilir; matbaa, kitap ve yayıncılık olayları artı puan alır.
   - CanWedding için aşk, evlilik, kültür ve sanat olayları güçlü öncelik alır. Bugün böyle bir olay yoksa Can Basımevi'nin olayı kullanılır.
4. **Görsel:** 1080×1920 JPEG olarak üretilir ve fotoğraf kaynağı görselin üzerine yazılır.
5. **Paylaşım:** Görseller depoya kaydedilir. Saat 07:00'de Instagram'a hikaye olarak paylaşılır.

> **Kendi tasarımını kullanmak için:** Bir gün için hazır tasarım istiyorsan (ör. bayram görseli),
> `assets/ozel/10-29_canbasimevi.jpg` ve `assets/ozel/10-29_canwedding.jpg` şeklinde koy. O gün otomatik görsel yerine bu dosya paylaşılır.

---

## Kurulum (bir kerelik)

### 1. GitHub deposu
1. GitHub'da yeni bir **public** depo aç (ör. `can-hikaye`).
   Instagram görseli herkese açık bir adresten çektiği için depo açık olmalı. Depoda şifre ya da anahtar bulunmaz; onlar "Secrets" bölümünde gizli tutulur.
2. Bu klasördeki tüm dosyaları depoya yükle (`.github` klasörü dahil).

### 2. Logolar
- `assets/logolar/canbasimevi.png`: koyu zemin üzerinde görünecek, açık renkli logo
- `assets/logolar/canwedding.png`: açık zemin üzerinde görünecek, koyu renkli logo
- Şeffaf arka planlı PNG olmalı. Yükseklik 84 piksele ölçeklenir.

### 3. Yapay zekâ (ücretsiz, ek ayar gerekmez)
- Varsayılan olarak **GitHub Models** kullanılır. GitHub'ın kendi ücretsiz yapay zekâ hizmetidir, depoya otomatik bağlanır, anahtar gerekmez.
- Günde tek istek atıldığı için ücretsiz sınırın çok altında kalınır.
- İleride daha iyi metin kalitesi istersen `ANTHROPIC_API_KEY` adında bir secret eklemen yeterli; sistem kendiliğinden Claude'a geçer.

### 4. Instagram erişimi (Meta)
İki hesap da işletme hesabı ve Facebook sayfasına bağlı olduğu için şu adımlar yeterli:

1. **developers.facebook.com:** "Uygulama oluştur", tür olarak **İşletme (Business)** seç.
   Uygulamaya **Instagram** ürününü ekle ("API setup with Facebook login").
2. **business.facebook.com → İşletme Ayarları:**
   - **Sistem Kullanıcıları:** Yönetici rolünde bir sistem kullanıcısı oluştur.
   - Bu kullanıcıya **iki Facebook sayfasını**, **iki Instagram hesabını** ve **uygulamayı** ata.
   - "Belirteç oluştur" ile süresi dolmayan bir token üret. Şu izinleri seç:
     `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `business_management`
3. Instagram kullanıcı kimliklerini öğrenmek için Graph API Explorer'da şunu çalıştır:
   `GET /me/accounts?fields=name,instagram_business_account`
   Her sayfanın altındaki `instagram_business_account.id` değeri, o hesabın kimliğidir.
4. GitHub Secrets'a ekle:

   | Ad | Değer |
   |---|---|
   | `IG_ID_CANBASIMEVI` | Can Basımevi Instagram kimliği |
   | `IG_TOKEN_CANBASIMEVI` | token |
   | `IG_ID_CANWEDDING` | CanWedding Instagram kimliği |
   | `IG_TOKEN_CANWEDDING` | token (aynı sistem kullanıcısı ise aynı token) |

> Uygulama ve hesaplar aynı işletmeye aitse genellikle Meta incelemesi gerekmez.
> Meta inceleme isterse `instagram_content_publish` izni için başvurmak gerekir (birkaç hafta sürebilir).

### 5. Deneme
1. Depoda **Actions → Günlük Instagram Hikayesi → Run workflow** yolunu izle.
2. Tarih kutusunu boş bırak, "Instagram'a da paylaşılsın mı?" kutusunu **işaretleme**.
3. İş bitince `yayin/<tarih>/` klasöründe görselleri ve `bilgi.json` dosyasını kontrol et.
4. Beğendiysen bir kez de kutuyu işaretleyerek çalıştır; hikaye anında paylaşılır.

Bundan sonra sistem her sabah kendiliğinden çalışır.

---

## Bakım
- **Dini bayramlar:** Her yıl Diyanet takvimi açıklanınca `veri/ozel_gunler.json` → `tarihli` bölümüne ekle.
  (2027 eklendi: Ramazan Bayramı 9 Mart, Kurban Bayramı 16 Mayıs.)
- **Hata olursa:** GitHub, iş başarısız olduğunda depo sahibine e-posta gönderir. Aynı günün işi tekrar çalıştırılırsa zaten paylaşılmış hesap atlanır, çift paylaşım olmaz.
- **Renkler ve yazı:** `veri/markalar.json` (renkler, marka seçim notları), `sablonlar/*.html` (tasarım).

## Yerelde deneme
```bash
pip install -r requirements.txt && playwright install chromium
python gunluk.py onizle --tarih 2026-11-15 --test        # internetsiz örnek
ANTHROPIC_API_KEY=... python gunluk.py onizle --tarih 2026-12-17   # gerçek veriyle, paylaşmadan
```
