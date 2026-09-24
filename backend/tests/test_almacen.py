from app.ai.memoria import almacen

import paths


def _guardar(tmp_path, monkeypatch, nombre="H1312"):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    return almacen.guardar(
        "mediciones", nombre,
        huella={"separador": ",", "bloques": []},
        regla={"separador": ",", "tablas": []},
        explicacion="de la 1 a la 12 es la primera tabla",
        creado_por="mateo",
    )


def test_guardar_y_obtener(tmp_path, monkeypatch):
    formato = _guardar(tmp_path, monkeypatch)
    obtenido = almacen.obtener(formato.id)
    assert obtenido == formato
    assert obtenido.usos == 0 and obtenido.ultimo_uso is None


def test_listar_filtra_por_pantalla(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    almacen.guardar("mediciones", "A", {}, {}, "", "u")
    almacen.guardar("plantilla", "B", {}, {}, "", "u")
    assert [f.nombre for f in almacen.listar("mediciones")] == ["A"]
    assert {f.nombre for f in almacen.listar()} == {"A", "B"}


def test_actualizar_cambia_nombre_huella_y_regla(tmp_path, monkeypatch):
    formato = _guardar(tmp_path, monkeypatch)
    actualizado = almacen.actualizar(
        formato.id, nombre="H1312 v2", huella={"separador": ";", "bloques": []}
    )
    assert actualizado.nombre == "H1312 v2"
    assert actualizado.huella == {"separador": ";", "bloques": []}
    assert actualizado.regla == formato.regla  # no se toco
    assert almacen.obtener(formato.id) == actualizado


def test_actualizar_formato_inexistente_es_un_error(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    with pytest.raises(ValueError, match="No existe"):
        almacen.actualizar("no-existe", nombre="x")


def test_registrar_uso_suma_y_marca_ultimo_uso(tmp_path, monkeypatch):
    formato = _guardar(tmp_path, monkeypatch)
    almacen.registrar_uso(formato.id)
    almacen.registrar_uso(formato.id)
    obtenido = almacen.obtener(formato.id)
    assert obtenido.usos == 2
    assert obtenido.ultimo_uso is not None


def test_borrar(tmp_path, monkeypatch):
    formato = _guardar(tmp_path, monkeypatch)
    almacen.borrar(formato.id)
    assert almacen.obtener(formato.id) is None
