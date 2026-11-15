"""Hikaye görselini (1080x1920 JPEG) HTML şablondan üretir."""
import html
from pathlib import Path
from playwright.sync_api import sync_playwright

KOK = Path(__file__).resolve().parent.parent

# Özel gün türüne göre tema ayarı
OZEL_TEMA = {
    "milli": {"vurgu": "#E30A17"},                     # bayrak kırmızısı
    "anma": {"vurgu": "{soluk}"},                       # sade, renksiz
    "kutlama": {},                                      # marka rengi
}


def _tema_css(tema: dict) -> str:
    return ":root{" + "".join(f"--{k}:{v};" for k, v in tema.items()) + "}"


def _logo(marka: dict) -> str:
    temel = (KOK / marka["logo"]).with_suffix("")
    for uzanti in (".svg", ".png"):  # SVG varsa o kullanılır (her boyutta keskin)
        yol = temel.with_suffix(uzanti)
        if yol.exists():
            return f'<img src="{yol.as_uri()}">'
    return f'<span class="yazi-logo">{marka["logo_yedek"]}</span>'


def _baslik_px(metin: str, ozel=False) -> int:
    n = len(metin)
    tablo = [(30, 96), (45, 86), (70, 74), (95, 64)] if ozel else [(45, 82), (70, 72), (95, 64)]
    for sinir, px in tablo:
        if n <= sinir:
            return px
    return 56


def _doldur(sablon: str, degerler: dict) -> str:
    for k, v in degerler.items():
        sablon = sablon.replace("{{" + k + "}}", v)
    return sablon


def gecmiste_bugun_html(icerik: dict, foto: Path, marka: dict) -> str:
    sablon = (KOK / "sablonlar/hikaye.html").read_text(encoding="utf-8")
    e = html.escape
    return _doldur(sablon, {
        "foto": foto.resolve().as_uri(),
        "kaynak": e(icerik.get("kaynak", "")),
        "tarih": e(icerik["tarih"]),
        "baslik": e(icerik["baslik"]),
        "baslik_px": str(_baslik_px(icerik["baslik"])),
        "aciklama": e(icerik.get("aciklama", "")),
        "tema_css": _tema_css(marka["tema"]),
        "logo": _logo(marka),
    })


def ozel_gun_html(gun: dict, tarih_metni: str, marka: dict) -> str:
    sablon = (KOK / "sablonlar/ozel_gun.html").read_text(encoding="utf-8")
    tema = dict(marka["tema"])
    for k, v in OZEL_TEMA.get(gun.get("tur"), {}).items():
        tema[k] = v.format(**tema)
    e = html.escape
    return _doldur(sablon, {
        "ust_baslik": "BUGÜN",
        "tarih": e(tarih_metni),
        "baslik": e(gun["baslik"]),
        "baslik_px": str(_baslik_px(gun["baslik"], ozel=True)),
        "mesaj": e(gun["mesaj"]),
        "tema_css": _tema_css(tema),
        "logo": _logo(marka),
    })


def html_den_jpeg(sayfalar: dict[str, str], klasor: Path) -> dict[str, Path]:
    """{ad: html} -> {ad: jpeg yolu}. Instagram hikaye görseli JPEG olmalı."""
    klasor.mkdir(parents=True, exist_ok=True)
    sonuc = {}
    with sync_playwright() as p:
        chrome = next((y for y in ("/usr/bin/google-chrome", "/usr/bin/chromium") if Path(y).exists()), None)
        tarayici = p.chromium.launch(executable_path=chrome)
        sekme = tarayici.new_page(viewport={"width": 1080, "height": 1920})
        for ad, icerik in sayfalar.items():
            gecici = KOK / "sablonlar" / f"_gecici_{ad}.html"  # göreli font yolları çalışsın diye
            gecici.write_text(icerik, encoding="utf-8")
            try:
                sekme.goto(gecici.as_uri())
                sekme.wait_for_load_state("networkidle")
                sekme.evaluate("document.fonts.ready")
                yol = klasor / f"{ad}.jpg"
                sekme.screenshot(path=str(yol), type="jpeg", quality=92)
                sonuc[ad] = yol
            finally:
                gecici.unlink(missing_ok=True)
        tarayici.close()
    return sonuc
