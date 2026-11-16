"""Claude ile günün olayını seçer ve Türkçe hikaye metnini yazar."""
import json
import os
import re
import requests

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
# Ücretsiz seçenek: Google Gemini API (aistudio.google.com'dan alınan anahtar ile)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_YEDEK = os.environ.get("GEMINI_YEDEK_MODEL", "gemini-3.5-flash-lite")


def saglayici() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    raise RuntimeError("Yapay zekâ anahtarı yok: GEMINI_API_KEY (ücretsiz) ya da ANTHROPIC_API_KEY secret'ı ekleyin.")


KURALLAR = """Sen iki Türk markasının Instagram hesabı için "Geçmişte Bugün" hikayesi hazırlayan bir editörsün.
Sana bugünün tarihinde yaşanmış olayların listesi verilecek. Her adayın kullanıma uygun en az bir fotoğrafı var.

KESİN KURALLAR
- Yalnızca adayın metninde ve sayfa özetlerinde yazan bilgileri kullan. Bilgi uydurma, sayı/isim ekleme.
- SEÇİM SIRASI (bir üst grupta uygun aday varsa alt gruba hiç inme):
  1) SICAK KONULAR: ilkler, icatlar, bilim, keşifler, kültür, sanat, edebiyat, müzik, sinema,
     spor başarıları, kuruluşlar, açılışlar, rekorlar, Türkiye tarihindeki olumlu dönüm noktaları.
     Türkiye ile ilgili güzel bir olay varsa öne al.
  2) NÖTR KONULAR: antlaşmalar, keşif gezileri, yönetim ve kurum değişiklikleri gibi
     ne sevindirici ne üzücü olaylar.
  3) ZOR KONULAR (yalnızca 1 ve 2'de hiç uygun aday yoksa): savaş, felaket, ölüm, siyaset.
     Bu durumda bile olabildiğince az sarsıcı olanı seç; dili sakin, saygılı ve tarafsız tut,
     acıyı ayrıntılandırma, kimseyi kahraman ya da kötü ilan etme.
- Fotoğraf olayla doğrudan ilgili olmalı (kişinin portresi, olayın yeri ya da kendisi). Harita, bayrak,
  arma, imza gibi görselleri seçme.
- Metinler kusursuz Türkçe olsun, düz cümle, emoji yok, ünlem yok.
  baslik: olayı anlatan tek cümle, en fazla 70 karakter, nokta ile biter.
  aciklama: başlığı tamamlayan, ilgi çekici tek cümle, en fazla 100 karakter.
  tarih: "15 KASIM 1920" biçiminde, ay adı büyük harf.

İKİ MARKA
{marka_notlari}

ÇIKTI: Yalnızca şu JSON'u yaz, başka hiçbir şey yazma:
{{"canbasimevi": {{"id": <aday id>, "dosya": "<seçilen görsel dosya adı>", "tarih": "...", "baslik": "...", "aciklama": "..."}},
  "canwedding":  {{"id": ..., "dosya": "...", "tarih": "...", "baslik": "...", "aciklama": "..."}}}}"""


def _aday_ozeti(adaylar):
    satirlar = []
    for a in adaylar:
        ozet = " | ".join(f"{s['baslik']}: {s['ozet'][:160]}" for s in a["sayfalar"][:2] if s.get("ozet"))
        gorseller = "; ".join(f"{g['dosya']} ({g['aciklama'][:60]})" for g in a["gorseller"][:3])
        satirlar.append(f"[{a['id']}] {a['yil']} ({a['kaynak']}): {a['metin']}\n   Özet: {ozet[:320]}\n   Görseller: {gorseller}")
    return "\n".join(satirlar)


def _gemini(sistem: str, mesaj: str, gorsel: str | None = None) -> str:
    """Yoğunlukta (429/500/503) bekleyip tekrar dener; sonunda yedek modele geçer."""
    import time
    baslik = {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}
    son_hata = ""
    for model, bekleme in [(GEMINI_MODEL, 0), (GEMINI_MODEL, 20), (GEMINI_MODEL, 60),
                           (GEMINI_YEDEK, 0), (GEMINI_YEDEK, 30), (GEMINI_YEDEK, 90)]:
        time.sleep(bekleme)
        govde = {"systemInstruction": {"parts": [{"text": sistem}]},
                 "contents": [{"role": "user", "parts": [{"text": mesaj}] + (
                     [{"inlineData": {"mimeType": "image/jpeg", "data": gorsel}}] if gorsel else [])}],
                 "generationConfig": {"temperature": 0.5 if gorsel else 0.3, "responseMimeType": "application/json",
                                      "thinkingConfig": {"thinkingLevel": "low"}}}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = requests.post(url, headers=baslik, json=govde, timeout=150)
            if r.status_code == 400 and "thinking" in r.text.lower():
                govde["generationConfig"].pop("thinkingConfig")
                r = requests.post(url, headers=baslik, json=govde, timeout=150)
        except requests.RequestException as e:
            son_hata = str(e); print(f"[uyarı] Gemini ({model}) bağlantı sorunu: {e}"); continue
        if r.ok:
            parcalar = r.json()["candidates"][0]["content"]["parts"]
            return "".join(x.get("text", "") for x in parcalar if not x.get("thought"))
        son_hata = f"{r.status_code}: {r.text[:300]}"
        if r.status_code not in (429, 500, 502, 503, 504):
            break
        print(f"[uyarı] Gemini ({model}) yoğun: {r.status_code}, tekrar denenecek")
    raise RuntimeError(f"Gemini hatası {son_hata}")


def _yapay_zeka(sistem: str, mesaj: str) -> str:
    if saglayici() == "gemini":
        return _gemini(sistem, mesaj)
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 1500, "system": sistem,
              "messages": [{"role": "user", "content": mesaj}]},
        timeout=120,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


def _dogrula(cevap: dict, adaylar, markalar) -> list[str]:
    hatalar = []
    for m in markalar:
        s = cevap.get(m)
        if not isinstance(s, dict):
            hatalar.append(f"{m} eksik"); continue
        aday = next((a for a in adaylar if a["id"] == s.get("id")), None)
        if not aday:
            hatalar.append(f"{m}: geçersiz id"); continue
        if s.get("dosya") not in [g["dosya"] for g in aday["gorseller"]]:
            hatalar.append(f"{m}: görsel o adaya ait değil")
        if not s.get("baslik") or len(s["baslik"]) > 90:
            hatalar.append(f"{m}: başlık boş ya da çok uzun")
        if len(s.get("aciklama", "")) > 130:
            hatalar.append(f"{m}: açıklama çok uzun")
        if not re.fullmatch(r"\d{1,2} [A-ZÇĞİÖŞÜ]+ \d{1,4}", s.get("tarih", "")):
            hatalar.append(f"{m}: tarih biçimi hatalı")
    return hatalar


def sec(adaylar: list[dict], markalar: dict, tarih_metni: str) -> dict:
    notlar = "\n".join(f"- {k} ({v['ad']}): {v['secim_notu']}" for k, v in markalar.items())
    sistem = KURALLAR.format(marka_notlari=notlar)
    mesaj = f"Bugün: {tarih_metni}\n\nADAYLAR\n{_aday_ozeti(adaylar)}"
    for deneme in range(3):
        metin = _yapay_zeka(sistem, mesaj)
        try:
            cevap = json.loads(re.search(r"\{.*\}", metin, re.S).group(0))
        except Exception:
            mesaj += "\n\nÖnceki cevabın geçerli JSON değildi. Yalnızca JSON yaz."
            continue
        hatalar = _dogrula(cevap, adaylar, markalar)
        if not hatalar:
            return cevap
        mesaj += "\n\nÖnceki cevabındaki sorunlar: " + "; ".join(hatalar) + ". Düzeltip yalnızca JSON yaz."
    raise RuntimeError("Yapay zekâ geçerli bir seçim üretemedi.")


GONDERI_KURALLARI = """Sen {ad} markasının Instagram editörüsün. {tanim}
Sana markanın daha önce yaptığı bir işin fotoğrafı ve o gönderinin eski açıklaması verilecek.
Bu fotoğraf yeni bir tasarımla tekrar paylaşılacak. Şunları yaz:
- slogan: fotoğraftaki işe uygun, akılda kalan, sıcak bir cümle. En fazla 40 karakter, nokta ile biter.
- alt_satir: işin öne çıkan 2-3 özelliği, aralarında " · " olacak. Örn: "Siyah kurdele · Sade zarafet". En fazla 40 karakter.
- aciklama: Instagram gönderi açıklaması. 2-4 kısa cümle; işi anlat, sonunda sipariş/bilgi için DM'e davet et.
  Ardından boş satır ve 6-10 Türkçe etiket (#). Emoji en fazla 2.
KURALLAR: Fotoğraftaki kişi adlarını, tarihleri, adresleri, mekân adlarını ASLA yazma (müşteri bilgisidir).
Görmediğin bir özelliği (kâğıt türü, baskı tekniği) uydurma; emin değilsen genel ifade kullan.
Önce fotoğrafı değerlendir: urun_fotografi = true yalnızca gerçek bir ürünün (davetiye, baskı işi vb.) fotoğrafıysa.
Üzerinde büyük reklam yazıları, fiyat, telefon numarası, kampanya metni olan hazır tasarlanmış reklam/afiş görseliyse
ya da işle ilgisiz bir fotoğrafsa urun_fotografi = false yaz (diğer alanları boş bırakabilirsin).
Kusursuz Türkçe. Yalnızca şu JSON'u yaz: {{"urun_fotografi": true, "slogan": "...", "alt_satir": "...", "aciklama": "..."}}"""


def gonderi_metni(foto_baytlari: bytes, eski_aciklama: str, marka: dict) -> dict:
    """Gemini'ye fotoğrafı da göstererek slogan ve açıklama yazdırır."""
    import base64
    sistem = GONDERI_KURALLARI.format(ad=marka["ad"], tanim=marka.get("gonderi_tanim", ""))
    mesaj = f"Eski açıklama (bilgi için, kopyalama):\n{(eski_aciklama or '-')[:800]}"
    for _ in range(3):
        metin = _gemini(sistem, mesaj, gorsel=base64.b64encode(foto_baytlari).decode())
        try:
            c = json.loads(re.search(r"\{.*\}", metin, re.S).group(0))
            if c.get("urun_fotografi") is False:
                return c
            if c.get("slogan") and c.get("aciklama") and len(c["slogan"]) <= 60 and len(c.get("alt_satir", "")) <= 60:
                return c
        except Exception:
            pass
        mesaj += "\n\nÖnceki cevap geçersizdi; kurallara uyan geçerli JSON yaz."
    raise RuntimeError("Gönderi metni üretilemedi.")
