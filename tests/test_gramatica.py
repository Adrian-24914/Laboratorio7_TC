from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import main
from simplificador import (
    ErrorSintaxisGramatica,
    analizar_anulables,
    eliminar_epsilon,
    interpretar_gramatica,
)


class ValidacionTests(unittest.TestCase):
    def test_acepta_flechas_espacios_digitos_y_epsilon(self) -> None:
        gramatica = interpretar_gramatica("S → 0A0 | a | ε\nA -> b")

        self.assertEqual(gramatica.simbolo_inicial, "S")
        self.assertEqual(gramatica.producciones["S"], (("0", "A", "0"), ("a",), ()))

    def test_une_lineas_repetidas_sin_duplicar_alternativas(self) -> None:
        gramatica = interpretar_gramatica("S -> a\nS -> a | b")

        self.assertEqual(gramatica.producciones["S"], (("a",), ("b",)))

    def test_rechaza_formatos_invalidos(self) -> None:
        invalidas = (
            "s -> a",
            "S a",
            "S ->",
            "S -> a |",
            "S -> a_b",
            "S -> εa",
            "S -> a\n\nA -> b",
        )
        for texto in invalidas:
            with self.subTest(texto=texto):
                with self.assertRaises(ErrorSintaxisGramatica):
                    interpretar_gramatica(texto)

    def test_rechaza_archivo_vacio(self) -> None:
        with self.assertRaises(ErrorSintaxisGramatica):
            interpretar_gramatica("")


class AnulablesTests(unittest.TestCase):
    def test_calcula_punto_fijo_por_iteraciones(self) -> None:
        gramatica = interpretar_gramatica(
            "S -> BB\nA -> C\nB -> A\nC -> ε"
        )

        analisis = analizar_anulables(gramatica)

        self.assertEqual(analisis.simbolos, frozenset({"S", "A", "B", "C"}))
        self.assertEqual(
            [tuple(izquierda for izquierda, _ in paso.descubrimientos) for paso in analisis.pasos],
            [("C",), ("A",), ("B",), ("S",)],
        )

    def test_un_ciclo_sin_base_no_es_anulable(self) -> None:
        gramatica = interpretar_gramatica("S -> A\nA -> S | a")

        self.assertEqual(analizar_anulables(gramatica).simbolos, frozenset())

    def test_no_terminal_sin_definicion_no_se_asume_anulable(self) -> None:
        gramatica = interpretar_gramatica("S -> AE\nA -> ε")

        analisis = analizar_anulables(gramatica)

        self.assertEqual(analisis.simbolos, frozenset({"A"}))
        self.assertNotIn(("S", ("A", "E")), analisis.producciones_anulables)


class EliminacionTests(unittest.TestCase):
    def test_genera_todos_los_subconjuntos_por_posicion(self) -> None:
        gramatica = interpretar_gramatica("S -> AA\nA -> a | ε")

        resultado = eliminar_epsilon(gramatica)
        casos_s = [caso for caso in resultado.casos if caso.izquierda == "S"]

        self.assertEqual(len(casos_s), 4)
        self.assertEqual(resultado.resultado.producciones["S"], (("A", "A"), ("A",)))
        self.assertNotIn((), resultado.resultado.producciones["S"])
        self.assertEqual(sum(caso.motivo == "produccion duplicada" for caso in casos_s), 1)

    def test_resultado_estricto_no_contiene_epsilon(self) -> None:
        gramatica = interpretar_gramatica("S -> A | ε\nA -> a | ε")

        resultado = eliminar_epsilon(gramatica)

        self.assertTrue(resultado.analisis.simbolos.issuperset({"S", "A"}))
        for cuerpos in resultado.resultado.producciones.values():
            self.assertNotIn((), cuerpos)

    def test_gramatica_sin_anulables_permanece_igual(self) -> None:
        gramatica = interpretar_gramatica("S -> aA | b\nA -> a")

        resultado = eliminar_epsilon(gramatica)

        self.assertEqual(resultado.resultado.producciones, gramatica.producciones)
        self.assertTrue(all(caso.total == 1 for caso in resultado.casos))

    def test_tres_posiciones_anulables_generan_ocho_casos(self) -> None:
        gramatica = interpretar_gramatica("S -> ABA\nA -> ε\nB -> ε")

        resultado = eliminar_epsilon(gramatica)
        casos_s = [caso for caso in resultado.casos if caso.izquierda == "S"]

        self.assertEqual(len(casos_s), 8)
        self.assertEqual({caso.total for caso in casos_s}, {8})
        self.assertEqual(
            set(resultado.resultado.producciones["S"]),
            {
                ("A", "B", "A"),
                ("B", "A"),
                ("A", "A"),
                ("A", "B"),
                ("A",),
                ("B",),
            },
        )

    def test_modo_preservacion_crea_inicio_fresco(self) -> None:
        gramatica = interpretar_gramatica("S -> A\nA -> a | ε")

        resultado = eliminar_epsilon(gramatica, preservar_palabra_vacia=True)

        nuevo = resultado.nuevo_simbolo_inicial
        self.assertIsNotNone(nuevo)
        assert nuevo is not None
        self.assertNotIn(nuevo, gramatica.simbolos)
        self.assertEqual(resultado.resultado.simbolo_inicial, nuevo)
        self.assertEqual(resultado.resultado.producciones[nuevo], (("S",), ()))

    def test_resultados_de_las_dos_gramaticas_del_laboratorio(self) -> None:
        g1 = interpretar_gramatica(
            "S -> 0A0 | 1B1 | BB\nA -> C\nB -> S | A\nC -> S | ε"
        )
        g2 = interpretar_gramatica(
            "S -> aAa | bBb | ε\nA -> C | a\nB -> C | b\n"
            "C -> CDE | ε\nD -> A | B | ab"
        )

        r1 = eliminar_epsilon(g1).resultado.producciones
        r2 = eliminar_epsilon(g2).resultado.producciones

        self.assertEqual(
            r1["S"],
            (
                ("0", "A", "0"),
                ("0", "0"),
                ("1", "B", "1"),
                ("1", "1"),
                ("B", "B"),
                ("B",),
            ),
        )
        self.assertEqual(r1["A"], (("C",),))
        self.assertEqual(r1["B"], (("S",), ("A",)))
        self.assertEqual(r1["C"], (("S",),))
        self.assertEqual(r2["S"], (("a", "A", "a"), ("a", "a"), ("b", "B", "b"), ("b", "b")))
        self.assertEqual(r2["A"], (("C",), ("a",)))
        self.assertEqual(r2["B"], (("C",), ("b",)))
        self.assertEqual(r2["C"], (("C", "D", "E"), ("D", "E"), ("C", "E"), ("E",)))
        self.assertEqual(r2["D"], (("A",), ("B",), ("a", "b")))


class CliTests(unittest.TestCase):
    def test_si_un_archivo_falla_no_se_procesa_ninguno(self) -> None:
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            valido = carpeta / "valido.txt"
            invalido = carpeta / "invalido.txt"
            valido.write_text("S -> a", encoding="utf-8")
            invalido.write_text("s -> a", encoding="utf-8")
            salida = StringIO()
            errores = StringIO()

            codigo = main.ejecutar(
                (valido, invalido),
                salida=salida,
                errores=errores,
            )

        self.assertEqual(codigo, 1)
        self.assertEqual(salida.getvalue(), "")
        self.assertIn("ERROR DE VALIDACION", errores.getvalue())
        self.assertNotIn("PASO 1", salida.getvalue())

    def test_cli_predeterminada_ejecuta_las_dos_gramaticas(self) -> None:
        salida = StringIO()
        errores = StringIO()

        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = main.main([])

        self.assertEqual(codigo, 0)
        self.assertEqual(errores.getvalue(), "")
        self.assertIn("Validacion completada: 2 archivo(s) correcto(s).", salida.getvalue())
        self.assertEqual(salida.getvalue().count("PASO 3 - GRAMATICA RESULTANTE"), 2)


if __name__ == "__main__":
    unittest.main()
