"""Test per indexing_rules — regole Antenati/FamilySearch (ed. 9 luglio 2024)."""
import indexing_rules as ir


class TestNormalizeMatchKey:
    def test_spazi_e_maiuscole(self):
        assert ir.normalize_match_key("  Rossi   Mario  ") == "rossi mario"

    def test_none_e_vuoto(self):
        assert ir.normalize_match_key(None) == ""
        assert ir.normalize_match_key("") == ""

    def test_trattino_tipografico_separatore(self):
        # em-dash con spazi → separatore (coerente con audit_cross_db)
        assert ir.normalize_match_key("  Gaiaschi — Luigi ") == "gaiaschi luigi"

    def test_apostrofo_mantenuto(self):
        # sez. 2.4.6: nessuno spazio attorno all'apostrofo, che resta
        assert ir.normalize_match_key("D'Azeglio") == "d'azeglio"

    def test_trattino_interno_mantenuto(self):
        assert ir.normalize_match_key("Jean-Marie") == "jean-marie"

    def test_punteggiatura_rimossa(self):
        assert ir.normalize_match_key("Rossi, Mario.") == "rossi mario"

    def test_accenti_preservati(self):
        # sez. 2.4.2: i segni diacritici sono fedeli all'originale
        assert ir.normalize_match_key("Nicolò") == "nicolò"

    def test_placeholder_vuoto(self):
        for p in ["N.N.", "Enne", "Nessun Nome", "sconosciuto", "-", "N/D"]:
            assert ir.normalize_match_key(p) == "", p


class TestIsEmptyValue:
    def test_veri(self):
        assert ir.is_empty_value("N.N.")
        assert ir.is_empty_value("  sconosciuto ")
        assert ir.is_empty_value(None)

    def test_falsi(self):
        assert not ir.is_empty_value("Rossi")


class TestStripTitles:
    def test_titolo_iniziale(self):
        # sez. 1.4.6: "signor Mario Rossi" → "Mario Rossi"
        assert ir.strip_titles("signor Mario Rossi") == "Mario Rossi"

    def test_don(self):
        assert ir.strip_titles("Don Giuseppe") == "Giuseppe"

    def test_senza_titolo(self):
        assert ir.strip_titles("Mario Rossi") == "Mario Rossi"

    def test_titolo_con_punto(self):
        assert ir.strip_titles("Sig. Rossi") == "Rossi"


class TestOrVariants:
    def test_espansione(self):
        # sez. 1.4.5
        assert ir.expand_or_variants("Giuseppe O Pino O il Magro") == [
            "Giuseppe", "Pino", "il Magro"
        ]

    def test_singola(self):
        assert ir.expand_or_variants("Marco Polo") == ["Marco Polo"]

    def test_fold_variants_chiavi(self):
        assert ir.fold_variants("Roselli O Rosselli") == ["roselli", "rosselli"]


class TestTitlecaseName:
    def test_apostrofo(self):
        # sez. 1.3.7: "D'amico" → "D'Amico"
        assert ir.titlecase_name("d'amico") == "D'Amico"

    def test_mc(self):
        assert ir.titlecase_name("mcgregor") == "McGregor"

    def test_preposizione(self):
        # le preposizioni del cognome restano maiuscole
        assert ir.titlecase_name("da vinci") == "Da Vinci"

    def test_trattino(self):
        assert ir.titlecase_name("jean-marie") == "Jean-Marie"


class TestCleanToponym:
    def test_frazione(self):
        # sez. 1.4.9.1
        assert ir.clean_toponym("frazione di Canneto") == "Canneto"

    def test_comune(self):
        assert ir.clean_toponym("comune di Milano") == "Milano"

    def test_eccezione_non_modificata(self):
        assert ir.clean_toponym("Città di Castello") == "Città di Castello"

    def test_toponimo_semplice(self):
        assert ir.clean_toponym("Trieste") == "Trieste"


class TestNormalizeAge:
    def test_anni_e_mesi_arrotonda(self):
        # sez. 1.4.11.1: "5 anni e 8 mesi" → 5
        assert ir.normalize_age("5 anni e 8 mesi") == 5

    def test_inferiore_a_un_anno(self):
        assert ir.normalize_age("8 mesi") == 0
        assert ir.normalize_age("inferiore a un anno") == 0

    def test_nato_morto(self):
        assert ir.normalize_age("nato morto") == 0

    def test_intervallo_prima_eta(self):
        # sez. 1.4.11.2: "65-67 anni" → 65
        assert ir.normalize_age("65-67 anni") == 65

    def test_circa(self):
        assert ir.normalize_age("circa 14 anni") == 14

    def test_piu_di(self):
        assert ir.normalize_age("più di 21 anni") == 21

    def test_assente(self):
        # sez. 1.4.11.6: età non espressa → None
        assert ir.normalize_age("") is None
        assert ir.normalize_age(None) is None
        assert ir.normalize_age("sconosciuta") is None
