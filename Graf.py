# menedżer grafu szlaku

from typing import Dict, Optional, Tuple
from Wezly import WezelGrafu, WezelZwrotnicy, WezelSemafora, ObszarStacji, Kierunek, Sygnal

global DEBUG_MODE

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

        if DEBUG_MODE:
            print(f"[DEBUG] Załadowano infrastrukturę: {len(self.wezly)} węzłów, {len(self.zwrotnice)} zwrotnic, {len(self.semafory)} semaforów, {len(self.stacje)} stacji.")

    def znajdz_wolna_przestrzen(self, id_punktu_poczatkowego: str, kierunek_nadjezdzania: Kierunek, max_liczba_krokow: int = 20) -> Tuple[int, Optional[str]]:
        """
        Algorytm BFS do obliczania ile wolnych kafelków znajduje się przed pociągiem. Poszukiwanie jest przerywane kiedy napotkamy: czerwony semafor, zajęty kafelek, koniec toru(brak połączenia w grafie) lub osiągniemy maksymalną liczbę kroków.
        Zwraca krotkę (liczba_wolnych_kafelkow, powod_zatrzymania). Jeśli nie znaleziono wolnego kafelka, zwraca (0, None).
        """
        if id_punktu_poczatkowego not in self.wezly:
            if DEBUG_MODE:
                print(f"[DEBUG] Punkt początkowy '{id_punktu_poczatkowego}' nie istnieje w grafie.")
            return 0, "punkt_nie_istnieje"

        liczba_wolnych_kafelkow = 0
        obecny_wezel_id = id_punktu_poczatkowego
        obecny_kierunek = kierunek_nadjezdzania

        for krok in range(max_liczba_krokow):
            obecny_wezel = self.wezly[obecny_wezel_id]

            # Sprawdzenie zajętości węzła
            if obecny_wezel.zajety:
                if DEBUG_MODE:
                    print(f"[DEBUG] Zajęty kafelek '{obecny_wezel_id}' napotkany po {liczba_wolnych_kafelkow} wolnych kafelkach.")
                return liczba_wolnych_kafelkow, "zajety_kafelek"

            # Sprawdzenie semafora na węźle
            semafor = self.semafory_dla_wezlow.get((obecny_wezel_id, obecny_kierunek))
            if semafor and semafor.sygnal == Sygnal.CZERWONY:
                if DEBUG_MODE:
                    print(f"[DEBUG] Czerwony semafor '{semafor.id_semafora}' napotkany po {liczba_wolnych_kafelkow} wolnych kafelkach.")
                return liczba_wolnych_kafelkow, "czerwony_semafor"

            # Próba przejścia do następnego węzła
            nastepny = obecny_wezel.nastepny_wezel(obecny_kierunek)
            if not nastepny:
                if DEBUG_MODE:
                    print(f"[DEBUG] Koniec toru napotkany po {liczba_wolnych_kafelkow} wolnych kafelkach.")
                return liczba_wolnych_kafelkow, "koniec_toru"

            # Aktualizacja obecnego węzła i kierunku
            obecny_wezel_id, obecny_kierunek = nastepny
            liczba_wolnych_kafelkow += 1

        if DEBUG_MODE:
            print(f"[DEBUG] Osiągnięto maksymalną liczbę kroków ({max_liczba_krokow}) po {liczba_wolnych_kafelkow} wolnych kafelkach.")

        return liczba_wolnych_kafelkow, "max_glebokosc_poszukiwania"
