from pathlib import Path

from app.ai.validacion_recetas import auditar_archivos, auditar_carpeta, validar_listado

REPO_ROOT = Path(__file__).resolve().parents[2]
RECETAS_DIR = REPO_ROOT / "docs" / "Recetas"


# --- el defecto real #1: PLAN_ASISTENTE_IA.md seccion 5 --------------------


def test_detecta_el_defecto_real_de_recetashd():
    # RecetasHD/001789002323.{15,17,19}.def.txt: la .17 tiene un digito
    # menos en #Descripcion que las otras dos variantes del mismo sellado.
    hallazgos = auditar_carpeta(RECETAS_DIR / "RecetasHD")
    de_esta_regla = [h for h in hallazgos if h.regla == "descripcion_inconsistente_entre_variantes"]
    assert de_esta_regla, "no se detecto el defecto real conocido de RecetasHD"
    archivos_marcados = {h.archivo for h in de_esta_regla}
    assert "001789002323.17.def.txt" in archivos_marcados


def test_detecta_el_defecto_real_de_recetasgps2_obsoletos():
    # RecetasGPS2/Obsoletos/004981008611.20.def.txt: #Codigo no coincide con
    # el nombre del archivo. Esta carpeta esta fuera del alcance normal de
    # auditar_carpeta() (solo mira el nivel superior, como cargar_catalogo),
    # pero la regla tiene que cazarlo si se la apunta directo.
    hallazgos = auditar_carpeta(RECETAS_DIR / "RecetasGPS2" / "Obsoletos")
    de_esta_regla = [h for h in hallazgos if h.regla == "codigo_no_coincide_con_archivo"]
    assert any(h.archivo == "004981008611.20.def.txt" for h in de_esta_regla)


def test_recetasgps1_no_tiene_hallazgos_conocidos():
    # control: un area sin defectos documentados no debe generar ruido.
    hallazgos = auditar_carpeta(RECETAS_DIR / "RecetasGPS1")
    assert hallazgos == []


# --- auditar_archivos(): reglas en aislamiento ------------------------------


def _archivo(codigo: str, descripcion: str, tep: str, sufijo: str = "15") -> str:
    return (
        f"#Codigo;{codigo}\n"
        f"#Operacion;{sufijo}\n"
        f"#Descripcion;{descripcion}\n"
        "\n"
        "* #Maquina;<idMaquinas>;<default>;<GPH>;<TEP>;<MUL>;<DIV>\n"
        f"#Maquina;1200001;True;;{tep};1;1\n"
    )


def test_codigo_no_coincide_con_archivo():
    archivos = {"111.15.def.txt": _archivo("222", "999", "15.00")}
    hallazgos = auditar_archivos(archivos)
    assert len(hallazgos) == 1
    assert hallazgos[0].regla == "codigo_no_coincide_con_archivo"
    assert "222" in hallazgos[0].mensaje and "111" in hallazgos[0].mensaje


def test_tep_no_coincide_con_sufijo():
    archivos = {"111.15.def.txt": _archivo("111", "999", "13.50", sufijo="15")}
    hallazgos = auditar_archivos(archivos)
    assert any(h.regla == "tep_no_coincide_con_sufijo" for h in hallazgos)


def test_tep_con_sufijo_decimal_no_da_falso_positivo():
    # sufijo "13.5" -> TEP "13.50" es correcto (startswith), no debe marcarse.
    archivos = {"111.13.5.def.txt": _archivo("111", "999", "13.50", sufijo="13.5")}
    hallazgos = auditar_archivos(archivos)
    assert hallazgos == []


def test_variantes_del_mismo_sellado_con_descripcion_consistente_no_marca():
    archivos = {
        "111.15.def.txt": _archivo("111", "999", "15.00", sufijo="15"),
        "111.17.def.txt": _archivo("111", "999", "17.00", sufijo="17"),
    }
    hallazgos = auditar_archivos(archivos)
    assert hallazgos == []


def test_variantes_del_mismo_sellado_con_descripcion_distinta_marca_ambas():
    archivos = {
        "111.15.def.txt": _archivo("111", "999", "15.00", sufijo="15"),
        "111.17.def.txt": _archivo("111", "998", "17.00", sufijo="17"),
    }
    hallazgos = [h for h in auditar_archivos(archivos) if h.regla == "descripcion_inconsistente_entre_variantes"]
    assert {h.archivo for h in hallazgos} == {"111.15.def.txt", "111.17.def.txt"}


def test_archivo_sin_problemas_no_genera_hallazgos():
    archivos = {"111.15.def.txt": _archivo("111", "999", "15.00")}
    assert auditar_archivos(archivos) == []


def test_nombre_de_archivo_no_estandar_se_ignora_sin_romper():
    archivos = {"no-respeta-el-formato.txt": "cualquier cosa"}
    assert auditar_archivos(archivos) == []


# --- validar_listado() ------------------------------------------------------


def test_validar_listado_sin_problemas():
    filas = [{"sellado": "111", "amortiguador": "222", "area": "HD"}]
    assert validar_listado(filas, "sellado", "amortiguador", "area") == []


def test_validar_listado_campo_vacio():
    filas = [{"sellado": "", "amortiguador": "222", "area": "HD"}]
    hallazgos = validar_listado(filas, "sellado", "amortiguador", "area")
    assert any(h.regla == "campo_vacio" and "sellado" in h.mensaje.lower() for h in hallazgos)


def test_validar_listado_no_numerico():
    filas = [{"sellado": "ABC", "amortiguador": "222", "area": "HD"}]
    hallazgos = validar_listado(filas, "sellado", "amortiguador", "area")
    assert any(h.regla == "campo_no_numerico" for h in hallazgos)


def test_validar_listado_codigo_repetido():
    filas = [
        {"sellado": "111", "amortiguador": "222", "area": "HD"},
        {"sellado": "111", "amortiguador": "333", "area": "HD"},
    ]
    hallazgos = validar_listado(filas, "sellado", "amortiguador", "area")
    de_esta_regla = [h for h in hallazgos if h.regla == "codigo_repetido"]
    assert len(de_esta_regla) == 1
    assert "111" in de_esta_regla[0].mensaje
