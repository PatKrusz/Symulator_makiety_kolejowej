import pygame as py
import math
from typing import Dict, Optional, Tuple
import config
from Graf import MenedzerGrafu
from Menedzer_pociagow import MenedzerPociagow
from Loader import Skaler
from Wezly import Kierunek, WezelSemafora, WezelZwrotnicy, Sygnal, Zwrot, kierunek_przeciwny

# Kolory
KOLORY = {
    "TLO": (30, 30, 30),
    "SIATKA": (50, 50, 50),
    "TOR": (150, 150, 150),
    "TOR_AKTYWNY": (50, 220, 100),       # Jasnozielony dla aktywnego toru zwrotnicy
    "TOR_NIEAKTYWNY": (80, 80, 80),      # Przyciemniony dla odgałęzienia nieaktywnego
    "POCIAG": (50, 150, 255),
    "STACJA": (100, 100, 200, 100),       # Z kanałem alpha
    "TEKST": (255, 255, 255),
    "KIERUNEK": (0, 0, 0),
    Sygnal.CZERWONY: (255, 50, 50),
    Sygnal.ZIELONY: (50, 255, 50),
    Sygnal.ZOLTY: (255, 255, 50),
    Sygnal.SZ: (250, 250, 250)
}

class SilnikGraficzny:
    """Klasa odpowiedzialna za rysowanie makiety i pociągów przy użyciu Pygame"""

    def __init__(self, szerokosc: int, wysokosc: int, skaler: Skaler):
        py.init()
        self.ekran = py.display.set_mode((szerokosc, wysokosc), py.RESIZABLE)
        py.display.set_caption("Symulator Makiety Kolejowej")

        self.skaler = skaler
        self.czcionka = py.font.SysFont("arial", 12)
        self.czcionka_duza = py.font.SysFont("arial", 16, bold=True)

        self.powierzchnia_alfa = py.Surface((szerokosc, wysokosc), py.SRCALPHA)

        self.zoom: float = 1.0
        self.zoom_min: float = 0.35
        self.zoom_max: float = 3.0
        self.przesuniecie_x: float = 0.0
        self.przesuniecie_y: float = 0.0

    def resetuj_widok(self) -> None:
        self.zoom = 1.0
        self.przesuniecie_x = 0.0
        self.przesuniecie_y = 0.0

    def swiat_na_ekran(self, x: float, y: float) -> Tuple[float, float]:
        return (x * self.zoom + self.przesuniecie_x, y * self.zoom + self.przesuniecie_y)

    def ekran_na_swiat(self, x: float, y: float) -> Tuple[float, float]:
        return ((x - self.przesuniecie_x) / self.zoom, (y - self.przesuniecie_y) / self.zoom)

    def ekran_na_siatke(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        x_swiat, y_swiat = self.ekran_na_swiat(float(pos[0]), float(pos[1]))
        return int(x_swiat // self.skaler.rozmiar_kafelka_px), int(y_swiat // self.skaler.rozmiar_kafelka_px)

    def ustaw_zoom(self, kierunek: int, punkt_ekranu: Optional[Tuple[int, int]] = None) -> None:
        if kierunek == 0:
            return

        stary_zoom = self.zoom
        nowy_zoom = self.zoom * (1.12 if kierunek > 0 else 1.0 / 1.12)
        nowy_zoom = max(self.zoom_min, min(self.zoom_max, nowy_zoom))
        if abs(nowy_zoom - stary_zoom) < 1e-6:
            return

        if punkt_ekranu is None:
            punkt_ekranu = (self.ekran.get_width() // 2, self.ekran.get_height() // 2)

        wx, wy = self.ekran_na_swiat(float(punkt_ekranu[0]), float(punkt_ekranu[1]))
        self.zoom = nowy_zoom
        self.przesuniecie_x = float(punkt_ekranu[0]) - wx * self.zoom
        self.przesuniecie_y = float(punkt_ekranu[1]) - wy * self.zoom

    def przesun_widok(self, dx: float, dy: float) -> None:
        self.przesuniecie_x += dx
        self.przesuniecie_y += dy

    @staticmethod
    def _wektor_kierunku(kierunek: Kierunek) -> Tuple[float, float]:
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

    def _rysuj_wskaznik_kierunku(self, pozycja: Tuple[float, float], kierunek: Kierunek, kolor: Tuple[int, int, int]) -> None:
        dx, dy = self._wektor_kierunku(kierunek)
        norm = math.hypot(dx, dy) or 1.0
        ux, uy = dx / norm, dy / norm
        px_prostopadly, py_prostopadly = -uy, ux

        cx, cy = pozycja
        rozmiar = max(4, int(round(6 * self.zoom)))
        tip_x = cx + ux * rozmiar
        tip_y = cy + uy * rozmiar
        base_x = cx - ux * rozmiar * 0.7
        base_y = cy - uy * rozmiar * 0.7
        p1 = (int(base_x + px_prostopadly * rozmiar * 0.55), int(base_y + py_prostopadly * rozmiar * 0.55))
        p2 = (int(base_x - px_prostopadly * rozmiar * 0.55), int(base_y - py_prostopadly * rozmiar * 0.55))
        tip = (int(tip_x), int(tip_y))
        py.draw.polygon(self.ekran, kolor, [tip, p1, p2])

    def _pozycja_semafora_na_ekranie(self, graf: MenedzerGrafu, semafor: WezelSemafora) -> Optional[Tuple[float, float]]:
        wezel_toru = getattr(semafor, "id_toru", None)
        if not wezel_toru:
            return None

        tor = graf.wezly.get(wezel_toru)
        if tor is None:
            return None

        x_w, y_w = self.skaler.siatka_na_ekran(tor.x, tor.y)
        x, y = self.swiat_na_ekran(x_w, y_w)
        przes = max(6, int(round(10 * self.zoom)))
        wx, wy = self._wektor_kierunku(semafor.kierunek_sem)
        return x + wx * przes, y + wy * przes

    def rysuj_siatke(self, szerokosc: int, wysokosc: int) -> None:
        """Rysuje siatkę dzielącą przestrzeń na kafelki"""
        rozmiar = self.skaler.rozmiar_kafelka_px
        world_left, world_top = self.ekran_na_swiat(0.0, 0.0)
        world_right, world_bottom = self.ekran_na_swiat(float(szerokosc), float(wysokosc))

        x_start = int(math.floor(world_left / rozmiar) * rozmiar)
        x_end = int(math.ceil(world_right / rozmiar) * rozmiar)
        y_start = int(math.floor(world_top / rozmiar) * rozmiar)
        y_end = int(math.ceil(world_bottom / rozmiar) * rozmiar)

        for x_world in range(x_start, x_end + rozmiar, rozmiar):
            x, _ = self.swiat_na_ekran(float(x_world), 0.0)
            py.draw.line(self.ekran, KOLORY["SIATKA"], (int(x), 0), (int(x), wysokosc))

        for y_world in range(y_start, y_end + rozmiar, rozmiar):
            _, y = self.swiat_na_ekran(0.0, float(y_world))
            py.draw.line(self.ekran, KOLORY["SIATKA"], (0, int(y)), (szerokosc, int(y)))

    def _wyciagnij_wezel_cel(self, element, graf: MenedzerGrafu):
        """Pomocnicza metoda bezpiecznie odczytująca węzeł docelowy."""
        if element is None:
            return None

        if isinstance(element, (tuple, list)) and len(element) > 0:
            element = element[0]

        if isinstance(element, str):
            return graf.wezly.get(element)

        if isinstance(element, dict):
            id_cel = element.get("id_cel") or element.get("cel") or element.get("id")
            return graf.wezly.get(id_cel) if id_cel else None

        for attr in ["id_cel", "cel", "id_wezel", "id"]:
            if hasattr(element, attr):
                val = getattr(element, attr)
                if isinstance(val, str):
                    return graf.wezly.get(val)

        if hasattr(element, "x") and hasattr(element, "y"):
            return element

        return None

    def _wyciagnij_aktywny_cel_zwrotnicy(self, wezel: WezelZwrotnicy, graf: MenedzerGrafu):
        """Określa, który węzeł docelowy odpowiada aktualnemu ustawieniu zwrotnicy."""
        # 1. Sprawdzanie bezpośredniego atrybutu aktywnego celu
        for attr in ["aktywne_id_cel", "aktywny_cel", "id_cel_aktywny"]:
            if hasattr(wezel, attr):
                val = getattr(wezel, attr)
                res = self._wyciagnij_wezel_cel(val, graf)
                if res:
                    return res

        # 2. Sprawdzanie relacji Zwrot -> polaczenie
        zwrot = getattr(wezel, "pozycja", getattr(wezel, "zwrot", getattr(wezel, "stan", None)))
        galezie = getattr(wezel, "polaczenia_zwrotnicy", getattr(wezel, "zwroty", getattr(wezel, "galezie", None)))

        if zwrot is not None and isinstance(galezie, dict):
            cel = galezie.get(zwrot)
            res = self._wyciagnij_wezel_cel(cel, graf)
            if res:
                return res

        # 3. Metody zwrotnicy
        for method_name in ["pobierz_aktywne_polaczenie", "pobierz_aktywny_wezel"]:
            if hasattr(wezel, method_name):
                try:
                    res = self._wyciagnij_wezel_cel(getattr(wezel, method_name)(), graf)
                    if res:
                        return res
                except TypeError:
                    pass

        return None

    def rysuj_infrastrukture(self, graf: MenedzerGrafu) -> None:
        """Rysuje tory, zwrotnice, perony i semafory."""
        rozmiar = self.skaler.rozmiar_kafelka_px
        self.powierzchnia_alfa.fill((0, 0, 0, 0))

        # 1. Stacje (tło)
        for stacja in graf.stacje.values():
            for id_toru in stacja.id_torow:
                wezel = graf.wezly.get(id_toru)
                if wezel:
                    x_px = wezel.x * rozmiar
                    y_px = wezel.y * rozmiar
                    x_r, y_r = self.swiat_na_ekran(float(x_px), float(y_px))
                    rozmiar_r = max(1, int(round(rozmiar * self.zoom)))
                    py.draw.rect(self.powierzchnia_alfa, KOLORY["STACJA"], (int(x_r), int(y_r), rozmiar_r, rozmiar_r))
        self.ekran.blit(self.powierzchnia_alfa, (0, 0))

        # 2. Tory i Zwrotnice
        for wezel in graf.wezly.values():
            x_swiat, y_swiat = self.skaler.siatka_na_ekran(wezel.x, wezel.y)
            x_srodek, y_srodek = self.swiat_na_ekran(x_swiat, y_swiat)
            kolor_wesela = (180, 180, 180)
            promien = max(2, int(round(4 * self.zoom)))

            if isinstance(wezel, WezelZwrotnicy):
                # Odczytanie aktualnego stanu zwrotnicy z pola self.pozycja
                stan = getattr(wezel, "pozycja", getattr(wezel, "zwrot", getattr(wezel, "stan", Zwrot.PLUS)))
                stan_str = str(stan.name if hasattr(stan, "name") else stan).upper()
                czy_plus_aktywny = "MINUS" not in stan_str
                kolor_wesela = (200, 100, 200)
                promien = max(3, int(round(6 * self.zoom)))

                # --- 2A. Połączenia w stanie PLUS ---
                polaczenia_plus = getattr(wezel, "polaczenia_plus", {})
                for p in polaczenia_plus.values():
                    wezel_cel = self._wyciagnij_wezel_cel(p, graf)
                    if wezel_cel:
                        x_cel_w, y_cel_w = self.skaler.siatka_na_ekran(wezel_cel.x, wezel_cel.y)
                        x_cel, y_cel = self.swiat_na_ekran(x_cel_w, y_cel_w)
                        self._rysuj_strzalke(
                            start=(x_srodek, y_srodek),
                            cel=(x_cel, y_cel),
                            kolor=KOLORY["TOR_AKTYWNY"] if czy_plus_aktywny else KOLORY["TOR_NIEAKTYWNY"],
                            rozmiar_grotu=max(4, int(round((10 if czy_plus_aktywny else 6) * self.zoom))),
                            grubosc=max(1, int(round((3 if czy_plus_aktywny else 1) * self.zoom)))
                        )

                # --- 2B. Połączenia w stanie MINUS ---
                polaczenia_minus = getattr(wezel, "polaczenia_minus", {})
                for p in polaczenia_minus.values():
                    wezel_cel = self._wyciagnij_wezel_cel(p, graf)
                    if wezel_cel:
                        x_cel_w, y_cel_w = self.skaler.siatka_na_ekran(wezel_cel.x, wezel_cel.y)
                        x_cel, y_cel = self.swiat_na_ekran(x_cel_w, y_cel_w)
                        czy_aktywny = not czy_plus_aktywny
                        self._rysuj_strzalke(
                            start=(x_srodek, y_srodek),
                            cel=(x_cel, y_cel),
                            kolor=KOLORY["TOR_AKTYWNY"] if czy_aktywny else KOLORY["TOR_NIEAKTYWNY"],
                            rozmiar_grotu=max(4, int(round((10 if czy_aktywny else 6) * self.zoom))),
                            grubosc=max(1, int(round((3 if czy_aktywny else 1) * self.zoom)))
                        )

                # Wyróżnienie środka zwrotnicy fioletowym pierścieniem
                py.draw.circle(self.ekran, (200, 100, 200), (int(x_srodek), int(y_srodek)), max(4, int(round(6 * self.zoom))), max(1, int(round(2 * self.zoom))))
                if getattr(wezel, "stan_awaryjny", False):
                    py.draw.circle(self.ekran, (255, 60, 60), (int(x_srodek), int(y_srodek)), max(6, int(round(10 * self.zoom))), max(1, int(round(2 * self.zoom))))

            else:
                # --- 2C. Zwykły tor ---
                polaczenia = getattr(wezel, "polaczenia", {})
                kolekcja = polaczenia.values() if isinstance(polaczenia, dict) else (
                    polaczenia if isinstance(polaczenia, (list, tuple, set)) else []
                )

                for p in kolekcja:
                    wezel_cel = self._wyciagnij_wezel_cel(p, graf)
                    if wezel_cel:
                        x_cel_w, y_cel_w = self.skaler.siatka_na_ekran(wezel_cel.x, wezel_cel.y)
                        x_cel, y_cel = self.swiat_na_ekran(x_cel_w, y_cel_w)
                        self._rysuj_linie(
                            start=(x_srodek, y_srodek),
                            cel=(x_cel, y_cel),
                            kolor=KOLORY["TOR"],
                            grubosc=max(1, int(round(2 * self.zoom)))
                        )

            py.draw.circle(self.ekran, kolor_wesela, (int(x_srodek), int(y_srodek)), promien)
            py.draw.circle(self.ekran, (15, 15, 15), (int(x_srodek), int(y_srodek)), promien, 1)

            # Debugowe etykiety ID
            if config.DEBUG_MODE:
                id_txt = getattr(wezel, "id_wezel", getattr(wezel, "id", ""))
                tekst = self.czcionka.render(str(id_txt), True, KOLORY["TEKST"])
                self.ekran.blit(tekst, (x_srodek - 10, y_srodek - 15))

    def rysuj_semafory(self, graf: MenedzerGrafu) -> None:
        """Rysuje semafory jako warstwę nad pociągami."""
        for semafor in graf.semafory.values():
            pozycja = self._pozycja_semafora_na_ekranie(graf, semafor)
            if pozycja:
                kolor = KOLORY.get(semafor.sygnal, KOLORY["TEKST"])
                promien = max(4, int(round(6 * self.zoom)))
                x_sem, y_sem = pozycja
                py.draw.circle(self.ekran, kolor, (int(x_sem), int(y_sem)), promien)
                py.draw.circle(self.ekran, (0, 0, 0), (int(x_sem), int(y_sem)), promien, max(1, int(round(self.zoom))))
                self._rysuj_wskaznik_kierunku((x_sem, y_sem), kierunek_przeciwny(semafor.kierunek_sem), KOLORY["KIERUNEK"])

    def rysuj_pociagi(self, menedzer_pociagow: MenedzerPociagow) -> None:
        """Rysuje pociągi na makiecie."""
        rozmiar = self.skaler.rozmiar_kafelka_px

        for pociag in menedzer_pociagow.pociagi.values():
            if not pociag.id_zajetych_kafelkow:
                continue

            for i, id_kafelka in enumerate(pociag.id_zajetych_kafelkow):
                wezel = menedzer_pociagow.graf.wezly.get(id_kafelka)
                if wezel:
                    x_w, y_w = self.skaler.siatka_na_ekran(wezel.x, wezel.y)
                    x, y = self.swiat_na_ekran(x_w, y_w)

                    jest_poczatkiem = (i == len(pociag.id_zajetych_kafelkow) - 1)
                    kolor = KOLORY["POCIAG"] if jest_poczatkiem else (30, 100, 200)

                    szer, wys = max(4, int(round(rozmiar * 0.6 * self.zoom))), max(4, int(round(rozmiar * 0.6 * self.zoom)))
                    prostokat = py.Rect(0, 0, szer, wys)
                    prostokat.center = (x, y)

                    py.draw.rect(self.ekran, kolor, prostokat)
                    py.draw.rect(self.ekran, (0, 0, 0), prostokat, max(1, int(round(2 * self.zoom))))

                    if jest_poczatkiem:
                        tekst = self.czcionka_duza.render(pociag.id_pociagu, True, KOLORY["TEKST"])
                        self.ekran.blit(tekst, (x - 12, y - 8))

    def renderuj_klatke(self, graf: MenedzerGrafu, menedzer_pociagow: MenedzerPociagow, czas_symulacji: str, edytor=None) -> None:
        """Funkcja wywoływana co klatkę w pętli."""
        self.ekran.fill(KOLORY["TLO"])

        szerokosc = self.ekran.get_width()
        wysokosc = self.ekran.get_height()

        self.powierzchnia_alfa = py.Surface((szerokosc, wysokosc), py.SRCALPHA)

        self.rysuj_siatke(szerokosc, wysokosc)
        self.rysuj_infrastrukture(graf)
        self.rysuj_pociagi(menedzer_pociagow)
        self.rysuj_semafory(graf)

        if edytor is not None:
            edytor.rysuj_nakladke(
                self.ekran,
                graf,
                self.skaler,
                self.czcionka,
                self.czcionka_duza,
                zoom=self.zoom,
                swiat_na_ekran=self.swiat_na_ekran,
            )

        tekst_czasu = self.czcionka_duza.render(f"Czas: {czas_symulacji}", True, KOLORY["TEKST"])
        self.ekran.blit(tekst_czasu, (10, 10))

        py.display.flip()

    def zamknij(self) -> None:
        py.quit()

    def _rysuj_strzalke(self, start, cel, kolor, rozmiar_grotu=8, margines=12, grubosc=2):
        """Rysuje linię ze strzałką od punktu start do cel."""
        x1, y1 = start
        x2, y2 = cel

        dx = x2 - x1
        dy = y2 - y1
        dlugosc = math.hypot(dx, dy)

        if dlugosc == 0:
            return

        if dlugosc <= margines:
            margines = dlugosc * 0.3

        udx = dx / dlugosc
        udy = dy / dlugosc

        koniec_x = x2 - udx * margines
        koniec_y = y2 - udy * margines

        # 1. Główna linia toru
        py.draw.line(self.ekran, kolor, (int(x1), int(y1)), (int(koniec_x), int(koniec_y)), grubosc)

        # 2. Grot strzałki
        kat = math.atan2(dy, dx)
        kat_skrzydla = math.radians(25)

        p1 = (
            int(koniec_x - rozmiar_grotu * math.cos(kat - kat_skrzydla)),
            int(koniec_y - rozmiar_grotu * math.sin(kat - kat_skrzydla))
        )
        p2 = (
            int(koniec_x - rozmiar_grotu * math.cos(kat + kat_skrzydla)),
            int(koniec_y - rozmiar_grotu * math.sin(kat + kat_skrzydla))
        )
        p_koniec = (int(koniec_x), int(koniec_y))

        py.draw.polygon(self.ekran, kolor, [p_koniec, p1, p2])

    def _rysuj_linie(self, start, cel, kolor, grubosc=2):
        """Rysuje zwykłe połączenie bez grotu strzałki."""
        x1, y1 = start
        x2, y2 = cel
        py.draw.line(self.ekran, kolor, (int(x1), int(y1)), (int(x2), int(y2)), grubosc)