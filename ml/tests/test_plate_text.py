import pytest

from anpr_ml.plate_text import best_plate, parse_plate


class TestLecturasLimpias:
    @pytest.mark.parametrize(
        ("lectura", "esperada"),
        [
            ("CUB-604", "CUB-604"),
            ("CUB604", "CUB-604"),  # el bug del legacy: 6 chars se descartaban
            ("cub-604", "CUB-604"),
            ("CUB 604", "CUB-604"),
            (" CUB-604 ", "CUB-604"),
            ("C U B 6 0 4", "CUB-604"),
            ("V1A-882", "V1A-882"),  # 2.º carácter numérico, válido en Perú
        ],
    )
    def test_interpreta(self, lectura, esperada):
        c = parse_plate(lectura)
        assert c.valid and c.plate == esperada

    def test_sin_guion_no_se_descarta(self):
        """El filtro `^.{7}$` del legacy tiraba esta placa correcta."""
        assert parse_plate("ABC123").plate == "ABC-123"


class TestCorreccionPosicional:
    @pytest.mark.parametrize(
        ("lectura", "esperada", "n_fixes"),
        [
            ("CUB-6O4", "CUB-604", 1),  # O en zona de dígitos
            ("CUB-6S4", "CUB-654", 1),  # S -> 5
            ("CUB-GO4", "CUB-604", 2),  # G -> 6 y O -> 0
            ("CUB-8O4", "CUB-804", 1),  # B -> 8 solo en zona de dígitos
        ],
    )
    def test_corrige_por_posicion(self, lectura, esperada, n_fixes):
        c = parse_plate(lectura)
        assert c.valid and c.plate == esperada
        assert len(c.corrections) == n_fixes
        assert c.was_corrected

    def test_no_toca_lo_que_ya_es_valido(self):
        c = parse_plate("CUB-604")
        assert c.valid and not c.was_corrected

    def test_no_corrige_letras_en_zona_de_letras(self):
        """Una B en posición 3 es legítima; no debe volverse 8."""
        c = parse_plate("CUB-123")
        assert c.plate == "CUB-123" and not c.was_corrected


class TestLecturasFallidas:
    @pytest.mark.parametrize("mala", ["", "AB", "ABCDEFGH", "12", "@@@@@@", "ABCD1234"])
    def test_devuelve_invalida_sin_lanzar(self, mala):
        c = parse_plate(mala)
        assert not c.valid and c.plate is None

    def test_conserva_el_raw_para_auditar(self):
        """
        El legacy devolvía un respaldo que el llamador siempre descartaba, así
        que los fallos del OCR se perdían y no había forma de medir la precisión.
        """
        c = parse_plate("XY")
        assert c.raw == "XY"

    def test_seis_digitos_no_es_placa(self):
        assert not parse_plate("123456").valid


class TestBestPlate:
    def test_prefiere_valida_sobre_invalida(self):
        r = best_plate([("XX", 0.99), ("CUB-604", 0.60)])
        assert r is not None and r.plate == "CUB-604"

    def test_prefiere_sin_correcciones_aunque_tenga_menos_confianza(self):
        """Una corrección posicional es una conjetura; ante la duda, la limpia."""
        r = best_plate([("CUB-6O4", 0.95), ("CUB-604", 0.80)])
        assert r is not None and not r.was_corrected

    def test_entre_iguales_gana_la_de_mas_confianza(self):
        r = best_plate([("ABC-111", 0.70), ("XYZ-222", 0.90)])
        assert r is not None and r.plate == "XYZ-222"

    def test_sin_lecturas_devuelve_none(self):
        assert best_plate([]) is None

    def test_todas_invalidas_devuelve_la_mejor_para_registrar(self):
        r = best_plate([("XX", 0.3), ("YYY", 0.8)])
        assert r is not None and not r.valid and r.raw == "YYY"


class TestSeguridad:
    """
    Reglas que impiden inventar una placa a partir de una lectura mala. Importan
    porque esto gobierna una puerta: una placa inventada que coincida por azar
    con la lista blanca abriría al vehículo equivocado.
    """

    def test_todo_digitos_no_es_placa(self):
        """Toda placa peruana empieza por letra; 6 dígitos son otra cosa."""
        c = parse_plate("123456")
        assert not c.valid, f"inventó {c.plate} a partir de seis dígitos"

    def test_rechaza_demasiadas_correcciones(self):
        """Con más de 2 conjeturas, la placa es más invención que lectura."""
        # G->6, O->0, S->5  =  3 conjeturas
        c = parse_plate("0UB-GOS")
        assert not c.valid
        assert len(c.corrections) > 2

    def test_dos_correcciones_siguen_siendo_aceptables(self):
        c = parse_plate("CUB-GO4")
        assert c.valid and len(c.corrections) == 2

    def test_primera_posicion_no_se_corrige(self):
        """Un dígito inicial ya no se convierte en letra: queda como no legible."""
        c = parse_plate("0UB-604")
        assert not c.valid and not c.was_corrected

    @pytest.mark.parametrize("lectura", ["12E274", "17P-632", "1SY-654", "13F-189"])
    def test_casos_reales_que_la_correccion_inventaba(self, lectura):
        """
        Lecturas reales de la prueba visual. Las placas eran T2E-274, T7P-632,
        TSY-654 y T3F-189: la "T" con la barra tapada se leía "1", y la antigua
        corrección 1->I fabricaba placas inexistentes marcadas como válidas.
        """
        c = parse_plate(lectura)
        assert not c.valid
        assert c.raw == lectura
