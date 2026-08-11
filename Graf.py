# Menedżer grafu szlaku

from typing import Any, Dict, Optional, Tuple
import config
from Wezly import WezelGrafu, WezelZwrotnicy, WezelSemafora, ObszarStacji, Kierunek, Sygnal, kierunek_przeciwny

class MenedzerGrafu:
    """
    Klasa odpowiedzialna za zarządzanie strukturą grafu skierowanego makiety. Odpowiada za wczytywanie węzłów, zarządzanie zwrotnicami i semaforami oraz przeszukiwanie drogi w grafie (BFS).
    """
    def __init__(self):
        self.wezly: Dict[str, WezelGrafu] = {}
        self.zwrotnice: Dict[str, WezelZwrotnicy] = {}
        self.semafory: Dict[str, WezelSemafora] = {} # klucz: id semafora
        self.semafory_dla_wezlow: Dict[Tuple[str, Kierunek], WezelSemafora] = {} # klucz: (id_toru, kierunek)
        self.stacje: Dict[str, ObszarStacji] = {}

    def dodaj_wezel(self, wezel: WezelGrafu) -> None:
        """Dodaje węzeł do grafu (tor lub zwrotnicę)."""
        self.wezly[wezel.id_wezel] = wezel
        if isinstance(wezel, WezelZwrotnicy):
            self.zwrotnice[wezel.id_wezel] = wezel

    def dodaj_semafor(self, semafor: WezelSemafora) -> None:
        """Dodaje semafor do grafu i indeksuje go po kafelku oraz kierunku."""
        self.semafory[semafor.id_semafora] = semafor
        klucz = (semafor.id_toru, semafor.kierunek_sem)
        self.semafory_dla_wezlow[klucz] = semafor

    def dodaj_stacje(self, stacja: ObszarStacji) -> None:
        """Dodaje stację do grafu."""
        self.stacje[stacja.id_stacji] = stacja

    @staticmethod
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
        return mapa[kierunek]

    def _czy_kierunek_semafora_zgodny(self, kierunek_pociagu: Kierunek, kierunek_semafora: Kierunek) -> bool:
        if kierunek_pociagu == kierunek_semafora:
            return True

        if kierunek_przeciwny(kierunek_pociagu) == kierunek_semafora:
            return False

        wektor_pociagu = self._wektor_kierunku(kierunek_pociagu)
        wektor_semafora = self._wektor_kierunku(kierunek_semafora)
        iloczyn_skalarny = wektor_pociagu[0] * wektor_semafora[0] + wektor_pociagu[1] * wektor_semafora[1]

        # Dopuszczamy zblizone kierunki (np. skos vs poziom), ale odrzucamy przeciwne.
        return iloczyn_skalarny > 0.0

    def znajdz_semafor_dla_kierunku(self, id_kafelka: str, kierunek: Kierunek) -> Optional[WezelSemafora]:
        """Znajduje semafor sterujacy ruchem dla podanego toru i kierunku jazdy."""
        semafor = self.semafory_dla_wezlow.get((id_kafelka, kierunek))
        if semafor:
            return semafor

        semafory_na_torze = [
            semafor_dla_toru
            for (id_toru, _), semafor_dla_toru in self.semafory_dla_wezlow.items()
            if id_toru == id_kafelka
        ]
        for semafor_dla_toru in semafory_na_torze:
            if self._czy_kierunek_semafora_zgodny(kierunek, semafor_dla_toru.kierunek_sem):
                return semafor_dla_toru

        return None

    def znajdz_wezel_po_wspolrzednych(self, x: int, y: int) -> Optional[WezelGrafu]:
        """Zwraca węzeł znajdujący się na podanych współrzędnych siatki."""
        for wezel in self.wezly.values():
            if wezel.x == x and wezel.y == y:
                return wezel
        return None

    def usun_wezel(self, id_wezla: str) -> bool:
        """Usuwa węzeł i wszystkie połączenia prowadzące do niego."""
        wezel = self.wezly.pop(id_wezla, None)
        if not wezel:
            return False

        self.zwrotnice.pop(id_wezla, None)

        for inny_wezel in self.wezly.values():
            if hasattr(inny_wezel, "polaczenia") and isinstance(inny_wezel.polaczenia, dict):
                inny_wezel.polaczenia = {
                    kierunek: wartosc
                    for kierunek, wartosc in inny_wezel.polaczenia.items()
                    if wartosc[0] != id_wezla
                }

            if isinstance(inny_wezel, WezelZwrotnicy):
                inny_wezel.polaczenia_plus = {
                    kierunek: wartosc
                    for kierunek, wartosc in inny_wezel.polaczenia_plus.items()
                    if wartosc[0] != id_wezla
                }
                inny_wezel.polaczenia_minus = {
                    kierunek: wartosc
                    for kierunek, wartosc in inny_wezel.polaczenia_minus.items()
                    if wartosc[0] != id_wezla
                }
                if inny_wezel.polaczenie_glowne and inny_wezel.polaczenie_glowne[0] == id_wezla:
                    inny_wezel.polaczenie_glowne = None
                if inny_wezel.polaczenie_zwrotne_plus and inny_wezel.polaczenie_zwrotne_plus[0] == id_wezla:
                    inny_wezel.polaczenie_zwrotne_plus = None
                if inny_wezel.polaczenie_zwrotne_minus and inny_wezel.polaczenie_zwrotne_minus[0] == id_wezla:
                    inny_wezel.polaczenie_zwrotne_minus = None

        for klucz, semafor in list(self.semafory_dla_wezlow.items()):
            if semafor.id_toru == id_wezla:
                self.semafory_dla_wezlow.pop(klucz, None)

        for id_semafora, semafor in list(self.semafory.items()):
            if semafor.id_toru == id_wezla:
                self.semafory.pop(id_semafora, None)

        for id_stacji, stacja in list(self.stacje.items()):
            if id_wezla in stacja.id_torow:
                stacja.id_torow = [id_toru for id_toru in stacja.id_torow if id_toru != id_wezla]
                if not stacja.id_torow:
                    self.stacje.pop(id_stacji, None)

        return True

    def eksportuj_do_slownika(self) -> Dict[str, Any]:
        """Eksportuje bieżący graf do struktury zgodnej z plikiem konfiguracyjnym."""
        wezly = []
        for wezel in self.wezly.values():
            if isinstance(wezel, WezelZwrotnicy):
                wezly.append(
                    {
                        "id": wezel.id_wezel,
                        "x": wezel.x,
                        "y": wezel.y,
                        "polaczenia_plus": {
                            kierunek.name: {
                                "id_cel": id_cel,
                                "kierunek_wejscia_cel": kierunek_cel.name,
                            }
                            for kierunek, (id_cel, kierunek_cel) in wezel.polaczenia_plus.items()
                        },
                        "polaczenia_minus": {
                            kierunek.name: {
                                "id_cel": id_cel,
                                "kierunek_wejscia_cel": kierunek_cel.name,
                            }
                            for kierunek, (id_cel, kierunek_cel) in wezel.polaczenia_minus.items()
                        },
                    }
                )
            else:
                wezly.append(
                    {
                        "id": wezel.id_wezel,
                        "x": wezel.x,
                        "y": wezel.y,
                        "polaczenia": {
                            kierunek.name: {
                                "id_cel": id_cel,
                                "kierunek_wejscia_cel": kierunek_cel.name,
                            }
                            for kierunek, (id_cel, kierunek_cel) in wezel.polaczenia.items()
                        },
                    }
                )

        return {
            "wezly": wezly,
            "zwrotnice": [
                {
                    "id": zwrotnica.id_wezel,
                    "x": zwrotnica.x,
                    "y": zwrotnica.y,
                    "kierunek_glowny": zwrotnica.kierunek_glowny.name if zwrotnica.kierunek_glowny else None,
                    "kierunek_zwrotny_plus": zwrotnica.kierunek_zwrotny_plus.name if zwrotnica.kierunek_zwrotny_plus else None,
                    "kierunek_zwrotny_minus": zwrotnica.kierunek_zwrotny_minus.name if zwrotnica.kierunek_zwrotny_minus else None,
                    "polaczenie_glowne": {
                        "id_cel": zwrotnica.polaczenie_glowne[0],
                        "kierunek_wejscia_cel": zwrotnica.polaczenie_glowne[1].name,
                    }
                    if zwrotnica.polaczenie_glowne
                    else None,
                    "polaczenie_zwrotne_plus": {
                        "id_cel": zwrotnica.polaczenie_zwrotne_plus[0],
                        "kierunek_wejscia_cel": zwrotnica.polaczenie_zwrotne_plus[1].name,
                    }
                    if zwrotnica.polaczenie_zwrotne_plus
                    else None,
                    "polaczenie_zwrotne_minus": {
                        "id_cel": zwrotnica.polaczenie_zwrotne_minus[0],
                        "kierunek_wejscia_cel": zwrotnica.polaczenie_zwrotne_minus[1].name,
                    }
                    if zwrotnica.polaczenie_zwrotne_minus
                    else None,
                    # Stan awaryjny jest stanem runtime i nie powinien startować jako trwale aktywny.
                    "stan_awaryjny": False,
                    "polaczenia_plus": {
                        kierunek.name: {
                            "id_cel": id_cel,
                            "kierunek_wejscia_cel": kierunek_cel.name,
                        }
                        for kierunek, (id_cel, kierunek_cel) in zwrotnica.polaczenia_plus.items()
                    },
                    "polaczenia_minus": {
                        kierunek.name: {
                            "id_cel": id_cel,
                            "kierunek_wejscia_cel": kierunek_cel.name,
                        }
                        for kierunek, (id_cel, kierunek_cel) in zwrotnica.polaczenia_minus.items()
                    },
                }
                for zwrotnica in self.zwrotnice.values()
            ],
            "semafory": [
                {
                    "id": semafor.id_semafora,
                    "id_toru": semafor.id_toru,
                    "kierunek_semafora": semafor.kierunek_sem.name,
                    "domyslny_stan": semafor.sygnal.name,
                }
                for semafor in self.semafory.values()
            ],
            "stacje": [
                {
                    "id": stacja.id_stacji,
                    "nazwa": stacja.nazwa_stacji,
                    "id_torow": stacja.id_torow,
                }
                for stacja in self.stacje.values()
            ],
        }

    def zaladuj_z_slownika(self, infrastruktura: Dict) -> None:
        """Ładuje węzły, zwrotnice, semafory i stacje z podanego słownika wczytanego z JSON."""

        # Wczytywanie zwykłych torów
        for wezel_dane in infrastruktura.get("wezly", []):
            wezel = WezelGrafu(wezel_dane["id"], wezel_dane["x"], wezel_dane["y"])
            for kierunek_str, polaczenie in wezel_dane.get("polaczenia", {}).items():
                kierunek = Kierunek[kierunek_str]
                kierunek_cel = Kierunek[polaczenie["kierunek_wejscia_cel"]]
                wezel.dodaj_polaczenie(kierunek, polaczenie["id_cel"], kierunek_cel)
            self.dodaj_wezel(wezel)

        # Wczytywanie zwrotnic
        for zwrotnica_dane in infrastruktura.get("zwrotnice", []):
            zwrotnica = WezelZwrotnicy(zwrotnica_dane["id"], zwrotnica_dane["x"], zwrotnica_dane["y"])
            # polaczenia dla pozycji PLUS
            for kierunek_str, polaczenie in zwrotnica_dane.get("polaczenia_plus", {}).items():
                kierunek = Kierunek[kierunek_str]
                kierunek_cel = Kierunek[polaczenie["kierunek_wejscia_cel"]]
                zwrotnica.polaczenia_plus[kierunek] = (polaczenie["id_cel"], kierunek_cel)
            # polaczenia dla pozycji MINUS
            for kierunek_str, polaczenie in zwrotnica_dane.get("polaczenia_minus", {}).items():
                kierunek = Kierunek[kierunek_str]
                kierunek_cel = Kierunek[polaczenie["kierunek_wejscia_cel"]]
                zwrotnica.polaczenia_minus[kierunek] = (polaczenie["id_cel"], kierunek_cel)

            kierunek_glowny = zwrotnica_dane.get("kierunek_glowny")
            kierunek_zwrotny_plus = zwrotnica_dane.get("kierunek_zwrotny_plus")
            kierunek_zwrotny_minus = zwrotnica_dane.get("kierunek_zwrotny_minus")
            polaczenie_glowne = zwrotnica_dane.get("polaczenie_glowne")
            polaczenie_zwrotne_plus = zwrotnica_dane.get("polaczenie_zwrotne_plus")
            polaczenie_zwrotne_minus = zwrotnica_dane.get("polaczenie_zwrotne_minus")

            zwrotnica.ustaw_geometrie(
                Kierunek[kierunek_glowny] if kierunek_glowny else None,
                Kierunek[kierunek_zwrotny_plus] if kierunek_zwrotny_plus else None,
                Kierunek[kierunek_zwrotny_minus] if kierunek_zwrotny_minus else None,
                (polaczenie_glowne["id_cel"], Kierunek[polaczenie_glowne["kierunek_wejscia_cel"]]) if polaczenie_glowne else None,
                (polaczenie_zwrotne_plus["id_cel"], Kierunek[polaczenie_zwrotne_plus["kierunek_wejscia_cel"]]) if polaczenie_zwrotne_plus else None,
                (polaczenie_zwrotne_minus["id_cel"], Kierunek[polaczenie_zwrotne_minus["kierunek_wejscia_cel"]]) if polaczenie_zwrotne_minus else None,
            )
            zwrotnica.stan_awaryjny = False
            self.dodaj_wezel(zwrotnica)

        # Wczytywanie semaforów
        for semafor_dane in infrastruktura.get("semafory", []):
            semafor = WezelSemafora(semafor_dane["id"], semafor_dane["id_toru"], Kierunek[semafor_dane["kierunek_semafora"]])
            semafor.ustaw_sygnal(Sygnal[semafor_dane.get("domyslny_stan", "CZERWONY")])
            self.dodaj_semafor(semafor)

        # Wczytywanie stacji
        for stacja_dane in infrastruktura.get("stacje", []):
            stacja = ObszarStacji(stacja_dane["id"], stacja_dane["nazwa"], stacja_dane["id_torow"])
            self.dodaj_stacje(stacja)

        if config.DEBUG_MODE:
            print(f"[DEBUG] Załadowano infrastrukturę: {len(self.wezly)} węzłów, {len(self.zwrotnice)} zwrotnic, {len(self.semafory)} semaforów, {len(self.stacje)} stacji.")

    def znajdz_wolna_przestrzen(self, id_punktu_poczatkowego: str, kierunek_nadjezdzania: Kierunek, max_liczba_krokow: int = 20) -> Tuple[int, Optional[str]]:
        """
        Algorytm BFS do obliczania ile wolnych kafelków znajduje się przed pociągiem. Poszukiwanie jest przerywane kiedy napotkamy: czerwony semafor, zajęty kafelek, koniec toru(brak połączenia w grafie) lub osiągniemy maksymalną liczbę kroków.
        Zwraca krotkę (liczba_wolnych_kafelkow, powod_zatrzymania). Jeśli nie znaleziono wolnego kafelka, zwraca (0, None).
        """
        if id_punktu_poczatkowego not in self.wezly:
            if config.DEBUG_MODE:
                print(f"[DEBUG] Punkt początkowy '{id_punktu_poczatkowego}' nie istnieje w grafie.")
            return 0, "punkt_nie_istnieje"

        liczba_wolnych_kafelkow = 0
        obecny_wezel_id = id_punktu_poczatkowego
        obecny_kierunek = kierunek_nadjezdzania

        for krok in range(max_liczba_krokow):
            obecny_wezel = self.wezly[obecny_wezel_id]

            # Sprawdzenie zajętości węzła
            if obecny_wezel.zajety:
                if config.DEBUG_MODE:
                    print(f"[DEBUG] Zajęty kafelek '{obecny_wezel_id}' napotkany po {liczba_wolnych_kafelkow} wolnych kafelkach.")
                return liczba_wolnych_kafelkow, "zajety_kafelek"

            # Sprawdzenie semafora na węźle
            semafor = self.znajdz_semafor_dla_kierunku(obecny_wezel_id, obecny_kierunek)
            if semafor and semafor.sygnal == Sygnal.CZERWONY:
                if config.DEBUG_MODE:
                    print(f"[DEBUG] Czerwony semafor '{semafor.id_semafora}' napotkany po {liczba_wolnych_kafelkow} wolnych kafelkach.")
                return liczba_wolnych_kafelkow, "czerwony_semafor"

            # Próba przejścia do następnego węzła
            nastepny = obecny_wezel.nastepny_wezel(obecny_kierunek, raportuj_awarie=False)
            if not nastepny:
                if config.DEBUG_MODE:
                    print(f"[DEBUG] Koniec toru napotkany po {liczba_wolnych_kafelkow} wolnych kafelkach.")
                return liczba_wolnych_kafelkow, "koniec_toru"

            # Aktualizacja obecnego węzła i kierunku
            obecny_wezel_id, obecny_kierunek = nastepny
            liczba_wolnych_kafelkow += 1

        if config.DEBUG_MODE:
            print(f"[DEBUG] Osiągnięto maksymalną liczbę kroków ({max_liczba_krokow}) po {liczba_wolnych_kafelkow} wolnych kafelkach.")

        return liczba_wolnych_kafelkow, "max_glebokosc_poszukiwania"

    def odczytaj_najblizszy_semafor(self, id_punktu_poczatkowego: str, kierunek_nadjezdzania: Kierunek, zasieg: int = 5) -> Optional[Sygnal]:
        """Zwraca sygnal na najblizszym semaforze przed pociagiem"""
        id_obecny_wezel = id_punktu_poczatkowego
        obecny_kierunek = kierunek_nadjezdzania

        for _ in range(zasieg):
            semafor = self.znajdz_semafor_dla_kierunku(id_obecny_wezel, obecny_kierunek)
            if semafor:
                return semafor.sygnal

            obecny_wezel = self.wezly.get(id_obecny_wezel)
            if not obecny_wezel:
                break

            nastepny = obecny_wezel.nastepny_wezel(obecny_kierunek, raportuj_awarie=False)
            if not nastepny:
                break

            id_obecny_wezel, obecny_kierunek = nastepny

        return None