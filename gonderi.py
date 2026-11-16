"""Günlük iş hikayesi: her hesap kendi eski iş fotoğraflarından birini
yeni tasarımla tam ekran hikaye (1080x1920) olarak paylaşır.
(Instagram API akışta 9:16 görsel kabul etmediği için hikaye olarak paylaşılır.)

  python gonderi.py uret     [--tarih 2026-11-16] [--marka canwedding]
  python gonderi.py yayinla  [--tarih 2026-11-16]

Çıktılar: yayin/gonderi/<tarih>/<marka>.jpg ve bilgi.json
Kullanılan fotoğraflar veri/kullanilan_medya.json'da tutulur, tekrar seçilmez.
"""
import argparse
import datetime as dt
import json
import os
import random
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from hikaye import gorsel, instagram, secici

KOK = Path(__file__).resolve().parent
TR = ZoneInfo("Europe/Istanbul")
KULLANILAN = KOK / "veri/kullanilan_medya.json"
ONCELIKLI_YIL = 2025      # bu yıl ve sonrasındaki gönderilere öncelik
EN_YENI_GUN = 60          # son 60 günün gönderilerine dokunma (tekrar hissi olmasın)


def _oku(yol, varsayilan):
    return json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else varsayilan


def _yaz(yol, veri):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")


def _token(m):
    return os.environ.get(f"IG_TOKEN_{m.upper()}") or os.environ["IG_TOKEN"]


def aday_fotograflar(medyalar: list[dict], kullanilan: set, bugun: dt.date) -> list[dict]:
    """Eski, daha önce kullanılmamış fotoğraflar. Albümlerde ilk fotoğraf alınır; videolar atlanır."""
    sinir = bugun - dt.timedelta(days=EN_YENI_GUN)
    adaylar = []
    for m in medyalar:
        if m["id"] in kullanilan or m.get("media_product_type") not in (None, "FEED"):
            continue
        if dt.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")).date() > sinir:
            continue
        url = None
        if m.get("media_type") == "IMAGE":
            url = m.get("media_url")
        elif m.get("media_type") == "CAROUSEL_ALBUM":
            ilk = next((c for c in (m.get("children") or {}).get("data", []) if c.get("media_type") == "IMAGE"), None)
            url = ilk and ilk.get("media_url")
        if url:
            adaylar.append({**m, "foto_url": url})
    return adaylar


def uret(tarih: dt.date, sadece=None) -> Path:
    markalar = json.loads((KOK / "veri/markalar.json").read_text(encoding="utf-8"))
    klasor = KOK / "yayin/gonderi" / tarih.isoformat()
    klasor.mkdir(parents=True, exist_ok=True)
    bilgi_yolu = klasor / "bilgi.json"
    bilgi = _oku(bilgi_yolu, {"tarih": tarih.isoformat(), "markalar": {}})
    kullanilan = _oku(KULLANILAN, {})
    rnd = random.Random(tarih.toordinal())
    sayfalar = {}
    for m, marka in markalar.items():
        if (sadece and m != sadece) or m in bilgi["markalar"]:
            continue
        ig_id = marka["ig_id"]
        medyalar = instagram.medya_listesi(ig_id, _token(m))
        # Bizim yaptığımız iş gönderilerini de kaynak olarak kullanma
        kendi = set(kullanilan.get(m, {}).get("paylasilan", []))
        secilmis = set(kullanilan.get(m, {}).get("kaynak", []))
        adaylar = [a for a in aday_fotograflar(medyalar, secilmis, tarih) if a["id"] not in kendi]
        print(f"[bilgi] {m}: {len(medyalar)} gönderi, {len(adaylar)} uygun eski fotoğraf")
        if not adaylar:
            print(f"[uyarı] {m}: kullanılabilecek eski fotoğraf kalmadı, bugün atlanıyor")
            continue
        # Öncelik 2025 ve sonrası; o yıllardan uygun fotoğraf kalmadıysa eskilere geçilir
        yeni = [a for a in adaylar if int(a["timestamp"][:4]) >= ONCELIKLI_YIL]
        print(f"[bilgi] {m}: {ONCELIKLI_YIL}+ uygun fotoğraf: {len(yeni)}")
        adaylar = yeni or adaylar
        rnd.shuffle(adaylar)
        foto = klasor / f"_foto_{m}.jpg"
        metin = None
        for aday in adaylar[:6]:   # reklam görseli çıkarsa sıradakini dene
            r = requests.get(aday["foto_url"], timeout=60)
            r.raise_for_status()
            metin = secici.gonderi_metni(r.content, aday.get("caption", ""), marka)
            if metin.get("urun_fotografi") is not False:
                break
            print(f"[bilgi] {m}: {aday.get('permalink')} ürün fotoğrafı değil, atlandı")
            kullanilan.setdefault(m, {}).setdefault("kaynak", []).append(aday["id"])
            metin = None
        if not metin:
            print(f"[uyarı] {m}: uygun ürün fotoğrafı bulunamadı, bugün atlanıyor")
            continue
        foto.write_bytes(r.content)
        sayfalar[m] = gorsel.is_hikayesi_html(metin["slogan"], metin.get("alt_satir", ""), foto, marka)
        bilgi["markalar"][m] = {**metin, "kaynak_id": aday["id"], "kaynak_link": aday.get("permalink")}
        kullanilan.setdefault(m, {}).setdefault("kaynak", []).append(aday["id"])
    if sayfalar:
        gorsel.html_den_jpeg(sayfalar, klasor)
    for f in klasor.glob("_foto_*"):
        f.unlink()
    _yaz(bilgi_yolu, bilgi)
    _yaz(KULLANILAN, kullanilan)
    print(json.dumps(bilgi, ensure_ascii=False, indent=2))
    return klasor


def yayinla(tarih: dt.date) -> None:
    markalar = json.loads((KOK / "veri/markalar.json").read_text(encoding="utf-8"))
    bilgi_yolu = KOK / "yayin/gonderi" / tarih.isoformat() / "bilgi.json"
    bilgi = _oku(bilgi_yolu, {"markalar": {}})
    kullanilan = _oku(KULLANILAN, {})
    depo, dal = os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_REF_NAME", "main")
    hatalar = []
    for m, kayit in bilgi["markalar"].items():
        if kayit.get("yayin_id"):
            print(f"{m}: zaten paylaşılmış, atlanıyor."); continue
        url = f"https://raw.githubusercontent.com/{depo}/{dal}/yayin/gonderi/{tarih.isoformat()}/{m}.jpg"
        try:
            kayit["yayin_id"] = instagram.hikaye_paylas(markalar[m]["ig_id"], _token(m), url)
            kayit["yayin_zamani"] = dt.datetime.now(TR).isoformat(timespec="seconds")
            kullanilan.setdefault(m, {}).setdefault("paylasilan", []).append(kayit["yayin_id"])
            print(f"{m}: paylaşıldı ({kayit['yayin_id']})")
        except Exception as e:
            hatalar.append(f"{m}: {e}")
    _yaz(bilgi_yolu, bilgi)
    _yaz(KULLANILAN, kullanilan)
    if hatalar:
        sys.exit("Paylaşım hataları:\n" + "\n".join(hatalar))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("islem", choices=["uret", "yayinla"])
    ap.add_argument("--tarih")
    ap.add_argument("--marka")
    a = ap.parse_args()
    tarih = dt.date.fromisoformat(a.tarih) if a.tarih else dt.datetime.now(TR).date()
    uret(tarih, a.marka) if a.islem == "uret" else yayinla(tarih)
