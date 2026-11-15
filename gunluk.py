"""Günlük Instagram hikayesi: üret ve yayınla.

  python gunluk.py uret      [--tarih 2026-11-15] [--test]
  python gunluk.py yayinla   [--tarih 2026-11-15]
  python gunluk.py onizle    --tarih 2027-10-29 [--test]   (yayınlamadan görsel üretir)

Çıktılar: yayin/<tarih>/<marka>.jpg ve yayin/<tarih>/bilgi.json
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from hikaye import gorsel, ozel_gunler

KOK = Path(__file__).resolve().parent
TR = ZoneInfo("Europe/Istanbul")
AYLAR = ["OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ",
         "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"]


def markalari_oku() -> dict:
    return json.loads((KOK / "veri/markalar.json").read_text(encoding="utf-8"))


def kaynak_satiri(g: dict) -> str:
    sahibi = re.sub(r"\s*\(.*?\)", "", g.get("sahibi") or "").strip()
    if len(sahibi) > 45:
        sahibi = sahibi[:44].rsplit(" ", 1)[0] + "…"
    parcalar = [f"Görsel: {sahibi}" if sahibi else "Görsel", g.get("lisans", ""), "Wikimedia Commons"]
    return " · ".join(p for p in parcalar if p)


def uret(tarih: dt.date, test: bool = False) -> Path:
    markalar = markalari_oku()
    klasor = KOK / "yayin" / tarih.isoformat()
    klasor.mkdir(parents=True, exist_ok=True)
    tarih_metni = f"{tarih.day} {AYLAR[tarih.month - 1]} {tarih.year}"
    bilgi = {"tarih": tarih.isoformat(), "markalar": {}}
    sayfalar = {}

    # 1) Hazır tasarım bırakıldıysa onu kullan: assets/ozel/<AA-GG>_<marka>.jpg
    # 2) Türkiye'de önemli bir gün mü?  3) Değilse "Geçmişte Bugün"
    ozel = {m: ozel_gunler.bugun_ozel_mi(tarih, m) for m in markalar}
    gecmis_gerekenler = []
    for m, marka in markalar.items():
        hazir = KOK / "assets/ozel" / f"{tarih:%m-%d}_{m}.jpg"
        if hazir.exists():
            shutil.copy(hazir, klasor / f"{m}.jpg")
            bilgi["markalar"][m] = {"tur": "hazir_tasarim", "dosya": hazir.name}
        elif ozel[m]:
            sayfalar[m] = gorsel.ozel_gun_html(ozel[m], tarih_metni, marka)
            bilgi["markalar"][m] = {"tur": "ozel_gun", **ozel[m]}
        else:
            gecmis_gerekenler.append(m)

    if gecmis_gerekenler:
        secim, adaylar = _gecmiste_bugun_sec(tarih, {m: markalar[m] for m in gecmis_gerekenler}, test)
        for m in gecmis_gerekenler:
            s = secim[m]
            aday = next(a for a in adaylar if a["id"] == s["id"])
            g = next(x for x in aday["gorseller"] if x["dosya"] == s["dosya"])
            foto = klasor / f"_foto_{m}{Path(g['dosya']).suffix.lower() or '.jpg'}"
            if test:
                shutil.copy(g["yerel"], foto)
            else:
                from hikaye import wiki
                wiki.gorsel_indir(g["indir_url"], foto, g.get("orijinal_url"))
            icerik = {**s, "kaynak": kaynak_satiri(g)}
            # Tasarımlar gün gün sırayla değişir (gazete, büyük yıl, gazete, ...)
            liste = markalar[m].get("sablonlar") or ["hikaye"]
            sablon = liste[tarih.toordinal() % len(liste)]
            sayfalar[m] = gorsel.gecmiste_bugun_html(icerik, foto, markalar[m], sablon)
            icerik["sablon"] = sablon
            bilgi["markalar"][m] = {"tur": "gecmiste_bugun", **icerik, "olay": aday["metin"], "yil": aday["yil"],
                                    "gorsel_sayfasi": g.get("sayfa_url"), "lisans": g.get("lisans")}

    gorsel.html_den_jpeg(sayfalar, klasor)
    for f in klasor.glob("_foto_*"):
        f.unlink()
    (klasor / "bilgi.json").write_text(json.dumps(bilgi, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(bilgi, ensure_ascii=False, indent=2))
    return klasor


def _gecmiste_bugun_sec(tarih, markalar, test):
    if test:
        adaylar = json.loads((KOK / "tests/ornek_adaylar.json").read_text(encoding="utf-8"))
        for a in adaylar:
            for g in a["gorseller"]:
                g["yerel"] = str(KOK / g["yerel"])
        secim = json.loads((KOK / "tests/ornek_secim.json").read_text(encoding="utf-8"))
        return secim, adaylar
    from hikaye import secici, wiki
    adaylar = wiki.adaylari_topla(tarih, en_fazla=60)
    if not adaylar:
        raise RuntimeError("Bugün için görseli uygun hiçbir olay bulunamadı.")
    tarih_metni = f"{tarih.day} {AYLAR[tarih.month - 1].capitalize()}"
    return secici.sec(adaylar, markalar, tarih_metni), adaylar


def yayinla(tarih: dt.date) -> None:
    from hikaye import instagram
    klasor = KOK / "yayin" / tarih.isoformat()
    bilgi_yolu = klasor / "bilgi.json"
    bilgi = json.loads(bilgi_yolu.read_text(encoding="utf-8"))
    depo = os.environ["GITHUB_REPOSITORY"]
    dal = os.environ.get("GITHUB_REF_NAME", "main")
    hatalar = []
    markalar = markalari_oku()
    for m, kayit in bilgi["markalar"].items():
        if kayit.get("yayin_id"):
            print(f"{m}: zaten yayınlanmış, atlanıyor.")
            continue
        ig_id = os.environ.get(f"IG_ID_{m.upper()}") or markalar[m].get("ig_id")
        # Tek bir sistem kullanıcısı token'ı iki hesaba da yeter: IG_TOKEN; istenirse marka bazlı IG_TOKEN_<MARKA>
        token = os.environ.get(f"IG_TOKEN_{m.upper()}") or os.environ.get("IG_TOKEN")
        if not ig_id or not token:
            hatalar.append(f"{m}: Instagram kimliği ya da IG_TOKEN tanımlı değil")
            continue
        url = f"https://raw.githubusercontent.com/{depo}/{dal}/yayin/{tarih.isoformat()}/{m}.jpg"
        try:
            kayit["yayin_id"] = instagram.hikaye_paylas(ig_id, token, url)
            kayit["yayin_zamani"] = dt.datetime.now(TR).isoformat(timespec="seconds")
            print(f"{m}: yayınlandı ({kayit['yayin_id']})")
        except Exception as e:
            hatalar.append(f"{m}: {e}")
    bilgi_yolu.write_text(json.dumps(bilgi, ensure_ascii=False, indent=2), encoding="utf-8")
    if hatalar:
        sys.exit("Yayın hataları:\n" + "\n".join(hatalar))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("islem", choices=["uret", "yayinla", "onizle"])
    ap.add_argument("--tarih", help="YYYY-AA-GG (varsayılan: bugün, Türkiye saati)")
    ap.add_argument("--test", action="store_true", help="İnternete çıkmadan örnek verilerle dene")
    a = ap.parse_args()
    tarih = dt.date.fromisoformat(a.tarih) if a.tarih else dt.datetime.now(TR).date()
    if a.islem in ("uret", "onizle"):
        uret(tarih, test=a.test)
    else:
        yayinla(tarih)
