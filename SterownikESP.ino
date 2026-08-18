#include <Arduino.h> // Wymagane dla ESP32 w Arduino IDE
#include <ArduinoJson.h> // Biblioteka do obsługi JSON (ArduinoJson v7) 
#include <map>
#include <list>
#include <vector>
#include <sstream>
#include <string>

// Ustawienie bufora RX na 4KB (wymagane dla dużych ramek EVT:MAPA_SEKCJI)
#define ROZMIAR_BUFORA_WEJSCIOWEGO 4096*4

enum class Sygnal : uint8_t { CZERWONY, ZOLTY, ZIELONY, SZ };
enum class Zwrot : bool { PLUS, MINUS };
enum class TypPociagu : uint8_t { TOWAROWY, OSOBOWY, POSPIESZNY, TECHNICZNY };
enum class Kierunek : uint8_t { POLNOC, POLUDNIE, WSCHOD, ZACHOD };

struct UstawienieZwrotnicy {
  uint16_t id_zwrotnicy;
  Zwrot wymagany_zwrot;
};

struct PolaczenieSekcji {
  uint16_t id_sekcji_docelowej;
  uint16_t id_semafora;
  std::vector<UstawienieZwrotnicy> wymagane_zwrotnice;
};

struct Sekcja {
  uint16_t id;
  bool zajeta;
  uint16_t pociag_id;
  std::vector<PolaczenieSekcji> polaczenia;
  uint8_t dlugosc;
};

struct Zwrotnica {
  uint16_t id;
  Zwrot pozycja;
  bool blokada;
  bool awaria;
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
  uint8_t predkosc_docelowa;
  uint8_t predkosc_aktualna;
  uint8_t predkosc_kmh;
  Kierunek kierunek; // 0 = północ, 1 = południe, 2 = wschód, 3 = zachód
  TypPociagu typ;
  uint16_t czolo; // ID sekcji, w której znajduje się czoło
  uint16_t ogon; // ID sekcji, w której znajduje się ogon
  uint16_t czas_postoju; // w sekundach
  bool przekroczenie_czerwonego; // czy pociąg przekroczył czerwone światło
  std::vector<Rozklad> rozklad;
};

std::map<uint16_t, Sekcja> mapa_sekcji;
std::map<uint16_t, Zwrotnica> mapa_zwrotnic;
std::map<uint16_t, Semafor> mapa_semaforow;
std::map<uint16_t, Pociag> mapa_pociagow;

uint32_t aktualny_czas_symulacji = 0; // w sekundach od początku symulacji przesunięte o czas startu symulacji

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
uint32_t konwertujCzasNaSekundy(const String& czasStr) {
  int godziny = 0, minuty = 0, sekundy = 0;
  sscanf(czasStr.c_str(), "%d:%d:%d", &godziny, &minuty, &sekundy);
  return godziny * 3600 + minuty * 60 + sekundy;
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

  // Testowe wysłanie zapytania o stan i mapę sekcji do Pythona po starcie
  Serial.println("SNP");
}

void loop() {
  // Nieblokujący odczyt linii ze strumienia
  if (Serial.available() > 0) {
    String linia = Serial.readStringUntil('\n');
    linia.trim(); // Usuwamy \r i ewentualne spakowane spacje

    if (linia.length() > 0) {
      przetworzLinie(linia);
    }
  }
  
  // TUTAJ: Twoja logika sterująca.
}

/**
 * Glowna funkcja parsowania odebranej ramki tekstowej z Pythona
 */
void przetworzLinie(String linia) {
  int pierwszyDwukropek = linia.indexOf(':');
  
  if (pierwszyDwukropek == -1) {
    // Ramka bez dwukropka (np. sam tekst)
    return;
  }

  String typ = linia.substring(0, pierwszyDwukropek);
  String tresc = linia.substring(pierwszyDwukropek + 1);

  // 1. ZDARZENIA ASYNCHRONICZNE (EVT)
  if (typ == "EVT") {
    if (tresc.startsWith("MAPA_SEKCJI:")) {
      String jsonMap = tresc.substring(12); // Odtcinamy prefiks "MAPA_SEKCJI:"
      obsluzMapeSekcji(jsonMap);
    } 
    else if (tresc.startsWith("SEK_WJA:")) {
      // Format: EVT:SEK_WJA:pociag_id:sekcja_id:czas
      // jeśli pociąg nie istnieje w mapie_pociagow, to go rejestrujemy
      int idx1 = tresc.indexOf(':', 8);
      int idx2 = tresc.indexOf(':', idx1 + 1);
      if (idx1 != -1 && idx2 != -1) {
        uint16_t pociag_id = modyfikujId(tresc.substring(8, idx1).c_str());
        uint16_t sekcja_id = modyfikujId(tresc.substring(idx1 + 1, idx2).c_str());
        uint32_t czas = konwertujCzasNaSekundy(tresc.substring(idx2 + 1));
        wjazdDoSekcji(pociag_id, sekcja_id, czas);
      }
      Serial.print("-> [ESP32 INFO] Pociąg wjechał do sekcji: ");
      Serial.println(tresc);
    }
    else if (tresc.startsWith("AWR:")) {
      // Format: EVT:AWR:zwrotnica_id:pociag_id:czas
      Serial.print("-> [ESP32 ALARM] Rozprucie zwrotnicy! ");
      Serial.println(tresc);
    }
    else {
      // Inne zdarzenia: SYG, ZWR, EST, STP, PRC itp.
      Serial.print("-> [ESP32 EVT]: ");
      Serial.println(tresc);
    }
  }
  // 2. DANE W ODPOWIEDZI NA ZAPYTANIE (DAT)
  else if (typ == "DAT") {
    obsluzOdpowiedzDAT(tresc);
  }
  // 3. POTWIERDZENIA WYKONANIA KOMENDY (OK)
  else if (typ == "OK") {
    Serial.print("-> [ESP32 OK]: Potwierdzono komendę: ");
    Serial.println(tresc);
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
    s.zajeta = false;
    s.pociag_id = 0;

    // 1. Parsowanie semaforów granicznych
    JsonArray semGraniczne = sekcjaJson["graniczne_semafory"].as<JsonArray>();
    for (JsonVariant semVar : semGraniczne) {
      uint8_t semId = modyfikujId(semVar.as<const char*>());
      //s.graniczne_semafory.push_back(semId);

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
    // 3. Rejestracja stacji (jeśli jeszcze nie ma na liście)
    const char* stacjaNazwa = sekcjaJson["stacja"]["nazwa"] | "";
    if (strlen(stacjaNazwa) > 0) {
      String stacjaStr(stacjaNazwa);
      if (std::find(Stacje.begin(), Stacje.end(), stacjaStr) == Stacje.end()) {
        Stacje.push_back(stacjaStr);
      }
    }

    // Zapis gotowej sekcji do mapy
    mapa_sekcji[s.id] = s;
  }
  
  poprawZwrotnice(); // Poprawiamy stan zwrotnic po załadowaniu mapy

  // Potwierdzenie załadowania do RAM
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
    // Format: POC:id:pred_akt:pred_doc:pred_kmh:typ:kier:czolo:ogon:sekcja...
    Serial.print("Dane pociągu: ");
    Serial.println(dane);
    // aktualizacja wszystkich danych pociągu w mapie_pociagow na podstawie odebranej ramki
    dane.trim();
    dane.replace(":", " "); // Zamieniamy dwukropki na spacje dla łatwiejszego parsowania
    std::istringstream iss(dane.c_str());
    uint16_t pociag_id;
    iss >> pociag_id;
    auto it = mapa_pociagow.find(pociag_id);
    if (it != mapa_pociagow.end()) {
      Pociag& pociag = it->second;
      int typ1int;
      int typ2int;
      iss >> pociag.predkosc_aktualna >> pociag.predkosc_docelowa >> pociag.predkosc_kmh >> typ1int >> typ2int >> pociag.czolo >> pociag.ogon >> pociag.czas_postoju >> pociag.przekroczenie_czerwonego;
      pociag.typ = static_cast<TypPociagu>(typ1int);
      pociag.kierunek = static_cast<Kierunek>(typ2int);
    }
  } 
  else if (komenda == "ZWR") {
    // Format: ZWR:id:pozycja:stan_awaryjny
    Serial.print("Stan zwrotnicy: ");
    Serial.println(dane);
  }
  else if (komenda == "SYG") {
    // Format: SYG:id:sygnal
    Serial.print("Stan sygnalizatora: ");
    Serial.println(dane);
  }
  else if (komenda == "SNP") {
    // Format: SNP:HH:MM:SS:liczba_pociagow:liczba_semaforow:liczba_zwrotnic:liczba_sekcji
    Serial.print("Stan symulatora: ");
    Serial.println(dane);
  }
  else if (komenda == "ROZ") {
    // Format: ROZ:id:stacja_docelowa:czas_przyjazdu:czas_odjazdu:czas_postoju
    // Aktualizacja rozkładu pociągu w mapie_pociagow
    int idx1 = dane.indexOf(':');
    if (idx1 != -1) {
      uint16_t pociag_id = modyfikujId(dane.substring(0, idx1).c_str());
      auto it = mapa_pociagow.find(pociag_id);
      if (it != mapa_pociagow.end()) {
        Pociag& pociag = it->second;
        String rozkladStr = dane.substring(idx1 + 1);
        rozkladStr.trim();
        rozkladStr.replace(":", " "); // Zamieniamy dwukropki na spacje dla łatwiejszego parsowania
        std::istringstream iss(rozkladStr.c_str());
        Rozklad r;
        std::string stacjaDocelowaStr, czasPrzyjazduStr, czasOdjazduStr;
        iss >> stacjaDocelowaStr >> czasPrzyjazduStr >> czasOdjazduStr >> r.czas_postoju;
        r.stacja_docelowa = stacjaDocelowaStr.c_str();
        r.czas_przyjazdu = konwertujCzasNaSekundy(czasPrzyjazduStr.c_str());
        r.czas_odjazdu = konwertujCzasNaSekundy(czasOdjazduStr.c_str());
        pociag.rozklad.push_back(r);
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
    p.predkosc_docelowa = 0;
    p.predkosc_aktualna = 0;
    p.kierunek = Kierunek::ZACHOD; // Domyślny kierunek
    p.typ = TypPociagu::OSOBOWY; // Domyślny typ
    p.czolo = sekcja_id; // Czoło wjechało
    p.ogon = sekcja_id; // Ostatnio wjechana sekcja
    mapa_pociagow[pociag_id] = p;
    pytaj_o_pociag(pociag_id); // Zapytanie o szczegóły pociągu
    Serial.print("-> [ESP32 INFO] Zarejestrowano nowy pociąg o ID: ");
    Serial.println(pociag_id);
  }
  // dodanie pociągu do sekcji
  auto obiekt = mapa_sekcji.find(sekcja_id);
  if (obiekt != mapa_sekcji.end()) {
    Sekcja& sekcja = obiekt->second;
    sekcja.zajeta = true;
    sekcja.pociag_id = pociag_id;
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

// --- FUNKCJE POMOCNICZE DO WYSYŁANIA KOMEND Z ESP32 DO PYTHONA ---

void przestawZwrotnice(String id, String pozycja) {
  // Wysyła np. ZWR:Z01:PLU
  Serial.print("ZWR:");
  Serial.print(id);
  Serial.print(":");
  Serial.println(pozycja);
}

void ustawSygnal(String id, String sygnal) {
  // Wysyła np. SYG:S01:ZIE
  Serial.print("SYG:");
  Serial.print(id);
  Serial.print(":");
  Serial.println(sygnal);
}

void pytaj_o_pociag(uint16_t pociag_id) {
  Serial.print("POC:");
  String idStr = odwrotnieModyfikujId(pociag_id, "P");
  Serial.println(idStr);
}

void pytaj_o_semafor(uint16_t semafor_id) {
  Serial.print("SYG:");
  Serial.println(semafor_id);
}

void pytaj_o_zwrotnice(uint16_t zwrotnica_id) {
  Serial.print("ZWR:");
  Serial.println(zwrotnica_id);
}

void pytaj_o_sekcje(uint16_t sekcja_id) {
  Serial.print("SEK:");
  Serial.println(sekcja_id);
}

void pytaj_o_czas_symulacji() {
  Serial.println("PING");
}

void pytaj_o_rozklad_pociagu(uint16_t pociag_id) {
  Serial.print("ROZ:");
  Serial.println(pociag_id);
}