"""Wikipedia'dan 'bugün ne oldu' adaylarını ve Wikimedia Commons'tan
kullanım izni uygun fotoğrafları toplar."""
import datetime as dt
import html
import re
import requests

UA = {"User-Agent": "CanHikayeBot/1.0 (https://github.com/delicanekrem-svg/can-hikaye; gunluk tek hikaye) python-requests"}
COMMONS = "https://commons.wikimedia.org/w/api.php"

# Ticari kullanıma ve değiştirmeye izin veren lisanslar (kaynak gösterilerek)
UYGUN_LISANS = re.compile(r"^(public domain|pd\b|pd-|cc0|no restrictions|cc by(-sa)? \d|cc-by(-sa)?-\d|cc by(-sa)?$)", re.I)
YASAK_LISANS = re.compile(r"(\bnc\b|-nc|\bnd\b|-nd|non-?commercial|no ?deriv|fair use)", re.I)


def _get(url, **params):
    r = requests.get(url, params=params or None, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def _temizle(metin: str) -> str:
    metin = re.sub(r"<[^>]+>", "", str(metin) if metin is not None else "")
    return re.sub(r"\s+", " ", html.unescape(metin)).strip()


# ---------- Adaylar ----------

def ingilizce_adaylar(tarih: dt.date) -> list[dict]:
    """Wikipedia 'On this day' akışı: olay metni + bağlantılı sayfalar ve görselleri."""
    adaylar = []
    for tur in ("selected", "events"):
        try:
            veri = _get(f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/{tur}/{tarih:%m}/{tarih:%d}")
        except Exception as e:
            print(f"[uyarı] EN {tur} alınamadı: {e}")
            continue
        for olay in veri.get(tur, []):
            sayfalar = []
            for s in olay.get("pages", [])[:5]:
                gorsel = (s.get("originalimage") or {}).get("source")
                sayfalar.append({
                    "baslik": s.get("normalizedtitle") or s.get("title"),
                    "ozet": (s.get("extract") or "")[:600],
                    "gorsel_url": gorsel,
                })
            adaylar.append({"kaynak": "en", "yil": olay.get("year"), "metin": olay.get("text", ""),
                            "secilmis": tur == "selected", "sayfalar": sayfalar})
    return adaylar


AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def turkce_adaylar(tarih: dt.date) -> list[dict]:
    """Türkçe Vikipedi'nin '15 Kasım' gibi gün sayfasındaki 'Olaylar' bölümü."""
    sayfa = f"{tarih.day} {AYLAR[tarih.month - 1]}"
    try:
        veri = _get("https://tr.wikipedia.org/w/api.php", action="parse", page=sayfa,
                    prop="wikitext", format="json", formatversion=2)
        wikitext = veri["parse"]["wikitext"]
    except Exception as e:
        print(f"[uyarı] TR gün sayfası alınamadı: {e}")
        return []
    bolum = re.search(r"==\s*Olaylar\s*==(.*?)(\n==[^=])", wikitext, re.S)
    if not bolum:
        return []
    adaylar = []
    for satir in bolum.group(1).splitlines():
        m = re.match(r"\*+\s*\[\[(\d{1,4})\]\]\s*[-–—:]\s*(.+)", satir.strip())
        if not m:
            continue
        yil, govde = int(m.group(1)), m.group(2)
        baglantilar = [b.split("|")[0] for b in re.findall(r"\[\[([^\]]+)\]\]", govde)]
        baglantilar = [b for b in baglantilar if not re.fullmatch(r"\d+", b)][:5]
        metin = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", govde)
        metin = re.sub(r"<ref.*?(</ref>|/>)", "", metin)
        metin = re.sub(r"\{\{.*?\}\}|'''?", "", metin).strip()
        adaylar.append({"kaynak": "tr", "yil": yil, "metin": metin, "secilmis": False,
                         "sayfalar": [{"baslik": b, "ozet": "", "gorsel_url": None} for b in baglantilar]})
    _turkce_gorselleri_ekle(adaylar)
    return adaylar


def _turkce_gorselleri_ekle(adaylar):
    basliklar = list({s["baslik"] for a in adaylar for s in a["sayfalar"]})
    bulunan = {}
    for i in range(0, len(basliklar), 50):
        try:
            veri = _get("https://tr.wikipedia.org/w/api.php", action="query", titles="|".join(basliklar[i:i + 50]),
                        prop="pageimages|extracts", piprop="original", exintro=1, explaintext=1,
                        exchars=500, redirects=1, format="json", formatversion=2)
        except Exception as e:
            print(f"[uyarı] TR görseller alınamadı: {e}")
            continue
        yonlendir = {r["from"]: r["to"] for r in veri["query"].get("redirects", [])}
        for p in veri["query"].get("pages", []):
            bulunan[p["title"]] = ((p.get("original") or {}).get("source"), p.get("extract", ""))
        for eski, yeni in yonlendir.items():
            if yeni in bulunan:
                bulunan[eski] = bulunan[yeni]
    for a in adaylar:
        for s in a["sayfalar"]:
            if s["baslik"] in bulunan:
                s["gorsel_url"], s["ozet"] = bulunan[s["baslik"]]


# ---------- Görsel izinleri ----------

def _dosya_adi(url: str) -> str | None:
    if not url or "upload.wikimedia.org" not in url:
        return None
    url = url.split("?")[0].split("#")[0]  # ?utm_source=... gibi ekleri at
    parca = url.split("/")
    ad = parca[-1]
    if "/thumb/" in url:  # .../thumb/a/ab/Dosya.jpg/800px-Dosya.jpg
        ad = parca[-2]
    # Commons adları boşlukla döndürür (Vikipedi URL'leri alt çizgi kullanır)
    return requests.utils.unquote(ad).replace("_", " ")


def commons_bilgisi(dosyalar: list[str]) -> dict[str, dict]:
    """Yalnızca Commons'ta bulunan ve lisansı uygun olan fotoğrafları döndürür.
    (Vikipedi'ye 'adil kullanım' ile yüklenmiş telifli görseller Commons'ta yoktur, böylece elenir.)"""
    sonuc = {}
    dosyalar = list(dict.fromkeys(dosyalar))
    for i in range(0, len(dosyalar), 50):
        veri = _get(COMMONS, action="query", titles="|".join("File:" + d for d in dosyalar[i:i + 50]),
                    prop="imageinfo", iiprop="url|mime|size|extmetadata", iiurlwidth=1280,
                    format="json", formatversion=2)
        for p in veri["query"].get("pages", []):
            if p.get("missing") or not p.get("imageinfo"):
                continue
            ii = p["imageinfo"][0]
            meta = {k: _temizle(v.get("value", "")) for k, v in ii.get("extmetadata", {}).items()}
            lisans = meta.get("LicenseShortName", "")
            if ii.get("mime") not in ("image/jpeg", "image/png", "image/tiff"):
                continue  # svg harita/bayrak/logo istemiyoruz
            if ii.get("width", 0) < 700 or ii.get("height", 0) < 450:
                continue
            if YASAK_LISANS.search(lisans) or not UYGUN_LISANS.search(lisans):
                continue
            sonuc[p["title"].removeprefix("File:")] = {
                "indir_url": ii.get("thumburl") or ii["url"],
                "orijinal_url": ii["url"],
                "sayfa_url": ii.get("descriptionurl"),
                "lisans": lisans,
                "sahibi": meta.get("Artist", "")[:80],
                "tarih": meta.get("DateTimeOriginal", "")[:40],
                "aciklama": meta.get("ImageDescription", "")[:200],
                "genislik": ii.get("width"), "yukseklik": ii.get("height"),
            }
    return sonuc


def adaylari_topla(tarih: dt.date, en_fazla: int = 70) -> list[dict]:
    """Görseli kullanılabilir olan adayları numaralandırılmış biçimde döndürür."""
    tr, en = turkce_adaylar(tarih), ingilizce_adaylar(tarih)
    adaylar = tr + en
    dosyalar = [d for d in (_dosya_adi(s["gorsel_url"]) for a in adaylar for s in a["sayfalar"]) if d]
    izinli = commons_bilgisi(dosyalar)
    print(f"[bilgi] olay: TR {len(tr)}, EN {len(en)} | görsel: {len(set(dosyalar))}, izinli: {len(izinli)}")
    temiz = []
    for a in adaylar:
        gorseller = []
        for s in a["sayfalar"]:
            d = _dosya_adi(s["gorsel_url"])
            if d and d in izinli and d not in [g["dosya"] for g in gorseller]:
                gorseller.append({"dosya": d, "sayfa": s["baslik"], **izinli[d]})
        if gorseller and a["metin"]:
            a["gorseller"] = gorseller
            temiz.append(a)
    # Türkçe ve 'seçilmiş' olaylar önce gelsin
    temiz.sort(key=lambda a: (a["kaynak"] != "tr", not a["secilmis"]))
    print(f"[bilgi] görseli uygun olay: {len(temiz)}")
    temiz = temiz[:en_fazla]
    for i, a in enumerate(temiz):
        a["id"] = i
    return temiz


def gorsel_indir(url: str, hedef, yedek_url: str | None = None) -> None:
    """Wikimedia yoğunlukta 429 dönebilir: bekleyip tekrar dene, olmazsa orijinal dosyayı indir."""
    import time
    for deneme, adres in enumerate([url, url, yedek_url or url, yedek_url or url]):
        r = requests.get(adres, headers=UA, timeout=60)
        if r.ok:
            hedef.write_bytes(r.content)
            return
        print(f"[uyarı] görsel indirilemedi ({r.status_code}), tekrar denenecek")
        time.sleep(int(r.headers.get("Retry-After", 0) or 0) or 10 * (deneme + 1))
    r.raise_for_status()
