"""Bugün Türkiye'de önemli bir gün mü? Öyleyse o günün bilgisini döndürür."""
import datetime as dt
import json
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def _ayin_n_inci_gunu(yil: int, ay: int, hafta: int, haftagunu: int) -> dt.date:
    """Örn. Mayıs'ın 2. Pazar'ı (haftagunu: Pazartesi=0 ... Pazar=6)."""
    gun = dt.date(yil, ay, 1)
    fark = (haftagunu - gun.weekday()) % 7
    return gun + dt.timedelta(days=fark + 7 * (hafta - 1))


def bugun_ozel_mi(tarih: dt.date, marka: str | None = None) -> dict | None:
    veri = json.loads((KOK / "veri/ozel_gunler.json").read_text(encoding="utf-8"))
    bulunan = veri["tarihli"].get(tarih.isoformat()) or veri["sabit"].get(tarih.strftime("%m-%d"))
    if not bulunan:
        for kural in veri["kurallar"].values():
            if tarih == _ayin_n_inci_gunu(tarih.year, kural["ay"], kural["hafta"], kural["haftagunu"]):
                bulunan = kural
                break
    if not bulunan:
        return None
    if marka and bulunan.get("markalar") and marka not in bulunan["markalar"]:
        return None
    gun = dict(bulunan)
    if "yil_baslangic" in gun:
        gun["mesaj"] = gun["mesaj"].replace("{yil}", str(tarih.year - gun["yil_baslangic"]))
    return gun
