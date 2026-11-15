"""Claude ile günün olayını seçer ve Türkçe hikaye metnini yazar."""
import json
import os
import re
import requests

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
# Ücretsiz seçenek: Google Gemini API (aistudio.google.com'dan alınan anahtar ile)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")


def saglayici() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    raise RuntimeError("Yapay zekâ anahtarı yok: GEMINI_API_KEY (ücretsiz) ya da ANTHROPIC_API_KEY secret'ı ekleyin.")


def _aday_ozeti(adaylar):
    satirlar = []
    for a in adaylar:
        ozet = " | ".join(f"{s['baslik']}: {s['ozet'][:160]}" for s in a["sayfalar"][:2] if s.get("ozet"))
        gorseller = "; ".join(f"{g['dosya']} ({g['aciklama'][:60]})" for g in a["gorseller"][:3])
        satirlar.append(f"[{a['id']}] {a['yil']} ({a['kaynak']}): {a['metin']}\n   Özet: {ozet[:320]}\n   Görseller: {gorseller}")
    return "\n".join(satirlar)


def _yapay_zeka(sistem: str, mesaj: str) -> str:
    if saglayici() == "gemini":
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
            json={"systemInstruction": {"parts": [{"text": sistem}]},
                  "contents": [{"role": "user", "parts": [{"text": mesaj}]}],
                  "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}},
            timeout=120,
        )
        if not r.ok:
            raise RuntimeError(f"Gemini hatası {r.status_code}: {r.text[:600]}")
        parcalar = r.json()["candidates"][0]["content"]["parts"]
        return "".join(x.get("text", "") for x in parcalar)
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
