"""Claude ile günün olayını seçer ve Türkçe hikaye metnini yazar."""
import json
import os
import re
import requests

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
# Ücretsiz seçenek: GitHub Models (GitHub Actions içindeki GITHUB_TOKEN ile, ek anahtar gerekmez)
GH_MODEL = os.environ.get("GH_MODEL", "openai/gpt-4.1")


def saglayici() -> str:
    return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "github"

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


def _yapay_zeka(sistem: str, mesaj: str) -> str:
    if saglayici() == "github":
        r = requests.post(
            "https://models.github.ai/inference/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Content-Type": "application/json"},
            json={"model": GH_MODEL, "temperature": 0.3, "max_tokens": 1200,
                  "messages": [{"role": "system", "content": sistem}, {"role": "user", "content": mesaj}]},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
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
