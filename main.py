import pygame as py
import sys
import math
import json
from pathlib import Path
from typing import Tuple
import config
from Loader import ConfigLoader
from Graf import MenedzerGrafu
from Menedzer_pociagow import MenedzerPociagow
from Pociag import Pociag
from Rozklad_jazdy import RozkladPociagu, SledzenieRozkladu, Przystanek
from Zegar_symulacji import ZegarSymulacji
from Wizualizacja import SilnikGraficzny
from Wezly import Kierunek, Sygnal, Zwrot, kierunek_przeciwny
from Komunikacja_USB import MostKomunikacjiUSB
from Edytor_mapy import EdytorMapy


def _wybierz_plik_konfiguracji(argv: list[str]) -> str:
    domyslny = "sim_config.json"
    edytorowy = "sim_config_edytor.json"

    if "--editor-config" in argv and Path(edytorowy).exists():
        return edytorowy

    if "--config" in argv:
        idx = argv.index("--config")
        if idx + 1 < len(argv):
            return argv[idx + 1]

    return domyslny


def _podpis_pociagow(pociagi: list) -> str:
    return json.dumps(pociagi, sort_keys=True, ensure_ascii=True)


def _podpis_edytora(edytor: EdytorMapy) -> Tuple[int, str]:
    return (
        edytor.wersja_zmian,
        _podpis_pociagow(edytor.projekt.get("pociagi", [])),
    )


def _zwolnij_kafelki_pociagu(graf: MenedzerGrafu, pociag: Pociag) -> None:
    for id_kafelka in pociag.id_zajetych_kafelkow:
        wezel = graf.wezly.get(id_kafelka)
        if wezel and wezel.pociag_id == pociag.id_pociagu:
            wezel.zajety = False
            wezel.pociag_id = None


def _kierunek_startowy_z_danych(dane: dict) -> Kierunek:
    nazwa_kierunku = str(dane.get("kierunek_startowy", Kierunek.ZACHOD.name)).strip().upper()
    try:
        return Kierunek[nazwa_kierunku]
    except KeyError:
        if config.DEBUG_MODE:
            print(f"[DEBUG] Nieznany kierunek_startowy '{nazwa_kierunku}', uzywam ZACHOD")
        return Kierunek.ZACHOD


def _odtworz_pociagi_z_projektu(graf: MenedzerGrafu, skaler, menedzer_pociagow: MenedzerPociagow, dane_pociagow: list) -> None:
    for pociag in menedzer_pociagow.pociagi.values():
        _zwolnij_kafelki_pociagu(graf, pociag)

    menedzer_pociagow.pociagi.clear()
    menedzer_pociagow.sledzenie_rozkladow.clear()
    menedzer_pociagow._poprzedni_stan_rozkladu.clear()

    for dane in dane_pociagow:
        try:
            pociag = Pociag(
                id_pociagu=dane["id"],
                typ_pociagu=dane["typ"],
                masa=float(dane["masa"]),
                predkosc_max_kmh=float(dane["max_predkosc_kmh"]),
                przyspieszenie_ms2=float(dane["przyspieszenie_bazowe"]),
                hamowanie_ms2=float(dane["hamowanie_bazowe"]),
                dlugosc_w_kafelkach=int(dane["dlugosc"]),
                skaler=skaler,
            )

            przystanki = []
            for dane_rozklad in dane.get("rozklad", []):
                przystanki.append(
                    Przystanek(
                        id_stacji=dane_rozklad["id_stacji"],
                        czas_przyjazdu=dane_rozklad.get("przyjazd"),
                        czas_odjazdu=dane_rozklad.get("odjazd"),
                        czas_postoju=float(dane_rozklad.get("czas_postoju", 10.0)),
                    )
                )

            rozklad = RozkladPociagu(f"R_{dane['id']}", przystanki)
            sledzenie = SledzenieRozkladu(rozklad)

            start_x = dane["pozycja_startowa"]["x"]
            start_y = dane["pozycja_startowa"]["y"]
            start_id = None
            for wezel in graf.wezly.values():
                if wezel.x == start_x and wezel.y == start_y:
                    start_id = wezel.id_wezel
                    break

            if not start_id:
                continue

            kierunek_startowy = _kierunek_startowy_z_danych(dane)
            pociag.utworz_pociag(start_id, kierunek_startowy, graf)
            menedzer_pociagow.dodaj_pociag(pociag, sledzenie)
        except (KeyError, TypeError, ValueError):
            continue


def _nastepny_sygnal(sygnal: Sygnal) -> Sygnal:
    kolejnosc = [Sygnal.CZERWONY, Sygnal.ZOLTY, Sygnal.ZIELONY, Sygnal.SZ]
    idx = kolejnosc.index(sygnal)
    return kolejnosc[(idx + 1) % len(kolejnosc)]


def _wektor_kierunku(kierunek: Kierunek) -> tuple[float, float]:
    mapa = {
        Kierunek.POLNOC: (0.0, -1.0),
        Kierunek.POLUDNIE: (0.0, 1.0),
        Kierunek.WSCHOD: (1.0, 0.0),
        Kierunek.ZACHOD: (-1.0, 0.0),
        Kierunek.POLNOC_WSCHOD: (0.7, -0.7),
        Kierunek.POLNOC_ZACHOD: (-0.7, -0.7),
        Kierunek.POLUDNIE_WSCHOD: (0.7, 0.7),
        Kierunek.POLUDNIE_ZACHOD: (-0.7, 0.7),
    }
    return mapa.get(kierunek, (0.0, -1.0))


def _pozycja_semafora_na_ekranie(graf: MenedzerGrafu, silnik: SilnikGraficzny, semafor) -> tuple[float, float] | None:
    wezel_toru = graf.wezly.get(getattr(semafor, "id_toru", ""))
    if not wezel_toru:
        return None

    x_tor, y_tor = silnik.skaler.siatka_na_ekran(wezel_toru.x, wezel_toru.y)
    x_sem, y_sem = silnik.swiat_na_ekran(x_tor, y_tor)
    przes = max(6, int(round(10 * silnik.zoom)))
    wx, wy = _wektor_kierunku(semafor.kierunek_sem)
    return x_sem + wx * przes, y_sem + wy * przes


def _obsluz_klik_symulacji(
    pos,
    graf: MenedzerGrafu,
    menedzer_pociagow: MenedzerPociagow,
    skaler,
    silnik: SilnikGraficzny,
    most_usb: MostKomunikacjiUSB,
    modyfikatory: int = 0,
) -> None:
    x_world, y_world = silnik.ekran_na_swiat(float(pos[0]), float(pos[1]))

    # 1) Najpierw semafory: klik blisko lampy.
    for semafor in graf.semafory.values():
        pozycja_semafora = _pozycja_semafora_na_ekranie(graf, silnik, semafor)
        if pozycja_semafora is None:
            continue
        x_sem, y_sem = pozycja_semafora
        promien_kliku = max(12, int(round(12 * silnik.zoom)))
        if (x_world - x_sem) ** 2 + (y_world - y_sem) ** 2 <= promien_kliku ** 2:
            semafor.ustaw_sygnal(_nastepny_sygnal(semafor.sygnal))
            most_usb.wyslij_zdarzenie(
                "semafor_zmieniony",
                {"semafor_id": semafor.id_semafora, "sygnal": semafor.sygnal.value},
            )
            return

    # 2) Zwrotnice i pociagi wykrywane po kafelku.
    x_siatka, y_siatka = silnik.ekran_na_siatke(pos)
    wezel = graf.znajdz_wezel_po_wspolrzednych(x_siatka, y_siatka)
    if not wezel:
        return

    if wezel.id_wezel in graf.zwrotnice:
        zwrotnica = graf.zwrotnice[wezel.id_wezel]
        nowa_pozycja = Zwrot.MINUS if zwrotnica.pozycja == Zwrot.PLUS else Zwrot.PLUS
        if zwrotnica.ustaw_pozycje(nowa_pozycja):
            most_usb.wyslij_zdarzenie(
                "zwrotnica_przestawiona",
                {"zwrotnica_id": zwrotnica.id_wezel, "pozycja": zwrotnica.pozycja.value},
            )
        return

    if wezel.pociag_id:
        pociag = menedzer_pociagow.pociagi.get(wezel.pociag_id)
        if not pociag:
            return

        if modyfikatory & py.KMOD_CTRL:
            nowy_kierunek = kierunek_przeciwny(pociag.aktualny_kierunek)
            if nowy_kierunek and pociag.ustaw_kierunek_ruchu(nowy_kierunek, graf, sprawdz_przejazd=True):
                most_usb.wyslij_zdarzenie(
                    "pociag_zmienil_kierunek",
                    {
                        "pociag_id": pociag.id_pociagu,
                        "kierunek": pociag.aktualny_kierunek.value,
                    },
                )
            return

        pociag.wymuszony_postoj = not pociag.wymuszony_postoj
        pociag.predkosc_docelowa_pxs = 0.0 if pociag.wymuszony_postoj else pociag.predkosc_max_pxs
        most_usb.wyslij_zdarzenie(
            "pociag_reczny_postoj",
            {
                "pociag_id": pociag.id_pociagu,
                "aktywny": pociag.wymuszony_postoj,
            },
        )

def main():
    sciezka_konfig = _wybierz_plik_konfiguracji(sys.argv[1:])
    loader = ConfigLoader(sciezka_konfig)
    if not loader.wczytaj_konfiguracje():
        print("[FATAL ERROR] Nie udało się wczytać konfiguracji. Przerwanie programu.")
        sys.exit(1)

    skaler = loader.scaler
    szerokosc_okna = 1600
    wysokosc_okna = 900

    zegar = ZegarSymulacji(wspolczynnik_czasu=loader.wspolczynnik_czasu)
    graf = MenedzerGrafu()
    graf.zaladuj_z_slownika(loader.surowe_dane.get("infrastruktura", {}))

    zasieg_widoku_m = float(loader.ustawienia_symulacji.get("zasieg_widoku_m", 50.0))
    zasieg_widoku_kafelki = max(1, math.ceil(zasieg_widoku_m / skaler.skala_w_metrach))
    menedzer_pociagow = MenedzerPociagow(
        graf=graf,
        zasieg_widoku_kafelki=zasieg_widoku_kafelki,
    )

    if config.DEBUG_MODE:
        print(
            f"[DEBUG] Zasięg patrzenia w przód: {zasieg_widoku_m} m "
            f"(~{zasieg_widoku_kafelki} kafelków)"
        )

    _odtworz_pociagi_z_projektu(graf, skaler, menedzer_pociagow, loader.pociagi)

    ustawienia_usb = loader.ustawienia_symulacji.get("usb", {})
    most_usb = MostKomunikacjiUSB(
        graf=graf,
        menedzer_pociagow=menedzer_pociagow,
        zegar=zegar,
        wlaczony=bool(ustawienia_usb.get("wlaczony", False)),
        port=ustawienia_usb.get("port"),
        baudrate=int(ustawienia_usb.get("baudrate", 115200)),
        timeout=float(ustawienia_usb.get("timeout", 0.0)),
    )

    silnik = SilnikGraficzny(szerokosc_okna, wysokosc_okna, skaler)
    zegar_pygame = py.time.Clock()
    edytor = EdytorMapy(projekt=loader.surowe_dane)
    pauza_przed_edytorem = False
    podpis_edytora = _podpis_edytora(edytor)

    dziala = True
    ostatnia_pozycja_pan = None
    #graf.zwrotnice["T07"].ustaw_pozycje(Zwrot.MINUS)
    #graf.zwrotnice["T16"].ustaw_pozycje(Zwrot.MINUS)
    
    while dziala:
        rzeczywista_delta_czasu = zegar_pygame.tick(60) / 1000.0
        most_usb.obsluz_wejscie()

        for zdarzenie in py.event.get():
            if zdarzenie.type == py.QUIT:
                dziala = False
            elif zdarzenie.type == py.KEYDOWN:
                if zdarzenie.key == py.K_e or zdarzenie.key == py.K_F2:
                    aktywny = edytor.przelacz()
                    if aktywny:
                        #silnik.resetuj_widok()
                        pauza_przed_edytorem = zegar.pauza
                        if not zegar.pauza:
                            zegar.przelacz_pauze()
                    elif zegar.pauza != pauza_przed_edytorem:
                        zegar.przelacz_pauze()
                    continue
                elif zdarzenie.key == py.K_KP0 or zdarzenie.key == py.K_0:
                    silnik.resetuj_widok()
                    continue
                elif zdarzenie.key == py.K_ESCAPE:
                    dziala = False
                    continue

                if edytor.aktywny and edytor.obsluz_zdarzenie(
                    zdarzenie,
                    graf,
                    skaler,
                    ekran_na_swiat=silnik.ekran_na_swiat,
                ):
                    continue

                if not edytor.aktywny and zdarzenie.key == py.K_SPACE:
                    zegar.przelacz_pauze()
                if zdarzenie.key in {py.K_PLUS, py.K_KP_PLUS, py.K_EQUALS}:
                    silnik.ustaw_zoom(1)
                    continue
                if zdarzenie.key in {py.K_MINUS, py.K_KP_MINUS}:
                    silnik.ustaw_zoom(-1)
                    continue
            elif zdarzenie.type == py.MOUSEBUTTONDOWN and zdarzenie.button == 1:
                if edytor.aktywny:
                    if edytor.obsluz_zdarzenie(
                        zdarzenie,
                        graf,
                        skaler,
                        ekran_na_swiat=silnik.ekran_na_swiat,
                    ):
                        continue
                else:
                    _obsluz_klik_symulacji(
                        zdarzenie.pos,
                        graf,
                        menedzer_pociagow,
                        skaler,
                        silnik,
                        most_usb,
                        modyfikatory=py.key.get_mods(),
                    )
            elif zdarzenie.type == py.MOUSEBUTTONDOWN and zdarzenie.button == 2:
                ostatnia_pozycja_pan = zdarzenie.pos
            elif zdarzenie.type == py.MOUSEBUTTONUP and zdarzenie.button == 2:
                ostatnia_pozycja_pan = None
            elif zdarzenie.type == py.MOUSEMOTION:
                if ostatnia_pozycja_pan is not None:
                    dx = zdarzenie.pos[0] - ostatnia_pozycja_pan[0]
                    dy = zdarzenie.pos[1] - ostatnia_pozycja_pan[1]
                    silnik.przesun_widok(dx, dy)
                    ostatnia_pozycja_pan = zdarzenie.pos
            elif zdarzenie.type == py.MOUSEWHEEL:
                if edytor.aktywny and edytor.obsluz_zdarzenie(
                    zdarzenie,
                    graf,
                    skaler,
                    ekran_na_swiat=silnik.ekran_na_swiat,
                ):
                    continue
                silnik.ustaw_zoom(zdarzenie.y, py.mouse.get_pos())
            elif zdarzenie.type == py.MOUSEBUTTONDOWN and zdarzenie.button in {4, 5}:
                if edytor.aktywny and edytor.obsluz_zdarzenie(
                    zdarzenie,
                    graf,
                    skaler,
                    ekran_na_swiat=silnik.ekran_na_swiat,
                ):
                    continue
                silnik.ustaw_zoom(1 if zdarzenie.button == 4 else -1, zdarzenie.pos)
            else:
                if edytor.aktywny and edytor.obsluz_zdarzenie(
                    zdarzenie,
                    graf,
                    skaler,
                    ekran_na_swiat=silnik.ekran_na_swiat,
                ):
                    continue

        nowy_podpis = _podpis_edytora(edytor)
        if nowy_podpis != podpis_edytora:
            if nowy_podpis[0] != podpis_edytora[0]:
                most_usb.odswiez_model_sekcji()

            if nowy_podpis[1] != podpis_edytora[1]:
                _odtworz_pociagi_z_projektu(graf, skaler, menedzer_pociagow, edytor.projekt.get("pociagi", []))

            podpis_edytora = nowy_podpis

        symulowana_delta_czasu = 0.0 if edytor.aktywny else zegar.aktualizuj_czas(rzeczywista_delta_czasu)
        if not zegar.pauza and not edytor.aktywny:
            zdarzenia = menedzer_pociagow.aktualizuj(symulowana_delta_czasu)
            most_usb.wyslij_zdarzenia_symulacji(zdarzenia, zegar.obecna_data())

        silnik.renderuj_klatke(graf, menedzer_pociagow, zegar.obecny_czas(), edytor=edytor)

    most_usb.zamknij()
    silnik.zamknij()

if __name__ == "__main__":
    main()