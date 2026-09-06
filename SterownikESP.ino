#include <Arduino.h> // Wymagane dla ESP32 w Arduino IDE
#include <ArduinoJson.h> // Biblioteka do obsługi JSON (ArduinoJson v7) 
#include <map>
#include <list>
#include <vector>
#include <algorithm>
#include <math.h>
#include <sstream>
#include <string>

// Mapa sekcji ma obecnie ok. 20 KB. Bufor musi zawierać całą ramkę JSON,
// ponieważ odbiór korzysta z readStringUntil('\n').
#define ROZMIAR_BUFORA_WEJSCIOWEGO 32768

enum class Sygnal : uint8_t { CZERWONY, ZOLTY, ZIELONY, SZ };
enum class Zwrot : bool { PLUS, MINUS };
enum class TypPociagu : uint8_t { TOWAROWY, OSOBOWY, POSPIESZNY, TECHNICZNY };
enum class Kierunek : uint8_t {
  POLNOC, POLUDNIE, WSCHOD, ZACHOD,
  POLNOC_WSCHOD, POLNOC_ZACHOD, POLUDNIE_WSCHOD, POLUDNIE_ZACHOD
};

struct OknoCzasowe {
  uint16_t id_pociagu; // ID pociągu, którego dotyczy okno czasowe
  uint32_t czas_start; // w sekundach od początku symulacji
  uint32_t czas_koniec; // w sekundach od początku symulacji
  uint16_t sekcja_zrodlowa;
  uint16_t sekcja_docelowa;
};

struct UstawienieZwrotnicy {
  uint16_t id_zwrotnicy;
  Zwrot wymagany_zwrot;
};

struct PolaczenieSekcji {
  uint16_t id_sekcji_docelowej;
  uint16_t id_semafora;
  Kierunek kierunek;
  uint16_t liczba_kafelkow_zwrotnic;
  std::vector<UstawienieZwrotnicy> wymagane_zwrotnice;
};

struct StacjaInfo {
  String id;
  String nazwa;
  uint16_t dlugosc_peronu; // dlugosc peronu w kafelkach
};

struct Sekcja {
  uint16_t id;
  bool zajeta;
  uint16_t pociag_id;
  std::vector<PolaczenieSekcji> polaczenia;
  uint8_t dlugosc;
  float pozycja_x;
  float pozycja_y;
  StacjaInfo stacja; // dane stacji/peronu na tej sekcji
  std::vector<OknoCzasowe> rezerwacje; // lista rezerwacji czasowych dla tej sekcji
};

struct PlanowanaKrawedz {
  uint16_t zrodlo;
  uint16_t cel;
  uint32_t czas_start;
  uint32_t czas_koniec_przejazdu;
  uint32_t czas_koniec_sekcji;
  const PolaczenieSekcji* polaczenie;
};

struct Zwrotnica {
  uint16_t id;
  Zwrot pozycja;
  bool blokada;
  bool awaria;
  std::vector<OknoCzasowe> rezerwacje; // lista rezerwacji czasowych dla tej zwrotnicy
};

struct Semafor {
  uint16_t id;
  Sygnal sygnal;
};

std::vector<String> Stacje;

struct Rozklad {
  String stacja_docelowa;
  uint32_t czas_przyjazdu; // w czasie symulacji np. 10:10:00 = 36600 sekund
  uint32_t czas_odjazdu; // w czasie symulacji
  uint16_t czas_postoju; // w sekundach
};

struct Pociag {
  uint16_t id;
  float predkosc_docelowa_pxs;
  float predkosc_aktualna_pxs;
  float predkosc_max_pxs;
  float predkosc_kmh;
  Kierunek kierunek; // 0 = północ, 1 = południe, 2 = wschód, 3 = zachód
  TypPociagu typ; // 0 = towarowy, 1 = osobowy, 2 = pospieszny, 3 = techniczny cyfry jednocześnie określają priorytety pociągów (0 = najniższy priorytet, 3 = najwyższy priorytet)
  uint16_t czolo; // ID sekcji, w której znajduje się czoło
  uint16_t ogon; // ID sekcji, w której znajduje się ogon
  uint16_t dlugosc; // Dlugosc pociagu w kafelkach
  uint16_t czas_postoju; // w sekundach
  bool przekroczenie_czerwonego; // czy pociąg przekroczył czerwone światło
  bool zatrzymany_na_czerwonym;
  bool na_postoju_stacyjnym;
  bool awaria;
  bool rozklad_zaladowany;
  uint16_t indeks_nastepnego_przystanku;
  uint16_t sekcja_z_terminem_wyjazdu;
  uint32_t termin_wyjazdu_z_sekcji;
  std::vector<Rozklad> rozklad;
};

std::map<uint16_t, Sekcja> mapa_sekcji;
std::map<uint16_t, Zwrotnica> mapa_zwrotnic;
std::map<uint16_t, Semafor> mapa_semaforow;
std::map<uint16_t, Pociag> mapa_pociagow;

uint32_t aktualny_czas_symulacji = 0; // w sekundach od początku symulacji przesunięte o czas startu symulacji
bool awaria = false; // czy ESTOP został włączony
bool DEBUG = true; // czy włączyć debugowanie

float skala_w_metrach = 100.0; // domyślna skala w metrach (1 kafelek = 100 metrów)
uint8_t rozmiar_kafelka_w_px = 48; // domyślny rozmiar kafelka w pikselach
float wspolczynnik_szybkosci_symulacji = 1.0f; // domyślny współczynnik szybkości symulacji (1x = normalna prędkość)
uint32_t ostatnia_aktualizacja_czasu_ms = 0;
float reszta_czasu_symulacji_ms = 0.0f;
uint16_t oczekiwana_liczba_pociagow = 0;
const uint32_t ZAPAS_REZERWACJI_S = 300;
const uint32_t HORYZONT_PLANOWANIA_S = 3600;
const uint8_t MAKS_KRAWEDZI_TRASY = 128;

std::vector<String> rozdzielTekst(const String& str, char separator) {
  std::vector<String> tokeny;
  int start = 0;
  int end = str.indexOf(separator);
  while (end != -1) {
    tokeny.push_back(str.substring(start, end));
    start = end + 1;
    end = str.indexOf(separator, start);
  }
  tokeny.push_back(str.substring(start));
  return tokeny;
}

void obsluzSygnalEVT(String wiadomosc);
void obsluzMapeSekcji(String jsonStr);
void obsluzOdpowiedzDAT(String wiadomosc);
void przetworzLinie(String linia);
uint16_t modyfikujId(const char* str);
void przestawZwrotnice(String id, String pozycja);
void ustawSygnal(String id, String sygnal);
void poprawZwrotnice();
void wjazdDoSekcji(uint16_t pociag_id, uint16_t sekcja_id, uint32_t czas);
void pytaj_o_pociag(uint16_t pociag_id);
void pytaj_o_semafor(uint16_t semafor_id);
void pytaj_o_zwrotnice(uint16_t zwrotnica_id);
void pytaj_o_sekcje(uint16_t sekcja_id);
void pytaj_o_czas_symulacji();
void pytaj_o_rozklad_pociagu(uint16_t pociag_id);
void aktualizujCzasWewnetrzny();
bool synchronizujCzasZRamy(const String& ramka);
void przeliczSterowanieSIPP();
void sprawdzPrzekroczoneRezerwacje();
void zatrzymajRuchWokolSekcji(uint16_t id_sekcji);
void ustawSygnaIStanZwrotnicSIPP();
uint32_t obliczCzasPrzejazdu(uint16_t pociag_id, uint16_t sekcja_id, uint16_t sekcja_docelowa_id);
Sygnal sygnalDlaZajetosci(uint16_t sekcja_zrodlowa, uint16_t sekcja_docelowa);
bool pociagMaRezerwacjePrzejazdu(uint16_t id_pociagu, uint16_t sekcja_zrodlowa, uint16_t sekcja_docelowa);
bool zwrotnicaJestWStrefieInnegoPociagu(uint16_t id_zwrotnicy, uint16_t id_pociagu);
bool wszystkieRozkladyZaladowane();
uint32_t najblizszyWolnyCzasZwrotnicy(uint16_t id_zwrotnicy, uint16_t id_pociagu, uint32_t czas_start, uint32_t czas_trwania);
float prawostronnyWynikSekcji(const Sekcja& sekcja, Kierunek kierunek);
bool sekcjaMaRezerwacjeInnegoPociagu(const Sekcja& sekcja, uint16_t id_pociagu);
Kierunek kierunekZTekstu(const String& kierunek);
uint32_t konwertujCzasNaSekundy(const String& czasStr) {
  if (czasStr.length() == 0 || czasStr == "-") return 0;
  int godziny = 0, minuty = 0, sekundy = 0;
  if (sscanf(czasStr.c_str(), "%d:%d:%d", &godziny, &minuty, &sekundy) == 3) {
    return godziny * 3600 + minuty * 60 + sekundy;
  }
  if (sscanf(czasStr.c_str(), "%d-%d-%d", &godziny, &minuty, &sekundy) == 3) {
    return godziny * 3600 + minuty * 60 + sekundy;
  }
  if (sscanf(czasStr.c_str(), "%d:%d", &godziny, &minuty) == 2) {
    return godziny * 3600 + minuty * 60;
  }
  if (sscanf(czasStr.c_str(), "%d-%d", &godziny, &minuty) == 2) {
    return godziny * 3600 + minuty * 60;
  }
  return 0;
}

Kierunek kierunekZTekstu(const String& kierunek) {
  if (kierunek == "POLNOC") return Kierunek::POLNOC;
  if (kierunek == "POLUDNIE") return Kierunek::POLUDNIE;
  if (kierunek == "WSCHOD") return Kierunek::WSCHOD;
  if (kierunek == "POLNOC_WSCHOD") return Kierunek::POLNOC_WSCHOD;
  if (kierunek == "POLNOC_ZACHOD") return Kierunek::POLNOC_ZACHOD;
  if (kierunek == "POLUDNIE_WSCHOD") return Kierunek::POLUDNIE_WSCHOD;
  if (kierunek == "POLUDNIE_ZACHOD") return Kierunek::POLUDNIE_ZACHOD;
  return Kierunek::ZACHOD;
}

void aktualizujCzasWewnetrzny() {
  uint32_t teraz_ms = millis();
  if (ostatnia_aktualizacja_czasu_ms == 0) {
    ostatnia_aktualizacja_czasu_ms = teraz_ms;
    return;
  }

  uint32_t delta_ms = teraz_ms - ostatnia_aktualizacja_czasu_ms;
  ostatnia_aktualizacja_czasu_ms = teraz_ms;
  reszta_czasu_symulacji_ms += delta_ms * wspolczynnik_szybkosci_symulacji;

  uint32_t pelne_sekundy = (uint32_t)(reszta_czasu_symulacji_ms / 1000.0f);
  if (pelne_sekundy > 0) {
    aktualny_czas_symulacji += pelne_sekundy;
    reszta_czasu_symulacji_ms -= pelne_sekundy * 1000.0f;
  }
}

bool synchronizujCzasZRamy(const String& ramka) {
  int pozycja_czasu = ramka.length() - 8;
  if (pozycja_czasu < 0) return false;

  String czas = ramka.substring(pozycja_czasu);
  if (czas.charAt(2) != ':' || czas.charAt(5) != ':') return false;

  int godziny = czas.substring(0, 2).toInt();
  int minuty = czas.substring(3, 5).toInt();
  int sekundy = czas.substring(6, 8).toInt();
  if (godziny > 23 || minuty > 59 || sekundy > 59) return false;

  aktualny_czas_symulacji = godziny * 3600UL + minuty * 60UL + sekundy;
  ostatnia_aktualizacja_czasu_ms = millis();
  reszta_czasu_symulacji_ms = 0.0f;
  return true;
}

char* odwrotnieModyfikujId(uint16_t id, std::string prefix = "") {
  static char buffer[16];
  if (id < 10) {
    snprintf(buffer, sizeof(buffer), "%s0%u", prefix.c_str(), id);
  } else {
    snprintf(buffer, sizeof(buffer), "%s%u", prefix.c_str(), id);
  }
  return buffer;
}


void setup() {
  // Zwiększenie bufora portu szeregowego
  Serial.setRxBufferSize(ROZMIAR_BUFORA_WEJSCIOWEGO);
  Serial.begin(115200);

  // Krótkie opóźnienie na ustabilizowanie połączenia
  delay(1000);

  // Wysłanie zapytania o stan i mapę sekcji do Pythona po starcie
  Serial.println("SNP");
  Serial.println("PING");
  Serial.println("UST");
}

void loop() {
  aktualizujCzasWewnetrzny();
  sprawdzPrzekroczoneRezerwacje();

  // Nieblokujący odczyt linii ze strumienia
  if (Serial.available() > 0) {
    String linia = Serial.readStringUntil('\n');
    linia.trim(); // Usuwamy \r i ewentualne spakowane spacje

    if (linia.length() > 0) {
      przetworzLinie(linia);
    }
  }
}

/**
 * Glowna funkcja parsowania odebranej ramki tekstowej z Pythona
 */
void przetworzLinie(String linia) {
  aktualizujCzasWewnetrzny();

  int pierwszyDwukropek = linia.indexOf(':');
  
  if (pierwszyDwukropek == -1) {
    // Ramka bez dwukropka (np. sam tekst)
    return;
  }

  String typ = linia.substring(0, pierwszyDwukropek);
  String tresc = linia.substring(pierwszyDwukropek + 1);

  // Tylko EVT i odpowiedz PNG niosa aktualny czas. Ramka ROZ takze ma
  // godziny, lecz sa to planowe czasy przystankow, a nie czas biezacy.
  if (typ == "EVT" || (typ == "OK" && tresc.startsWith("PNG:"))) {
    synchronizujCzasZRamy(linia);
  }

  // 1. ZDARZENIA ASYNCHRONICZNE (EVT)
  if (typ == "EVT") {
    if (tresc.startsWith("MAPA_SEKCJI:")) {
      String jsonMap = tresc.substring(12); // Odtcinamy prefiks "MAPA_SEKCJI:"
      obsluzMapeSekcji(jsonMap);
    } 
    else if (tresc.startsWith("SEK_WJA:")) {
      // Format: EVT:SEK_WJA:pociag_id:sekcja_id:kierunek:czas
      // jeśli pociąg nie istnieje w mapie_pociagow, to go rejestrujemy
      std::vector<String> tokeny = rozdzielTekst(tresc, ':');
      if (tokeny.size() >= 4) {
        uint16_t pociag_id = modyfikujId(tokeny[1].c_str());
        uint16_t sekcja_id = modyfikujId(tokeny[2].c_str());
        String czas_txt;
        if (tokeny.size() >= 5) {
          mapa_pociagow[pociag_id].kierunek = kierunekZTekstu(tokeny[3]);
          czas_txt = tokeny[4];
          for (size_t indeks = 5; indeks < tokeny.size(); indeks++) {
            czas_txt += ":" + tokeny[indeks];
          }
        } else {
          czas_txt = tokeny[3];
        }
        uint32_t czas = konwertujCzasNaSekundy(czas_txt);
        wjazdDoSekcji(pociag_id, sekcja_id, czas);
      }
      Serial.print("-> [ESP32 INFO] Pociąg wjechał do sekcji: ");
      Serial.println(tresc);
    }
    else if (tresc.startsWith("SEK_WYJ:")) {
      // Format: EVT:SEK_WYJ:pociag_id:sekcja_id:czas
      int idx1 = tresc.indexOf(':', 8);
      int idx2 = tresc.indexOf(':', idx1 + 1);
      if (idx1 != -1 && idx2 != -1) {
        uint16_t pociag_id = modyfikujId(tresc.substring(8, idx1).c_str());
        uint16_t sekcja_id = modyfikujId(tresc.substring(idx1 + 1, idx2).c_str());
        uint32_t czas = konwertujCzasNaSekundy(tresc.substring(idx2 + 1));
        wyjazdZSekcji(pociag_id, sekcja_id, czas);
      }
      Serial.print("-> [ESP32 INFO] Pociąg wyjechał z sekcji: ");
      Serial.println(tresc);
    }
    else if (tresc.startsWith("AWR:")) {
      // Format: EVT:AWR:zwrotnica_id:pociag_id:czas
      std::vector<String> tokeny = rozdzielTekst(tresc, ':');
      if (tokeny.size() >= 3) {
        uint16_t id_zwrotnicy = modyfikujId(tokeny[1].c_str());
        for (const auto& [id_sekcji, sekcja] : mapa_sekcji) {
          for (const auto& polaczenie : sekcja.polaczenia) {
            for (const auto& zwrotnica : polaczenie.wymagane_zwrotnice) {
              if (zwrotnica.id_zwrotnicy == id_zwrotnicy) {
                zatrzymajRuchWokolSekcji(id_sekcji);
                zatrzymajRuchWokolSekcji(polaczenie.id_sekcji_docelowej);
              }
            }
          }
        }
      }
      Serial.print("-> [ESP32 ALARM] Rozprucie zwrotnicy! ");
      Serial.println(tresc);
    }
    else if (tresc.startsWith("ZWR:")) {
      // Format: EVT:ZWR:zwrotnica_id:PLU|MIN:wymuszenie:czas
      std::vector<String> tokeny = rozdzielTekst(tresc, ':');
      if (tokeny.size() >= 3) {
        uint16_t id_zwrotnicy = modyfikujId(tokeny[1].c_str());
        auto it = mapa_zwrotnic.find(id_zwrotnicy);
        if (it != mapa_zwrotnic.end()) {
          it->second.pozycja = tokeny[2] == "MIN" ? Zwrot::MINUS : Zwrot::PLUS;
          ustawSygnaIStanZwrotnicSIPP();
        }
      }
    }
    else if (tresc.startsWith("SYG:")) {
      // Format: EVT:SYG:semafor_id:CZE|ZOL|ZIE|SZ:czas
      std::vector<String> tokeny = rozdzielTekst(tresc, ':');
      if (tokeny.size() >= 3) {
        uint16_t id_semafora = modyfikujId(tokeny[1].c_str());
        auto it = mapa_semaforow.find(id_semafora);
        if (it != mapa_semaforow.end()) {
          if (tokeny[2] == "CZE") it->second.sygnal = Sygnal::CZERWONY;
          else if (tokeny[2] == "ZOL") it->second.sygnal = Sygnal::ZOLTY;
          else if (tokeny[2] == "ZIE") it->second.sygnal = Sygnal::ZIELONY;
          else if (tokeny[2] == "SZ") it->second.sygnal = Sygnal::SZ;
        }
      }
    }
    else if (tresc.startsWith("CZE_STP:")) {
      // Format: EVT:CZE_STP:pociag_id:semafor_id:czas
      std::vector<String> tokeny = rozdzielTekst(tresc, ':');
      if (tokeny.size() >= 2) {
        uint16_t id_pociagu = modyfikujId(tokeny[1].c_str());
        auto it_pociagu = mapa_pociagow.find(id_pociagu);
        if (it_pociagu != mapa_pociagow.end()) {
          it_pociagu->second.zatrzymany_na_czerwonym = true;
        }
      }
    }
    else if (tresc.startsWith("CZE_ODJ:")) {
      // Format: EVT:CZE_ODJ:pociag_id:semafor_id:czas
      std::vector<String> tokeny = rozdzielTekst(tresc, ':');
      if (tokeny.size() >= 2) {
        uint16_t id_pociagu = modyfikujId(tokeny[1].c_str());
        auto it_pociagu = mapa_pociagow.find(id_pociagu);
        if (it_pociagu != mapa_pociagow.end()) {
          it_pociagu->second.zatrzymany_na_czerwonym = false;
        }
      }
    }
    else if (tresc.startsWith("PRC:")) {
      // Format: EVT:PRC:pociag_id:semafor_id:czas
      std::vector<String> tokeny = rozdzielTekst(tresc, ':');
      if (tokeny.size() >= 3) {
        uint16_t id_pociagu = modyfikujId(tokeny[1].c_str());
        uint16_t id_semafora = modyfikujId(tokeny[2].c_str());
        auto it_pociagu = mapa_pociagow.find(id_pociagu);

        if (it_pociagu != mapa_pociagow.end()) {
          auto it_sekcji = mapa_sekcji.find(it_pociagu->second.czolo);
          if (it_sekcji != mapa_sekcji.end()) {
            for (const auto& polaczenie : it_sekcji->second.polaczenia) {
              if (polaczenie.id_semafora != id_semafora) continue;

              auto it_docelowej = mapa_sekcji.find(polaczenie.id_sekcji_docelowej);
              if (it_docelowej != mapa_sekcji.end() && !it_docelowej->second.zajeta) {
                zezwolenieNaJazde(id_pociagu);
                Serial.print("-> [ESP32 ALARM] Przejazd na czerwonym przez P");
                Serial.print(id_pociagu);
                Serial.print(", sekcja za S");
                Serial.print(id_semafora);
                Serial.println(" jest wolna; wyslano ZGD.");
              }
              break;
            }
          }
        }
      }
    }
    else if (tresc.startsWith("STP:")) {
      // Format: EVT:STP:pociag_id:nazwa_stacji:czas
      std::vector<String> tokeny = rozdzielTekst(tresc, ':');
      if (tokeny.size() >= 2) {
        uint16_t id_pociagu = modyfikujId(tokeny[1].c_str());
        auto it_pociagu = mapa_pociagow.find(id_pociagu);
        if (it_pociagu != mapa_pociagow.end()) {
          it_pociagu->second.na_postoju_stacyjnym = true;
        }
      }
    }
    else if (tresc.startsWith("ODJ:")) {
      // Format: EVT:ODJ:pociag_id:nazwa_stacji:czas
      std::vector<String> tokeny = rozdzielTekst(tresc, ':');
      if (tokeny.size() >= 3) {
        uint16_t id_pociagu = modyfikujId(tokeny[1].c_str());
        auto it_pociagu = mapa_pociagow.find(id_pociagu);
        if (it_pociagu != mapa_pociagow.end()) {
          Pociag& pociag = it_pociagu->second;
          pociag.na_postoju_stacyjnym = false;
          if (pociag.indeks_nastepnego_przystanku < pociag.rozklad.size() &&
              pociag.rozklad[pociag.indeks_nastepnego_przystanku].stacja_docelowa == tokeny[2]) {
            pociag.indeks_nastepnego_przystanku++;
          }
        }
      }
    }
    else {
      // Inne zdarzenia: SYG, ZWR, EST, STP, PRC itp.
      Serial.print("-> [ESP32 EVT]: ");
      Serial.println(tresc);
    }
    if (tresc.startsWith("MAPA_SEKCJI:") || tresc.startsWith("SEK_WJA:") ||
      tresc.startsWith("SEK_WYJ:") || tresc.startsWith("CZE_ODJ:") ||
      tresc.startsWith("ODJ:") ||
        tresc.startsWith("AWR:")) {
      przeliczSterowanieSIPP();
    }
  }
  // 2. DANE W ODPOWIEDZI NA ZAPYTANIE (DAT)
  else if (typ == "DAT") {
    obsluzOdpowiedzDAT(tresc);
  }
  // 3. POTWIERDZENIA WYKONANIA KOMENDY (OK)
  else if (typ == "OK") {
    obsluzOdpowiedzOk(tresc);
  }
  // 4. BŁĘDY Z SYMUTATORA (ERR)
  else if (typ == "ERR") {
    Serial.print("-> [ESP32 ERROR]: Błąd z symulatora: ");
    Serial.println(tresc);
  }
}

/**
 * Parsowanie i obsługa dużej mapy sekcji w formacie JSON
 */
void obsluzMapeSekcji(String jsonStr) {
  // Dla dużych dokumentów JSON na ESP32 używamy JsonDocument (ArduinoJson v7)
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, jsonStr);

  if (error) {
    Serial.print("ERR:PARSER_JSON_FAILED:");
    Serial.println(error.f_str());
    return;
  }

  // Serial.println("OK:MAPA_SEKCJI_PARSED");

  mapa_sekcji.clear();

  JsonObject obj = doc.as<JsonObject>();
  for (JsonPair kv : obj) {
    JsonObject sekcjaJson = kv.value().as<JsonObject>();

    Sekcja s;
    s.id = modyfikujId(sekcjaJson["id"] | kv.key().c_str());
    s.dlugosc = sekcjaJson["dlugosc"] | 0;
    JsonObject pozycjaJson = sekcjaJson["pozycja"].as<JsonObject>();
    s.pozycja_x = pozycjaJson["x"] | 0.0f;
    s.pozycja_y = pozycjaJson["y"] | 0.0f;
    s.zajeta = false;
    s.pociag_id = 0;

    // 1. Parsowanie semaforów granicznych
    JsonArray semGraniczne = sekcjaJson["graniczne_semafory"].as<JsonArray>();
    for (JsonVariant semVar : semGraniczne) {
      uint8_t semId = modyfikujId(semVar.as<const char*>());
      // Rejestracja semafora w globalnej bazie (jeśli jeszcze nie istnieje)
      if (mapa_semaforow.find(semId) == mapa_semaforow.end()) {
        mapa_semaforow[semId] = {semId, Sygnal::CZERWONY};
      }
    }

    // 2. Parsowanie połączeń z innymi sekcjami
    JsonArray polaczeniaJson = sekcjaJson["polaczenia"].as<JsonArray>();
    for (JsonObject polJson : polaczeniaJson) {
      PolaczenieSekcji pol;
      pol.id_sekcji_docelowej = modyfikujId(polJson["sekcja_docelowa"] | "0");
      pol.id_semafora = modyfikujId(polJson["semafor_id"] | "");
      pol.kierunek = kierunekZTekstu(String(polJson["kierunek"] | "ZACHOD"));
      pol.liczba_kafelkow_zwrotnic = polJson["liczba_kafelkow_zwrotnic"] | 0;

      // Parsowanie wymaganych zwrotnic
      JsonArray zwrotniceJson = polJson["zwrotnice"].as<JsonArray>();
      for (JsonObject zwrotJson : zwrotniceJson) {
        UstawienieZwrotnicy uz;
        uz.id_zwrotnicy = modyfikujId(zwrotJson["id"] | "");
        
        const char* poz = zwrotJson["pozycja"] | "PLUS";
        uz.wymagany_zwrot = (strcmp(poz, "MINUS") == 0) ? Zwrot::MINUS : Zwrot::PLUS;

        pol.wymagane_zwrotnice.push_back(uz);

        // Rejestracja zwrotnicy w globalnej bazie (jeśli jeszcze nie istnieje)
        if (mapa_zwrotnic.find(uz.id_zwrotnicy) == mapa_zwrotnic.end()) {
          mapa_zwrotnic[uz.id_zwrotnicy] = {uz.id_zwrotnicy, Zwrot::PLUS, false, false};
        }
      }

      s.polaczenia.push_back(pol);
    }
    // 3. Rejestracja stacji (jeśli jest przypisana do sekcji)
    JsonObject stacjaJson = sekcjaJson["stacja"].as<JsonObject>();
    if (!stacjaJson.isNull()) {
      s.stacja.id = stacjaJson["id"] | "";
      s.stacja.nazwa = stacjaJson["nazwa"] | "";
      s.stacja.dlugosc_peronu = stacjaJson["dlugosc_peronu"] | 0;

      if (s.stacja.nazwa.length() > 0) {
        String stacjaStr = s.stacja.nazwa;
        if (std::find(Stacje.begin(), Stacje.end(), stacjaStr) == Stacje.end()) {
          Stacje.push_back(stacjaStr);
        }
      }
    }

    // Zapis gotowej sekcji do mapy
    mapa_sekcji[s.id] = s;
  }
  
  poprawZwrotnice(); // Poprawiamy stan zwrotnic po załadowaniu mapy
  przeliczSterowanieSIPP();

  // [DEBUG] Potwierdzenie załadowania do RAM
  if (DEBUG) {
    Serial.print("OK:MAPA_SEKCJI_LOADED: Zbudowano ");
    Serial.print(mapa_sekcji.size());
    Serial.print(" sekcji, ");
    Serial.print(mapa_zwrotnic.size());
    Serial.print(" zwrotnic, ");
    Serial.print(mapa_semaforow.size());
    Serial.println(" semaforów.");
    Serial.print("Stacje: ");
    for (const auto& stacja : Stacje) {
      Serial.print(stacja);
      Serial.print(" ");
    }
    Serial.println();
    Serial.println("lista sekcji i połączeń:");
    for (const auto& [id, sekcja] : mapa_sekcji) {
      Serial.print("Sekcja ");
      Serial.print(id);
      Serial.print(" (dlugosc=");
      Serial.print(sekcja.dlugosc);
      Serial.print(") -> Polaczenia: ");
      for (const auto& pol : sekcja.polaczenia) {
        Serial.print("Sekcja ");
        Serial.print(pol.id_sekcji_docelowej);
        Serial.print(" (semafor ");
        Serial.print(pol.id_semafora);
        Serial.print(") Zwrotnice: ");
        for (const auto& zwrot : pol.wymagane_zwrotnice) {
          Serial.print(zwrot.id_zwrotnicy);
          Serial.print("(");
          Serial.print((zwrot.wymagany_zwrot == Zwrot::PLUS) ? "PLUS" : "MINUS");
          Serial.print(") ");
        }
        Serial.print("; ");
      }
      Serial.println();
    }
    Serial.println("lista zwrotnic:");
    for (const auto& [id, zwrot] : mapa_zwrotnic) {
      Serial.print("Zwrotnica ");
      Serial.print(id);
      Serial.print(" (stan=");
      Serial.print((zwrot.pozycja == Zwrot::PLUS) ? "PLUS" : "MINUS");
      Serial.print(") ");
      Serial.println();
    }
    Serial.println("lista semaforów:");
    for (const auto& [id, sem] : mapa_semaforow) {
      Serial.print("Semafor ");
      Serial.print(id);
      Serial.print(" (sygnal=");
      switch (sem.sygnal) {
        case Sygnal::CZERWONY: Serial.print("CZERWONY"); break;
        case Sygnal::ZOLTY: Serial.print("ZOLTY"); break;
        case Sygnal::ZIELONY: Serial.print("ZIELONY"); break;
        case Sygnal::SZ: Serial.print("SZ"); break;
      }
      Serial.println(")");
    }
  }
}

/**
 * Obsługa danych zwrotnych z komend typu POC, ZWR, SYG, TOR
 */
void obsluzOdpowiedzDAT(String wiadomosc) {
  // Dzielimy tresc po dwukropkach
  int idx = wiadomosc.indexOf(':');
  if (idx == -1) return;

  String komenda = wiadomosc.substring(0, idx);
  String dane = wiadomosc.substring(idx + 1);

  if (komenda == "POC") {
    // Format: POC:id:pred_akt:pred_doc:pred_kmh:typ:kier:czolo:ogon:dlugosc:sekcja:stacja_nast:przyj:odj:postoj:czer_aktyw:czer_sem:pred_max
    std::vector<String> tokeny = rozdzielTekst(dane, ':');
    if (tokeny.size() >= 9) {
      uint16_t pociag_id = modyfikujId(tokeny[0].c_str());
      auto it = mapa_pociagow.find(pociag_id);
      if (it == mapa_pociagow.end()) {
        Pociag nowy = {};
        nowy.id = pociag_id;
        nowy.kierunek = Kierunek::ZACHOD;
        nowy.typ = TypPociagu::OSOBOWY;
        mapa_pociagow[pociag_id] = nowy;
        it = mapa_pociagow.find(pociag_id);
      }
      {
        Pociag& pociag = it->second;
        pociag.predkosc_aktualna_pxs = tokeny[1].toFloat();
        pociag.predkosc_docelowa_pxs = tokeny[2].toFloat();
        pociag.predkosc_kmh = tokeny[3].toFloat();
        pociag.typ = static_cast<TypPociagu>(tokeny[4].toInt());

        String kierStr = tokeny[5];
        if (kierStr == "POLNOC" || kierStr == "0") pociag.kierunek = Kierunek::POLNOC;
        else if (kierStr == "POLUDNIE" || kierStr == "1") pociag.kierunek = Kierunek::POLUDNIE;
        else if (kierStr == "WSCHOD" || kierStr == "2") pociag.kierunek = Kierunek::WSCHOD;
        else pociag.kierunek = Kierunek::ZACHOD;

        pociag.czolo = modyfikujId(tokeny[6].c_str());
        pociag.ogon = modyfikujId(tokeny[7].c_str());
        pociag.dlugosc = (uint16_t)tokeny[8].toInt();
        if (tokeny.size() >= 10) pociag.czolo = modyfikujId(tokeny[9].c_str());
        if (tokeny.size() >= 17) pociag.predkosc_max_pxs = tokeny[16].toFloat();

        if (tokeny.size() >= 14) {
          pociag.czas_postoju = (uint16_t)tokeny[13].toInt();
        }
        if (tokeny.size() >= 15) {
          pociag.przekroczenie_czerwonego = (tokeny[14] == "1");
        }

        auto it_sekcji_czola = mapa_sekcji.find(pociag.czolo);
        if (it_sekcji_czola != mapa_sekcji.end()) {
          it_sekcji_czola->second.zajeta = true;
          it_sekcji_czola->second.pociag_id = pociag_id;
        }
      }
      pytaj_o_rozklad_pociagu(pociag_id);
    }
    if (DEBUG) {
      Serial.print("Dane pociągu: ");
      Serial.println(dane);
    }
  } 
  else if (komenda == "ZWR") {
    // Format: ZWR:id:pozycja:stan_awaryjny
    // Parsowanie danych zwrotnicy
    int idx1 = dane.indexOf(':');
    if (idx1 != -1) {
      uint16_t zwrotnica_id = modyfikujId(dane.substring(0, idx1).c_str());
      String reszta = dane.substring(idx1 + 1);
      int idx2 = reszta.indexOf(':');
      if (idx2 != -1) {
        String pozycjaStr = reszta.substring(0, idx2);
        String stanAwaryjnyStr = reszta.substring(idx2 + 1);
        // Aktualizacja stanu zwrotnicy w mapie_zwrotnic na podstawie odebranej ramki
        auto it = mapa_zwrotnic.find(zwrotnica_id);
        if (it != mapa_zwrotnic.end()) {
          Zwrotnica& zwrotnica = it->second;
          zwrotnica.pozycja = (pozycjaStr == "PLUS") ? Zwrot::PLUS : Zwrot::MINUS;
          zwrotnica.awaria = (stanAwaryjnyStr == "1");
        }
      }
    }
    Serial.print("Stan zwrotnicy: ");
    Serial.println(dane);
  }
  else if (komenda == "SYG") {
    // Format: SYG:id:sygnal
    // Aktualizacja stanu semafora w mapie_semaforow na podstawie odebranej ramki
    int idx1 = dane.indexOf(':');
    if (idx1 != -1) {
      uint16_t semafor_id = modyfikujId(dane.substring(0, idx1).c_str());
      String sygnalStr = dane.substring(idx1 + 1);
      auto it = mapa_semaforow.find(semafor_id);
      if (it != mapa_semaforow.end()) {
        Semafor& semafor = it->second;
        if (sygnalStr == "CZERWONY") semafor.sygnal = Sygnal::CZERWONY;
        else if (sygnalStr == "ZOLTY") semafor.sygnal = Sygnal::ZOLTY;
        else if (sygnalStr == "ZIELONY") semafor.sygnal = Sygnal::ZIELONY;
        else if (sygnalStr == "SZ") semafor.sygnal = Sygnal::SZ;
      }
    }
    Serial.print("Stan sygnalizatora: ");
    Serial.println(dane);
  }
  else if (komenda == "SNP") {
    // Format: SNP:HH:MM:SS:liczba_pociagow:liczba_semaforow:liczba_zwrotnic:liczba_sekcji
    std::vector<String> pola = rozdzielTekst(dane, ':');
    if (pola.size() >= 4) {
      oczekiwana_liczba_pociagow = (uint16_t)pola[3].toInt();
    }
    Serial.print("Stan symulatora: ");
    Serial.println(dane);
  }
  else if (komenda == "ROZ") {
    // Format: ROZ:pociag_id:liczba_przystankow:stacja1;postoj1;przyj1;odj1:stacja2;postoj2;przyj2;odj2:...
    std::vector<String> tokeny = rozdzielTekst(dane, ':');
    if (tokeny.size() >= 2) {
      uint16_t pociag_id = modyfikujId(tokeny[0].c_str());
      auto it = mapa_pociagow.find(pociag_id);
      if (it != mapa_pociagow.end()) {
        Pociag& pociag = it->second;
        pociag.rozklad.clear();
        int liczbaPrzystankow = tokeny[1].toInt();
        for (size_t i = 2; i < tokeny.size() && (int)(i - 2) < liczbaPrzystankow; i++) {
          std::vector<String> subtok = rozdzielTekst(tokeny[i], ';');
          if (subtok.size() >= 4) {
            Rozklad r;
            r.stacja_docelowa = subtok[0];
            r.czas_postoju = (uint16_t)subtok[1].toInt();
            r.czas_przyjazdu = konwertujCzasNaSekundy(subtok[2]);
            r.czas_odjazdu = konwertujCzasNaSekundy(subtok[3]);
            pociag.rozklad.push_back(r);
          }
        }
        pociag.rozklad_zaladowany = true;
        pociag.indeks_nastepnego_przystanku = 0;
        if (wszystkieRozkladyZaladowane()) {
          przeliczSterowanieSIPP();
        }
        if (DEBUG) {
          Serial.print("-> [ESP32 INFO] Załadowano pełny rozkład dla pociągu ");
          Serial.print(pociag_id);
          Serial.print(" (liczba przystanków: ");
          Serial.print(pociag.rozklad.size());
          Serial.println("):");
          for (size_t idx = 0; idx < pociag.rozklad.size(); idx++) {
            const auto& r = pociag.rozklad[idx];
            Serial.print("   Przystanek ");
            Serial.print(idx + 1);
            Serial.print(": ");
            Serial.print(r.stacja_docelowa);
            Serial.print(" [postój: ");
            Serial.print(r.czas_postoju);
            Serial.print("s, przyjazd: ");
            Serial.print(r.czas_przyjazdu);
            Serial.print("s, odjazd: ");
            Serial.print(r.czas_odjazdu);
            Serial.println("s]");
          }
        }
      }
    }
    Serial.print("Rozkład pociągu: ");
    Serial.println(dane);
  }
  else {
    Serial.print("Nieznana komenda DAT: ");
    Serial.println(wiadomosc);
  }
}

uint16_t modyfikujId(const char* str) {
  if (!str || strlen(str) == 0) return 0;
  while (*str && !isdigit(*str)) {
    str++; // Pomijamy litery
  }
  return (uint16_t)atoi(str);
}

void obsluzOdpowiedzOk(String wiadomosc) {
  // Obsługa potwierdzenia wykonania komendy PING
  if (wiadomosc.startsWith("PNG")) {
    // ustawienie czasu symulacji na podstawie odpowiedzi z symulatora
    int idx1 = wiadomosc.indexOf(':');
    if (idx1 != -1) {
      String czasStr = wiadomosc.substring(idx1 + 1);
      aktualny_czas_symulacji = konwertujCzasNaSekundy(czasStr);
      ostatnia_aktualizacja_czasu_ms = millis();
      reszta_czasu_symulacji_ms = 0.0f;
      Serial.print("-> [ESP32 INFO] Aktualny czas symulacji: ");
      Serial.println(czasStr);
    }
  }
  // Obsługa potwierdzenia wykonania komendy UST
  else if (wiadomosc.startsWith("UST")) {
    // Wczytanie ustawień symulatora po starcie
    int idx1 = wiadomosc.indexOf(':');
    if (idx1 != -1) {
      String ustawieniaStr = wiadomosc.substring(idx1 + 1);
      std::vector<String> pola = rozdzielTekst(ustawieniaStr, ':');
      if (pola.size() >= 3) {
        wspolczynnik_szybkosci_symulacji = pola[0].toFloat();
        skala_w_metrach = pola[1].toFloat();
        rozmiar_kafelka_w_px = (uint8_t)pola[2].toInt();
        Serial.printf(
            "-> [ESP32 INFO] Ustawienia: czas=%.2f, skala=%.2f, px=%u\n",
            wspolczynnik_szybkosci_symulacji,
            skala_w_metrach,
            rozmiar_kafelka_w_px);
      } else {
        Serial.print("-> [ESP32 ERROR] Niepoprawna ramka UST: ");
        Serial.println(ustawieniaStr);
      }
    }
  }
  
  else { // pozostałe potwierdzenia komend
    Serial.print("-> [ESP32 OK]: ");
    Serial.println(wiadomosc);
  }
}

void poprawZwrotnice() {
  // Funkcja do poprawy stanu zwrotnic koniecznych do zmiany sekcji po otrzymaniu danych z symulatora
  // Przechodzi przez wszystkie pary sekcji i jeśli w obu kierunkach wymagane są różne pozycje zwrotnic (np. 1->2 wymaga plus a 2->1 wymaga minus), to w obu kierunkach ustawia daną zwrotnicę w kierunku minus.
  // Zapobiega to rozpruciu zwrotnicy.
  for (const auto& [id, sekcja] : mapa_sekcji) {
    for (const auto& pol : sekcja.polaczenia) {
      for (const auto& zwrot : pol.wymagane_zwrotnice) {
        // Sprawdzamy, czy istnieje połączenie w przeciwnym kierunku
        auto it = mapa_sekcji.find(pol.id_sekcji_docelowej);
        if (it != mapa_sekcji.end()) {
          const Sekcja& sekcja_docelowa = it->second;
          for (const auto& pol_doc : sekcja_docelowa.polaczenia) {
            if (pol_doc.id_sekcji_docelowej == sekcja.id) {
              // Znaleziono połączenie w przeciwnym kierunku
              for (const auto& zwrot_doc : pol_doc.wymagane_zwrotnice) {
                if (zwrot_doc.id_zwrotnicy == zwrot.id_zwrotnicy) {
                  // Jeśli pozycje są różne, ustawiamy na MINUS
                  if (zwrot.wymagany_zwrot != zwrot_doc.wymagany_zwrot) {
                    mapa_sekcji[sekcja.id].polaczenia[&pol - &sekcja.polaczenia[0]].wymagane_zwrotnice[&zwrot - &pol.wymagane_zwrotnice[0]].wymagany_zwrot = Zwrot::MINUS;
                    mapa_sekcji[sekcja_docelowa.id].polaczenia[&pol_doc - &sekcja_docelowa.polaczenia[0]].wymagane_zwrotnice[&zwrot_doc - &pol_doc.wymagane_zwrotnice[0]].wymagany_zwrot = Zwrot::MINUS;
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}

void wjazdDoSekcji(uint16_t pociag_id, uint16_t sekcja_id, uint32_t czas) {
  // Funkcja do obsługi zdarzenia wjazdu pociągu do sekcji
  // Rejestracja pociągu jeśli jeszcze nie istnieje
  if (mapa_pociagow.find(pociag_id) == mapa_pociagow.end()) {
    Pociag p;
    p.id = pociag_id;
    p.predkosc_docelowa_pxs = 0.0f;
    p.predkosc_aktualna_pxs = 0.0f;
    p.predkosc_max_pxs = 0.0f;
    p.predkosc_kmh = 0.0f;
    p.kierunek = Kierunek::ZACHOD; // Domyślny kierunek
    p.typ = TypPociagu::OSOBOWY; // Domyślny typ
    p.czolo = sekcja_id; // Czoło wjechało
    p.ogon = sekcja_id; // Ostatnio wjechana sekcja
    p.dlugosc = 0;
    p.czas_postoju = 0;
    p.przekroczenie_czerwonego = false;
    p.zatrzymany_na_czerwonym = false;
    p.na_postoju_stacyjnym = false;
    p.awaria = false;
    p.rozklad_zaladowany = false;
    p.indeks_nastepnego_przystanku = 0;
    p.sekcja_z_terminem_wyjazdu = 0;
    p.termin_wyjazdu_z_sekcji = 0;
    mapa_pociagow[pociag_id] = p;
    pytaj_o_pociag(pociag_id); // Zapytanie o szczegóły pociągu
    Serial.print("-> [ESP32 INFO] Zarejestrowano nowy pociąg o ID: ");
    Serial.println(pociag_id);
    pytaj_o_rozklad_pociagu(pociag_id); // Zapytanie o rozkład pociągu
  }
  // dodanie pociągu do sekcji
  auto obiekt = mapa_sekcji.find(sekcja_id);
  if (obiekt != mapa_sekcji.end()) {
    Sekcja& sekcja = obiekt->second;
    auto it_pociagu = mapa_pociagow.find(pociag_id);
    if (it_pociagu != mapa_pociagow.end()) {
      Pociag& pociag = it_pociagu->second;
      for (const auto& rezerwacja : sekcja.rezerwacje) {
        if (rezerwacja.id_pociagu == pociag_id) {
          pociag.sekcja_z_terminem_wyjazdu = sekcja_id;
          pociag.termin_wyjazdu_z_sekcji = rezerwacja.czas_koniec;
          break;
        }
      }
    }
    sekcja.zajeta = true;
    sekcja.pociag_id = pociag_id;
    mapa_pociagow[pociag_id].czolo = sekcja_id;
    Serial.print("-> [ESP32 INFO] Pociąg ");
    Serial.print(pociag_id);
    Serial.print(" wjechał do sekcji ");
    Serial.print(sekcja_id);
    Serial.print(" o czasie symulacji ");
    Serial.println(czas);
  } else {
    Serial.print("-> [ESP32 ERROR] Nieznana sekcja: ");
    Serial.println(sekcja_id);
  }
}

void wyjazdZSekcji(uint16_t pociag_id, uint16_t sekcja_id, uint32_t czas) {
  // Funkcja do obsługi zdarzenia wyjazdu pociągu z sekcji
  // usunięcie pociągu z sekcji
  auto obiekt = mapa_sekcji.find(sekcja_id);
  if (obiekt != mapa_sekcji.end()) {
    Sekcja& sekcja = obiekt->second;
    if (sekcja.pociag_id == pociag_id) {
      sekcja.zajeta = false;
      sekcja.pociag_id = 0;
      auto it_pociagu = mapa_pociagow.find(pociag_id);
      if (it_pociagu != mapa_pociagow.end() && it_pociagu->second.sekcja_z_terminem_wyjazdu == sekcja_id) {
        it_pociagu->second.sekcja_z_terminem_wyjazdu = 0;
        it_pociagu->second.termin_wyjazdu_z_sekcji = 0;
      }
      Serial.print("-> [ESP32 INFO] Pociąg ");
      Serial.print(pociag_id);
      Serial.print(" wyjechał z sekcji ");
      Serial.print(sekcja_id);
      Serial.print(" o czasie symulacji ");
      Serial.println(czas);
    }
  }
}

// --- FUNKCJE POMOCNICZE DO WYSYŁANIA KOMEND Z ESP32 DO PYTHONA ---

void przestawZwrotnice(uint16_t id, String pozycja) {
  // Wysyła np. ZWR:Z01:PLU
  Serial.print("ZWR:");
  String idStr = odwrotnieModyfikujId(id, "T");
  Serial.print(idStr);
  Serial.print(":");
  Serial.println(pozycja);
}

void ustawSygnal(uint16_t id, String sygnal) {
  // Wysyła np. SYG:S01:ZIE
  Serial.print("SYG:");
  String idStr = odwrotnieModyfikujId(id, "S");
  Serial.print(idStr);
  Serial.print(":");
  Serial.println(sygnal);
}

void zezwolenieNaJazde(uint16_t id) {
  // Wysyła np. ZGD:P01
  Serial.print("ZGD:");
  String idStr = odwrotnieModyfikujId(id, "P");
  Serial.println(idStr);
}

void ustawLimitPredkosci(uint16_t id, uint8_t predkosc) {
  // Wysyła np. LIM:P01:80
  Serial.print("LIM:");
  String idStr = odwrotnieModyfikujId(id, "P");
  Serial.print(idStr);
  Serial.print(":");
  Serial.println(predkosc);
}

void wylaczLimitPredkosci(uint16_t id) {
  // Wysyła np. LIM:P01:OFF
  Serial.print("LIM:");
  String idStr = odwrotnieModyfikujId(id, "P");
  Serial.print(idStr);
  Serial.print(":");
  Serial.println("OFF");
}

void zmienKierunekPociagu(uint16_t id, Kierunek kierunek) {
  // Wysyła np. KIR:P01:2
  Serial.print("KIR:");
  String idStr = odwrotnieModyfikujId(id, "P");
  Serial.print(idStr);
  Serial.print(":");
  Serial.println(static_cast<uint8_t>(kierunek));
}

void ESTOP(){
  // Wysyła np. EST:1
  Serial.print("EST:");
  if (awaria) {
    Serial.println("0"); // Wyłączenie awarii
    awaria = false;
  } else {
    Serial.println("1"); // Włączenie awarii
    awaria = true;
  }
  
}

void pytaj_o_pociag(uint16_t pociag_id) {
  Serial.print("POC:");
  String idStr = odwrotnieModyfikujId(pociag_id, "P");
  Serial.println(idStr);
}

void pytaj_o_semafor(uint16_t semafor_id) {
  Serial.print("SYG:");
  String idStr = odwrotnieModyfikujId(semafor_id, "S");
  Serial.println(idStr);
}

void pytaj_o_zwrotnice(uint16_t zwrotnica_id) {
  Serial.print("ZWR:");
  String idStr = odwrotnieModyfikujId(zwrotnica_id, "T");
  Serial.println(idStr);
}

void pytaj_o_sekcje(uint16_t pociag_id) {
  Serial.print("SEK:");
  String idStr = odwrotnieModyfikujId(pociag_id, "P");
  Serial.println(idStr);
}

void pytaj_o_czas_symulacji() {
  Serial.println("PING");
}

void pytaj_o_rozklad_pociagu(uint16_t pociag_id) {
  Serial.print("ROZ:");
  String idStr = odwrotnieModyfikujId(pociag_id, "P");
  Serial.println(idStr);
}

void pytaj_o_ustawienia_symulatora() {
  Serial.println("UST");
}

// --- FUNKCJE POMOCNICZE DO OBSŁUGI STEROWANIA RUCHU KOLEJOWEGO ---

void przestawZwrotniceDlaPolaczenia(uint16_t sekcja_id, uint16_t sekcja_docelowa_id) {
  // Funkcja przestawia zwrotnice wymagane do przejazdu z sekcji_id do sekcji_docelowa_id
  auto it = mapa_sekcji.find(sekcja_id);
  if (it != mapa_sekcji.end()) {
    const Sekcja& sekcja = it->second;
    for (const auto& pol : sekcja.polaczenia) {
      if (pol.id_sekcji_docelowej == sekcja_docelowa_id) {
        for (const auto& zwrot : pol.wymagane_zwrotnice) {
          String pozycjaStr = (zwrot.wymagany_zwrot == Zwrot::PLUS) ? "PLU" : "MIN";
          przestawZwrotnice(zwrot.id_zwrotnicy, pozycjaStr);
        }
      }
    }
  }
}

void ustawSygnalyDlaPolaczenia(uint16_t sekcja_id, uint16_t sekcja_docelowa_id) {
  // Funkcja ustawia sygnały semaforów wymagane do przejazdu z sekcji_id do sekcji_docelowa_id
  auto it = mapa_sekcji.find(sekcja_id);
  if (it != mapa_sekcji.end()) {
    const Sekcja& sekcja = it->second;
    for (const auto& pol : sekcja.polaczenia) {
      if (pol.id_sekcji_docelowej == sekcja_docelowa_id) {
        ustawSygnal(pol.id_semafora, "ZIE"); // Ustawienie sygnału na zielony
      }
    }
  }
}

uint32_t priorytetPociagu(const Pociag& pociag) {
  uint32_t priorytet_bazowy = 1;
  if (pociag.typ == TypPociagu::TECHNICZNY) priorytet_bazowy = 4;
  else if (pociag.typ == TypPociagu::POSPIESZNY) priorytet_bazowy = 3;
  else if (pociag.typ == TypPociagu::OSOBOWY) priorytet_bazowy = 2;

  uint32_t opoznienie_s = 0;
  if (pociag.indeks_nastepnego_przystanku < pociag.rozklad.size()) {
    const Rozklad& przystanek = pociag.rozklad[pociag.indeks_nastepnego_przystanku];
    if (przystanek.czas_przyjazdu > 0 && aktualny_czas_symulacji > przystanek.czas_przyjazdu) {
      opoznienie_s = min(aktualny_czas_symulacji - przystanek.czas_przyjazdu, 99999UL);
    }
  }
  return priorytet_bazowy * 100000UL + opoznienie_s;
}

bool sekcjaMaDocelowyPeron(const Sekcja& sekcja, const Pociag& pociag, const String& nazwa_stacji) {
  if (sekcja.stacja.nazwa != nazwa_stacji ||
      sekcja.stacja.dlugosc_peronu < pociag.dlugosc) {
    return false;
  }

  // Peron zajety przez inny pociag nie jest dopuszczalnym celem trasy.
  // BFS musi kontynuowac poszukiwanie, aby wybrac inny wolny peron tej
  // samej stacji, zamiast kierowac pociag na zajety odcinek.
  return !sekcja.zajeta || sekcja.pociag_id == pociag.id;
}

float prawostronnyWynikSekcji(const Sekcja& sekcja, Kierunek kierunek) {
  switch (kierunek) {
    // Kierunek opisuje stronę wjazdu, więc rzeczywisty wektor ruchu jest przeciwny.
    case Kierunek::POLNOC: return -sekcja.pozycja_x;
    case Kierunek::POLUDNIE: return sekcja.pozycja_x;
    case Kierunek::WSCHOD: return -sekcja.pozycja_y;
    case Kierunek::ZACHOD: return sekcja.pozycja_y;
    case Kierunek::POLNOC_WSCHOD: return -sekcja.pozycja_x - sekcja.pozycja_y;
    case Kierunek::POLNOC_ZACHOD: return sekcja.pozycja_x - sekcja.pozycja_y;
    case Kierunek::POLUDNIE_WSCHOD: return -sekcja.pozycja_x + sekcja.pozycja_y;
    case Kierunek::POLUDNIE_ZACHOD: return sekcja.pozycja_x + sekcja.pozycja_y;
  }
  return 0.0f;
}

bool sekcjaMaRezerwacjeInnegoPociagu(const Sekcja& sekcja, uint16_t id_pociagu) {
  for (const auto& rezerwacja : sekcja.rezerwacje) {
    if (rezerwacja.id_pociagu != id_pociagu &&
        rezerwacja.czas_start <= aktualny_czas_symulacji &&
        aktualny_czas_symulacji < rezerwacja.czas_koniec + ZAPAS_REZERWACJI_S) {
      return true;
    }
  }
  return false;
}

bool znajdzTraseDoPeronu(
    const Pociag& pociag,
    std::vector<uint16_t>& trasa) {
  if (pociag.indeks_nastepnego_przystanku >= pociag.rozklad.size()) return false;
  const String& cel = pociag.rozklad[pociag.indeks_nastepnego_przystanku].stacja_docelowa;
  if (cel.length() == 0 || mapa_sekcji.find(pociag.czolo) == mapa_sekcji.end()) return false;
  if (sekcjaMaDocelowyPeron(mapa_sekcji[pociag.czolo], pociag, cel)) {
    trasa.push_back(pociag.czolo);
    return true;
  }

  // Poprzednia wersja przechowywala w kolejce cala sciezke dla kazdej galezi.
  // W grafie 22 sekcji i 86 polaczen oznaczalo to tworzenie ogromnej liczby
  // prostych sciezek, co konczylo sie bad_alloc i resetem ESP.
  std::vector<uint16_t> kolejka = {pociag.czolo};
  std::map<uint16_t, uint16_t> poprzednik;
  std::map<uint16_t, uint8_t> glebokosc;
  uint16_t najlepszy_peron = 0;
  uint8_t glebokosc_peronu = MAKS_KRAWEDZI_TRASY + 1;
  poprzednik[pociag.czolo] = 0;
  glebokosc[pociag.czolo] = 0;

  for (size_t indeks = 0; indeks < kolejka.size(); indeks++) {
    uint16_t aktualna = kolejka[indeks];
    const Sekcja& sekcja = mapa_sekcji[aktualna];
    if (glebokosc[aktualna] > glebokosc_peronu) break;
    if (aktualna != pociag.czolo &&
        sekcjaMaDocelowyPeron(sekcja, pociag, cel)) {
      if (najlepszy_peron == 0 ||
        glebokosc[aktualna] < glebokosc_peronu ||
        (glebokosc[aktualna] == glebokosc_peronu &&
         prawostronnyWynikSekcji(sekcja, pociag.kierunek) >
           prawostronnyWynikSekcji(mapa_sekcji[najlepszy_peron], pociag.kierunek))) {
        najlepszy_peron = aktualna;
        glebokosc_peronu = glebokosc[aktualna];
      }
      continue;
    }
    if (glebokosc[aktualna] >= MAKS_KRAWEDZI_TRASY) continue;

    std::vector<const PolaczenieSekcji*> polaczenia_posortowane;
    for (const auto& polaczenie : sekcja.polaczenia) {
      polaczenia_posortowane.push_back(&polaczenie);
    }
    std::sort(
        polaczenia_posortowane.begin(),
        polaczenia_posortowane.end(),
        [&pociag](const PolaczenieSekcji* lewe, const PolaczenieSekcji* prawe) {
          const Sekcja& sekcja_lewa = mapa_sekcji[lewe->id_sekcji_docelowej];
          const Sekcja& sekcja_prawa = mapa_sekcji[prawe->id_sekcji_docelowej];
          return prawostronnyWynikSekcji(sekcja_lewa, pociag.kierunek) >
              prawostronnyWynikSekcji(sekcja_prawa, pociag.kierunek);
        });

    for (const PolaczenieSekcji* polaczenie_wsk : polaczenia_posortowane) {
      const PolaczenieSekcji& polaczenie = *polaczenie_wsk;
      uint16_t sasiad = polaczenie.id_sekcji_docelowej;
      if (poprzednik.find(sasiad) != poprzednik.end()) continue;
      auto it_sasiada = mapa_sekcji.find(sasiad);
      if (it_sasiada == mapa_sekcji.end()) continue;
      if (it_sasiada->second.zajeta && it_sasiada->second.pociag_id != pociag.id) continue;
      if (sekcjaMaRezerwacjeInnegoPociagu(it_sasiada->second, pociag.id)) continue;
      poprzednik[sasiad] = aktualna;
      glebokosc[sasiad] = glebokosc[aktualna] + 1;
      kolejka.push_back(sasiad);
    }
  }

  if (najlepszy_peron != 0) {
    for (uint16_t id = najlepszy_peron; id != 0; id = poprzednik[id]) {
      trasa.push_back(id);
    }
    std::reverse(trasa.begin(), trasa.end());
    return true;
  }
  return false;
}

const PolaczenieSekcji* znajdzPolaczenie(uint16_t zrodlo, uint16_t cel) {
  auto it = mapa_sekcji.find(zrodlo);
  if (it == mapa_sekcji.end()) return nullptr;
  for (const auto& polaczenie : it->second.polaczenia) {
    if (polaczenie.id_sekcji_docelowej == cel) return &polaczenie;
  }
  return nullptr;
}

uint32_t najblizszyWolnyCzasSekcji(
    uint16_t id_sekcji,
    uint16_t id_pociagu,
    uint32_t czas_start,
    uint32_t czas_trwania) {
  auto it = mapa_sekcji.find(id_sekcji);
  if (it == mapa_sekcji.end()) return UINT32_MAX;
  if (it->second.zajeta && it->second.pociag_id != id_pociagu) {
    return UINT32_MAX;
  }
  if (sekcjaMaRezerwacjeInnegoPociagu(it->second, id_pociagu)) {
    return UINT32_MAX;
  }

  bool znaleziono_konflikt = true;
  while (znaleziono_konflikt) {
    znaleziono_konflikt = false;
    uint32_t czas_koniec = czas_start + czas_trwania;
    for (const auto& rezerwacja : it->second.rezerwacje) {
      if (rezerwacja.id_pociagu == id_pociagu) continue;
      uint32_t koniec_rezerwacji = rezerwacja.czas_koniec + ZAPAS_REZERWACJI_S;
      if (czas_start < koniec_rezerwacji && czas_koniec > rezerwacja.czas_start) {
        czas_start = koniec_rezerwacji;
        znaleziono_konflikt = true;
        break;
      }
    }
  }
  return czas_start;
}

uint32_t najblizszyWolnyCzasZwrotnicy(
    uint16_t id_zwrotnicy,
    uint16_t id_pociagu,
    uint32_t czas_start,
    uint32_t czas_trwania) {
  auto it = mapa_zwrotnic.find(id_zwrotnicy);
  if (it == mapa_zwrotnic.end()) return UINT32_MAX;

  bool znaleziono_konflikt = true;
  while (znaleziono_konflikt) {
    znaleziono_konflikt = false;
    uint32_t czas_koniec = czas_start + czas_trwania;
    for (const auto& rezerwacja : it->second.rezerwacje) {
      if (rezerwacja.id_pociagu == id_pociagu) continue;
      uint32_t koniec_rezerwacji = rezerwacja.czas_koniec + ZAPAS_REZERWACJI_S;
      if (czas_start < koniec_rezerwacji && czas_koniec > rezerwacja.czas_start) {
        czas_start = koniec_rezerwacji;
        znaleziono_konflikt = true;
        break;
      }
    }
  }
  return czas_start;
}

bool rezerwujPrzejazdSIPP(Pociag& pociag, const std::vector<uint16_t>& trasa) {
  uint32_t czas = aktualny_czas_symulacji;
  std::vector<PlanowanaKrawedz> plan;
  for (size_t indeks = 1; indeks < trasa.size(); indeks++) {
    uint16_t zrodlo = trasa[indeks - 1];
    uint16_t cel = trasa[indeks];
    const PolaczenieSekcji* polaczenie = znajdzPolaczenie(zrodlo, cel);
    if (polaczenie == nullptr) {
      if (DEBUG) Serial.printf("[SIPP] Brak krawedzi %u -> %u\n", zrodlo, cel);
      return false;
    }

    uint32_t czas_przejazdu = obliczCzasPrzejazdu(pociag.id, zrodlo, cel);
    if (czas_przejazdu == 0) {
      if (DEBUG) {
        Serial.printf("[SIPP] Zerowy czas dla %u -> %u, v_doc=%.3f, v_max=%.3f\n",
                      zrodlo, cel, pociag.predkosc_docelowa_pxs, pociag.predkosc_max_pxs);
      }
      return false;
    }

    bool przesunieto_okno = true;
    while (przesunieto_okno) {
      przesunieto_okno = false;
      uint32_t czas_sekcji = najblizszyWolnyCzasSekcji(cel, pociag.id, czas, czas_przejazdu);
      if (czas_sekcji == UINT32_MAX) return false;
      if (czas_sekcji > czas) {
        czas = czas_sekcji;
        przesunieto_okno = true;
      }
      for (const auto& ustawienie : polaczenie->wymagane_zwrotnice) {
        uint32_t czas_zwrotnicy = najblizszyWolnyCzasZwrotnicy(
            ustawienie.id_zwrotnicy, pociag.id, czas, czas_przejazdu);
        if (czas_zwrotnicy == UINT32_MAX) return false;
        if (czas_zwrotnicy > czas) {
          czas = czas_zwrotnicy;
          przesunieto_okno = true;
        }
      }
    }
    if (czas == UINT32_MAX || czas > aktualny_czas_symulacji + HORYZONT_PLANOWANIA_S) {
      if (DEBUG) {
        Serial.printf("[SIPP] Krawedz %u -> %u poza horyzontem: t=%lu, teraz=%lu\n",
                      zrodlo, cel, (unsigned long)czas, (unsigned long)aktualny_czas_symulacji);
      }
      return false;
    }

    uint32_t koniec_przejazdu = czas + czas_przejazdu;
    uint32_t koniec = koniec_przejazdu;

    if (indeks == trasa.size() - 1 && pociag.indeks_nastepnego_przystanku < pociag.rozklad.size()) {
      const Rozklad& przystanek = pociag.rozklad[pociag.indeks_nastepnego_przystanku];
      koniec += przystanek.czas_postoju;
      if (przystanek.czas_odjazdu > koniec) koniec = przystanek.czas_odjazdu;
    }
    plan.push_back({zrodlo, cel, czas, koniec_przejazdu, koniec, polaczenie});
    czas = koniec;
  }

  for (const auto& krawedz : plan) {
    mapa_sekcji[krawedz.cel].rezerwacje.push_back(
        {pociag.id, krawedz.czas_start, krawedz.czas_koniec_sekcji, krawedz.zrodlo, krawedz.cel});
    for (const auto& ustawienie : krawedz.polaczenie->wymagane_zwrotnice) {
      mapa_zwrotnic[ustawienie.id_zwrotnicy].rezerwacje.push_back(
          {pociag.id, krawedz.czas_start, krawedz.czas_koniec_przejazdu, krawedz.zrodlo, krawedz.cel});
    }
  }
  return true;
}

Sygnal sygnalDlaZajetosci(uint16_t sekcja_zrodlowa, uint16_t sekcja_docelowa) {
  const Sekcja& zrodlowa = mapa_sekcji[sekcja_zrodlowa];
  const Sekcja& docelowa = mapa_sekcji[sekcja_docelowa];

  // Podczas przejazdu sklad przez chwile zajmuje obie sekcje: czoło jest
  // juz w docelowej, a ogon nadal trzyma zrodlowa. Semafor za tym samym
  // pociagiem musi byc zolty az do EVT:SEK_WYJ z sekcji zrodlowej.
  if (zrodlowa.zajeta && docelowa.zajeta &&
      zrodlowa.pociag_id != 0 && zrodlowa.pociag_id == docelowa.pociag_id) {
    auto it_pociagu = mapa_pociagow.find(zrodlowa.pociag_id);
    if (it_pociagu != mapa_pociagow.end() &&
        it_pociagu->second.czolo == sekcja_docelowa) {
      return Sygnal::ZOLTY;
    }
  }

  // Wjazd na zajeta sekcje za odjezdzajacym skladem jest zolty. Pozwala to
  // wyhamowac za poprzednim pociagiem, lecz zabrania jazdy z pelna predkoscia.
  if (docelowa.zajeta && docelowa.pociag_id != 0) {
    auto it_pociagu = mapa_pociagow.find(docelowa.pociag_id);
    if (it_pociagu == mapa_pociagow.end() || it_pociagu->second.czolo == sekcja_docelowa ||
        it_pociagu->second.czolo == sekcja_zrodlowa) {
      return Sygnal::CZERWONY;
    }
    return Sygnal::ZOLTY;
  }

  // Pociag znajdujacy sie w sekcji zrodlowej porusza sie poza ta krawedzia.
  // Sygnał prowadzacy wstecz (lub do innej niz czolo sekcji) musi pozostac czerwony.
  if (zrodlowa.zajeta && zrodlowa.pociag_id != 0) {
    auto it_pociagu = mapa_pociagow.find(zrodlowa.pociag_id);
    if (it_pociagu == mapa_pociagow.end()) {
      return Sygnal::CZERWONY;
    }

    // Czoło w sekcji źródłowej oznacza normalny wyjazd. Dopuszczamy tylko
    // krawędź już przydzieloną temu pociągowi przez planner SIPP.
    if (it_pociagu->second.czolo == sekcja_zrodlowa) {
      return pociagMaRezerwacjePrzejazdu(
          zrodlowa.pociag_id, sekcja_zrodlowa, sekcja_docelowa)
          ? Sygnal::ZIELONY
          : Sygnal::CZERWONY;
    }

    if (it_pociagu->second.czolo != sekcja_docelowa) return Sygnal::CZERWONY;
  }

  // Semafor bez pociagu w sekcji zrodlowej nie otwiera sie "na zapas".
  // Przejazd dostaje sygnal dopiero po potwierdzeniu aktywnej rezerwacji.
  return Sygnal::CZERWONY;
}

bool pociagMaRezerwacjePrzejazdu(
    uint16_t id_pociagu,
    uint16_t sekcja_zrodlowa,
    uint16_t sekcja_docelowa) {
  auto it_docelowej = mapa_sekcji.find(sekcja_docelowa);
  if (it_docelowej == mapa_sekcji.end()) return false;
  for (const auto& rezerwacja : it_docelowej->second.rezerwacje) {
    if (rezerwacja.id_pociagu == id_pociagu &&
        rezerwacja.sekcja_zrodlowa == sekcja_zrodlowa &&
        rezerwacja.sekcja_docelowa == sekcja_docelowa &&
        rezerwacja.czas_start <= aktualny_czas_symulacji &&
        aktualny_czas_symulacji < rezerwacja.czas_koniec) {
      return true;
    }
  }
  return false;
}

bool zwrotnicaJestWStrefieInnegoPociagu(uint16_t id_zwrotnicy, uint16_t id_pociagu) {
  auto it_zwrotnicy = mapa_zwrotnic.find(id_zwrotnicy);
  if (it_zwrotnicy == mapa_zwrotnic.end()) return true;

  // Sama możliwość przejazdu przez zwrotnicę z sąsiedniej sekcji nie jest
  // zajętością. Blokadę utrzymuje wyłącznie rezerwacja aktywna w bieżącym
  // czasie, należąca do innego pociągu.
  for (const auto& rezerwacja : it_zwrotnicy->second.rezerwacje) {
    if (rezerwacja.id_pociagu != id_pociagu &&
        rezerwacja.czas_start <= aktualny_czas_symulacji &&
        rezerwacja.czas_koniec > aktualny_czas_symulacji) {
      return true;
    }
  }
  return false;
}

bool wszystkieRozkladyZaladowane() {
  if (oczekiwana_liczba_pociagow == 0 ||
      mapa_pociagow.size() < oczekiwana_liczba_pociagow) {
    return false;
  }
  for (const auto& [id_pociagu, pociag] : mapa_pociagow) {
    if (!pociag.rozklad_zaladowany) return false;
  }
  return true;
}

void ustawSygnaIStanZwrotnicSIPP() {
  std::map<uint16_t, Sygnal> sygnaly_docelowe;

  for (const auto& [id_sekcji, sekcja] : mapa_sekcji) {
    for (const auto& polaczenie : sekcja.polaczenia) {
      auto it_docelowej = mapa_sekcji.find(polaczenie.id_sekcji_docelowej);
      if (it_docelowej == mapa_sekcji.end()) continue;

      const Sekcja& docelowa = it_docelowej->second;
      Sygnal sygnal = sygnalDlaZajetosci(id_sekcji, polaczenie.id_sekcji_docelowej);
      if (sygnal != Sygnal::CZERWONY) {
        for (const auto& rezerwacja : docelowa.rezerwacje) {
          const Sekcja& zrodlowa = mapa_sekcji[id_sekcji];
          if (zrodlowa.zajeta && zrodlowa.pociag_id == rezerwacja.id_pociagu &&
              rezerwacja.sekcja_zrodlowa == id_sekcji &&
              rezerwacja.sekcja_docelowa == polaczenie.id_sekcji_docelowej) {
            continue;
          }
            if (rezerwacja.czas_start <= aktualny_czas_symulacji &&
              rezerwacja.czas_koniec + ZAPAS_REZERWACJI_S > aktualny_czas_symulacji &&
              rezerwacja.sekcja_zrodlowa != id_sekcji) {
            sygnal = Sygnal::CZERWONY;
            break;
          }
          if (rezerwacja.czas_start <= aktualny_czas_symulacji + HORYZONT_PLANOWANIA_S) {
            sygnal = Sygnal::ZOLTY;
          }
        }
      }

      for (const auto& ustawienie : polaczenie.wymagane_zwrotnice) {
        auto it_zwrotnicy = mapa_zwrotnic.find(ustawienie.id_zwrotnicy);
        if (it_zwrotnicy != mapa_zwrotnic.end() &&
            it_zwrotnicy->second.pozycja != ustawienie.wymagany_zwrot) {
          // Bez potwierdzonej nastawy nie wolno otworzyć sygnału prowadzącego
          // przez zwrotnicę; zapobiega to wjazdowi na niezgodną gałąź.
          sygnal = Sygnal::CZERWONY;
        }
        if (it_zwrotnicy != mapa_zwrotnic.end() && it_zwrotnicy->second.pozycja == Zwrot::MINUS && sygnal == Sygnal::ZIELONY) {
          sygnal = Sygnal::ZOLTY;
        }
        if (it_zwrotnicy != mapa_zwrotnic.end()) {
          for (const auto& rezerwacja : it_zwrotnicy->second.rezerwacje) {
            if (rezerwacja.czas_start <= aktualny_czas_symulacji &&
              rezerwacja.czas_koniec + ZAPAS_REZERWACJI_S > aktualny_czas_symulacji &&
                rezerwacja.sekcja_zrodlowa != id_sekcji) {
              sygnal = Sygnal::CZERWONY;
              break;
            }
          }
        }
      }

      auto it_docelowego = sygnaly_docelowe.find(polaczenie.id_semafora);
      if (it_docelowego == sygnaly_docelowe.end() || sygnal > it_docelowego->second) {
        sygnaly_docelowe[polaczenie.id_semafora] = sygnal;
      }
    }
  }

  for (const auto& [id_semafora, sygnal] : sygnaly_docelowe) {
    auto it_semafora = mapa_semaforow.find(id_semafora);
    if (it_semafora == mapa_semaforow.end() || it_semafora->second.sygnal == Sygnal::SZ) continue;
    if (it_semafora->second.sygnal != sygnal) {
      it_semafora->second.sygnal = sygnal;
      ustawSygnal(id_semafora, sygnal == Sygnal::CZERWONY ? "CZE" : sygnal == Sygnal::ZOLTY ? "ZOL" : "ZIE");
    }
  }
}

void przeliczSterowanieSIPP() {
  if (!wszystkieRozkladyZaladowane()) return;

  for (auto& [id, sekcja] : mapa_sekcji) sekcja.rezerwacje.clear();
  for (auto& [id, zwrotnica] : mapa_zwrotnic) zwrotnica.rezerwacje.clear();

  std::vector<uint16_t> kolejnosc;
  for (const auto& [id, pociag] : mapa_pociagow) {
    if (!pociag.awaria && pociag.rozklad_zaladowany &&
        pociag.indeks_nastepnego_przystanku < pociag.rozklad.size() &&
      !pociag.na_postoju_stacyjnym) {
      kolejnosc.push_back(id);
    }
  }
  std::sort(kolejnosc.begin(), kolejnosc.end(), [](uint16_t a, uint16_t b) {
    return priorytetPociagu(mapa_pociagow[a]) > priorytetPociagu(mapa_pociagow[b]);
  });

  // EVT:SEK_WJA moze nadejsc przed odpowiedzia DAT:ROZ. Do czasu wczytania
  // rozkladu nie zmieniaj semaforow ani limitow, aby nie zaplanowac stopu
  // na podstawie niekompletnego stanu sterownika.
  if (kolejnosc.empty()) return;

  for (uint16_t id_pociagu : kolejnosc) {
    Pociag& pociag = mapa_pociagow[id_pociagu];
    std::vector<uint16_t> trasa;
    bool znaleziona_trasa = znajdzTraseDoPeronu(pociag, trasa);
    bool zarezerwowano = znaleziona_trasa && rezerwujPrzejazdSIPP(pociag, trasa);
    if (!zarezerwowano) {
      if (DEBUG) {
        Serial.print("[SIPP] Brak rezerwacji dla P");
        Serial.print(id_pociagu);
        Serial.print(" z sekcji ");
        Serial.print(pociag.czolo);
        Serial.print(" do ");
        Serial.println(pociag.rozklad[pociag.indeks_nastepnego_przystanku].stacja_docelowa);
        if (!znaleziona_trasa) Serial.println("[SIPP] Nie znaleziono trasy do peronu.");
      }
      // Brak planu nie moze trwale unieruchamiac pociagu. Bezpieczenstwo
      // zapewnia czerwony semafor, a usuniecie limitu pozwala automatyce
      // wznowic ruch od razu po kolejnym poprawnym przeliczeniu SIPP.
      wylaczLimitPredkosci(id_pociagu);
      continue;
    }

    if (trasa.size() > 1 &&
      najblizszyWolnyCzasSekcji(
        trasa[1], id_pociagu, aktualny_czas_symulacji,
        obliczCzasPrzejazdu(id_pociagu, trasa[0], trasa[1])) > aktualny_czas_symulacji) {
      ustawLimitPredkosci(id_pociagu, 10);
    } else {
      wylaczLimitPredkosci(id_pociagu);
    }

    // Ustawiamy tylko zwrotnice najbliższej krawędzi. Nastawy dalszej trasy
    // są rezerwowane, ale nie mogą zmienić położenia pod innym pociągiem.
    if (trasa.size() > 1) {
      const PolaczenieSekcji* polaczenie = znajdzPolaczenie(trasa[0], trasa[1]);
      if (polaczenie != nullptr) {
        for (const auto& ustawienie : polaczenie->wymagane_zwrotnice) {
          auto it_zwrotnicy = mapa_zwrotnic.find(ustawienie.id_zwrotnicy);
          if (it_zwrotnicy != mapa_zwrotnic.end() &&
              it_zwrotnicy->second.pozycja != ustawienie.wymagany_zwrot &&
              !zwrotnicaJestWStrefieInnegoPociagu(ustawienie.id_zwrotnicy, id_pociagu)) {
            przestawZwrotnice(
                ustawienie.id_zwrotnicy,
                ustawienie.wymagany_zwrot == Zwrot::PLUS ? "PLU" : "MIN");
          }
        }
      }
    }
  }

  // Zwrotnica bez rezerwacji nie jest potrzebna zadnej trasie i wraca do
  // bezpiecznej nastawy domyslnej PLUS.
  for (auto& [id_zwrotnicy, zwrotnica] : mapa_zwrotnic) {
    if (zwrotnica.rezerwacje.empty() && zwrotnica.pozycja != Zwrot::PLUS) {
      przestawZwrotnice(id_zwrotnicy, "PLU");
    }
  }

  ustawSygnaIStanZwrotnicSIPP();
}

void zatrzymajRuchWokolSekcji(uint16_t id_sekcji) {
  auto it = mapa_sekcji.find(id_sekcji);
  if (it == mapa_sekcji.end()) return;
  for (const auto& [id_pociagu, pociag] : mapa_pociagow) {
    if (pociag.czolo == id_sekcji || pociag.ogon == id_sekcji) ustawLimitPredkosci(id_pociagu, 0);
  }
  for (const auto& polaczenie : it->second.polaczenia) {
    ustawSygnal(polaczenie.id_semafora, "CZE");
  }
  for (const auto& [id_sasiedniej, sasiednia] : mapa_sekcji) {
    for (const auto& polaczenie : sasiednia.polaczenia) {
      if (polaczenie.id_sekcji_docelowej == id_sekcji) {
        ustawSygnal(polaczenie.id_semafora, "CZE");
      }
    }
  }
}

void sprawdzPrzekroczoneRezerwacje() {
  for (auto& [id_pociagu, pociag] : mapa_pociagow) {
    if (pociag.awaria || pociag.zatrzymany_na_czerwonym ||
      pociag.sekcja_z_terminem_wyjazdu == 0 ||
        aktualny_czas_symulacji <= pociag.termin_wyjazdu_z_sekcji + ZAPAS_REZERWACJI_S) {
      continue;
    }

    auto it_sekcji = mapa_sekcji.find(pociag.sekcja_z_terminem_wyjazdu);
    if (it_sekcji != mapa_sekcji.end() && it_sekcji->second.zajeta &&
        it_sekcji->second.pociag_id == id_pociagu) {
      pociag.awaria = true;
      ustawLimitPredkosci(id_pociagu, 0);
      zatrzymajRuchWokolSekcji(pociag.sekcja_z_terminem_wyjazdu);
      Serial.print("ALM:POC:");
      Serial.print(odwrotnieModyfikujId(id_pociagu, "P"));
      Serial.println(":PRZEKROCZONA_REZERWACJA");
    }
  }
}

void ustawSygnalyWedlugRegul() {
  ustawSygnaIStanZwrotnicSIPP();
}

void aktualizujStanySemaforow() {
  // Funkcja wysyła aktualne stany semaforów do symulatora
  for (const auto& [id, semafor] : mapa_semaforow) {
    String sygnalStr;
    switch (semafor.sygnal) {
      case Sygnal::CZERWONY: sygnalStr = "CZE"; break;
      case Sygnal::ZOLTY: sygnalStr = "ZOL"; break;
      case Sygnal::ZIELONY: sygnalStr = "ZIE"; break;
      case Sygnal::SZ: sygnalStr = "SZ"; break;
    }
    ustawSygnal(id, sygnalStr);
  }
}

bool rezerwujSekcjeWOknieCzasowym(uint16_t pociag_id, uint16_t sekcja_id, uint32_t czas_start, uint32_t czas_koniec) {
  // Funkcja rezerwuje sekcję dla pociągu w oknie czasowym (czas_start - czas_koniec)
  auto it = mapa_sekcji.find(sekcja_id);
  if (it != mapa_sekcji.end()) {
    Sekcja& sekcja = it->second;
    // Sprawdzamy, czy sekcja jest już zajęta lub zarezerwowana w tym czasie
    for (const auto& rezerwacja : sekcja.rezerwacje) {
      if ((czas_start < rezerwacja.czas_koniec) && (czas_koniec > rezerwacja.czas_start)) {
        // Konflikt czasowy z istniejącą rezerwacją
        if (DEBUG) {
          Serial.print("-> [ESP32 ERROR] Konflikt rezerwacji sekcji ");
          Serial.print(sekcja_id);
          Serial.print(" dla pociągu ");
          Serial.print(pociag_id);
          Serial.print(" w oknie czasowym: ");
          Serial.print(czas_start);
          Serial.print(" - ");
          Serial.println(czas_koniec);
        }
        return false; // Nie dokonujemy rezerwacji
      }
    }
    // Dodajemy rezerwację
    sekcja.rezerwacje.push_back({pociag_id, czas_start, czas_koniec, sekcja_id, sekcja_id});
    if (DEBUG) {
      Serial.print("-> [ESP32 INFO] Zarezerwowano sekcję ");
      Serial.print(sekcja_id);
      Serial.print(" dla pociągu ");
      Serial.print(pociag_id);
      Serial.print(" w oknie czasowym: ");
      Serial.print(czas_start);
      Serial.print(" - ");
      Serial.println(czas_koniec);
    }
  } else {
    if (DEBUG) {
      Serial.print("-> [ESP32 ERROR] Nieznana sekcja: ");
      Serial.println(sekcja_id);
    }
  }
  return true; // Rezerwacja udana
}

bool rezerwujZwrotniceDlaPociagu(uint16_t pociag_id, uint16_t sekcja_id, uint16_t sekcja_docelowa_id, uint32_t czas_start, uint32_t czas_koniec) {
  // Funkcja rezerwuje zwrotnice wymagane do przejazdu pomiędzy sekcjami w oknie czasowym (czas_start - czas_koniec)
  // Pobieramy wymagane zwrotnice dla połączenia i sprawdzamy, czy są już zarezerwowane w tym czasie
  auto it = mapa_sekcji.find(sekcja_id);
  if (it != mapa_sekcji.end()) {
    const Sekcja& sekcja = it->second;
    for (const auto& pol : sekcja.polaczenia) {
      if (pol.id_sekcji_docelowej == sekcja_docelowa_id) {
        for (const auto& zwrot : pol.wymagane_zwrotnice) {
          auto itZwrot = mapa_zwrotnic.find(zwrot.id_zwrotnicy);
          if (itZwrot != mapa_zwrotnic.end()) {
            Zwrotnica& zwrotnica = itZwrot->second;
            // Sprawdzamy, czy zwrotnica jest już zarezerwowana w tym czasie
            for (const auto& rezerwacja : zwrotnica.rezerwacje) {
              if ((czas_start < rezerwacja.czas_koniec) && (czas_koniec > rezerwacja.czas_start)) {
                // Konflikt czasowy z istniejącą rezerwacją
                if (DEBUG) {
                  Serial.print("-> [ESP32 ERROR] Konflikt rezerwacji zwrotnicy ");
                  Serial.print(zwrot.id_zwrotnicy);
                  Serial.print(" dla pociągu ");
                  Serial.print(pociag_id);
                  Serial.print(" w oknie czasowym: ");
                  Serial.print(czas_start);
                  Serial.print(" - ");
                  Serial.println(czas_koniec);
                }
                return false; // Nie dokonujemy rezerwacji
              }
            }
            // Dodajemy rezerwację
            zwrotnica.rezerwacje.push_back({pociag_id, czas_start, czas_koniec, sekcja_id, sekcja_docelowa_id});
            if (DEBUG) {
              Serial.print("-> [ESP32 INFO] Zarezerwowano zwrotnicę ");
              Serial.print(zwrot.id_zwrotnicy);
              Serial.print(" dla pociągu ");
              Serial.print(pociag_id);
              Serial.print(" w oknie czasowym: ");
              Serial.print(czas_start);
              Serial.print(" - ");
              Serial.println(czas_koniec);
            }
          }
        }
      }
    }
  }
  return true; // Rezerwacja udana
}

void zwolnijRezerwacjePociagu(uint16_t pociag_id) {
  // Funkcja zwalnia wszystkie rezerwacje sekcji i zwrotnic dla danego pociągu
  for (auto& [id, sekcja] : mapa_sekcji) {
    sekcja.rezerwacje.erase(
      std::remove_if(sekcja.rezerwacje.begin(), sekcja.rezerwacje.end(),
                     [pociag_id](const OknoCzasowe& r) { return r.id_pociagu == pociag_id; }),
      sekcja.rezerwacje.end());
  }
  for (auto& [id, zwrotnica] : mapa_zwrotnic) {
    zwrotnica.rezerwacje.erase(
      std::remove_if(zwrotnica.rezerwacje.begin(), zwrotnica.rezerwacje.end(),
                     [pociag_id](const OknoCzasowe& r) { return r.id_pociagu == pociag_id; }),
      zwrotnica.rezerwacje.end());
  }
  if (DEBUG) {
    Serial.print("-> [ESP32 INFO] Zwolniono wszystkie rezerwacje dla pociągu ");
    Serial.println(pociag_id);
  }
}

uint32_t obliczCzasPrzejazdu(uint16_t pociag_id, uint16_t sekcja_id, uint16_t sekcja_docelowa_id) {
  // W grafie SIPP wierzcholkami sa semafory graniczne. Przejscie przez
  // krawedz obejmuje dlugosc sekcji oraz pola zwrotnic potrzebne na wyjezdzie.
  // Wynik jest zaokraglany w gore, aby nie utworzyc zbyt krotkiego interwalu.
  auto itPociag = mapa_pociagow.find(pociag_id);
  auto itSekcja = mapa_sekcji.find(sekcja_id);
  auto itSekcjaDocelowa = mapa_sekcji.find(sekcja_docelowa_id);
  if (itPociag == mapa_pociagow.end() || itSekcja == mapa_sekcji.end() || itSekcjaDocelowa == mapa_sekcji.end()) {
    if (DEBUG) {
      Serial.printf("[SIPP] Brak danych dla czasu %u -> %u: p=%d, z=%d, d=%d\n",
                    sekcja_id, sekcja_docelowa_id,
                    itPociag != mapa_pociagow.end(), itSekcja != mapa_sekcji.end(),
                    itSekcjaDocelowa != mapa_sekcji.end());
    }
    return 0;
  }

  const PolaczenieSekcji* polaczenie = nullptr;
  for (const auto& kandydat : itSekcja->second.polaczenia) {
    if (kandydat.id_sekcji_docelowej == sekcja_docelowa_id) {
      polaczenie = &kandydat;
      break;
    }
  }
  if (polaczenie == nullptr || skala_w_metrach <= 0.0f || rozmiar_kafelka_w_px == 0) {
    if (DEBUG) {
      Serial.printf("[SIPP] Niepoprawne parametry %u -> %u: pol=%d, skala=%.3f, px=%u\n",
                    sekcja_id, sekcja_docelowa_id, polaczenie != nullptr,
                    skala_w_metrach, rozmiar_kafelka_w_px);
    }
    return 0;
  }

  const Pociag& pociag = itPociag->second;
  const float metry_na_piksel = skala_w_metrach / (float)rozmiar_kafelka_w_px;
  const float predkosc_planowania_pxs = pociag.predkosc_docelowa_pxs > 0.0f
      ? pociag.predkosc_docelowa_pxs
      : pociag.predkosc_max_pxs;
  const float predkosc_m_s = predkosc_planowania_pxs * metry_na_piksel;
  if (predkosc_m_s <= 0.0f) {
    if (DEBUG) {
      Serial.printf("[SIPP] Zerowa predkosc %u -> %u: v_plan=%.3f, m_px=%.3f\n",
                    sekcja_id, sekcja_docelowa_id, predkosc_planowania_pxs, metry_na_piksel);
    }
    return 0;
  }

  const uint32_t liczba_kafelkow =
      (uint32_t)itSekcja->second.dlugosc + polaczenie->liczba_kafelkow_zwrotnic;
  const float dystans_m = liczba_kafelkow * skala_w_metrach;
  if (dystans_m <= 0.0f) {
    if (DEBUG) {
      Serial.printf("[SIPP] Zerowy dystans %u -> %u: dlugosc=%lu, skala=%.3f\n",
                    sekcja_id, sekcja_docelowa_id, (unsigned long)liczba_kafelkow,
                    skala_w_metrach);
    }
    return 0;
  }
  const uint32_t czas_przejazdu = (uint32_t)ceilf(dystans_m / predkosc_m_s);
  return czas_przejazdu > 0 ? czas_przejazdu : 1;
}

