import pygame as py
import sys
import datetime
import config
from Loader import ConfigLoader
from Graf import MenedzerGrafu
from Menedzer_pociagow import MenedzerPociagow
from Pociag import Pociag
from Rozklad_jazdy import RozkladPociagu, SledzenieRozkladu, Przystanek
from Zegar_symulacji import ZegarSymulacji
from Wizualizacja import SilnikGraficzny
from Wezly import Kierunek, Zwrot

def main():
    loader = ConfigLoader("sim_config.json")
    if not loader.wczytaj_konfiguracje():
        print("[FATAL ERROR] Nie udało się wczytać konfiguracji. Przerwanie programu.")
        sys.exit(1)

    skaler = loader.scaler
    szerokosc_okna = 1600
    wysokosc_okna = 900

    zegar = ZegarSymulacji(wspolczynnik_czasu=loader.wspolczynnik_czasu)
    graf = MenedzerGrafu()
    graf.zaladuj_z_slownika(loader.surowe_dane.get("infrastruktura", {}))

    menedzer_pociagow = MenedzerPociagow(graf=graf)

    for dane in loader.pociagi:
        pociag = Pociag(
            id_pociagu=dane["id"],
            typ_pociagu=dane["typ"],
            masa=dane["masa"],
            predkosc_max_kmh=dane["max_predkosc_kmh"],
            przyspieszenie_ms2=dane["przyspieszenie_bazowe"],
            hamowanie_ms2=dane["hamowanie_bazowe"],
            dlugosc_w_kafelkach=dane["dlugosc"],
            skaler=skaler
            )

        przystanki = []
        for dane_rozklad in dane.get("rozklad", []):
            przystanki.append(Przystanek(
                id_stacji=dane_rozklad["id_stacji"],
                czas_przyjazdu=dane_rozklad.get("przyjazd"),
                czas_odjazdu=dane_rozklad.get("odjazd"),
                czas_postoju=10.0
                ))

        rozklad = RozkladPociagu(f"R_{dane['id']}", przystanki)
        sledzenie = SledzenieRozkladu(rozklad)

        start_x, start_y = dane["pozycja_startowa"]["x"], dane["pozycja_startowa"]["y"]

        start_id = None
        for wezel in graf.wezly.values():
            if wezel.x == start_x and wezel.y == start_y:
                start_id = wezel.id_wezel
                break

        if start_id:
            pociag.utworz_pociag(start_id,Kierunek.ZACHOD,graf)
            menedzer_pociagow.dodaj_pociag(pociag, sledzenie)

    silnik = SilnikGraficzny(szerokosc_okna, wysokosc_okna, skaler)
    zegar_pygame = py.time.Clock()

    dziala = True
    #graf.zwrotnice["T07"].ustaw_pozycje(Zwrot.MINUS)
    #graf.zwrotnice["T16"].ustaw_pozycje(Zwrot.MINUS)
    
    while dziala:
        rzeczywista_delta_czasu = zegar_pygame.tick(60) / 1000.0

        for zdarzenie in py.event.get():
            if zdarzenie.type == py.QUIT:
                dziala = False
            elif zdarzenie.type == py.KEYDOWN:
                if zdarzenie.key == py.K_SPACE:
                    zegar.przelacz_pauze()

        symulowana_delta_czasu = zegar.aktualizuj_czas(rzeczywista_delta_czasu)
        if not zegar.pauza:
            menedzer_pociagow.aktualizuj(symulowana_delta_czasu)

        silnik.renderuj_klatke(graf, menedzer_pociagow, zegar.obecny_czas())

    silnik.zamknij()

if __name__ == "__main__":
    main()