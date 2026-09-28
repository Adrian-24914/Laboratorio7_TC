"""CLI del problema 1 del Laboratorio 7 de Teoria de la Computacion."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence, TextIO

from simplificador import (
    EliminacionEpsilon,
    ErrorSemanticoGramatica,
    ErrorSintaxisGramatica,
    Gramatica,
    cargar_gramatica,
    eliminar_epsilon,
    texto_cuerpo,
)


RAIZ = Path(__file__).resolve().parent
ARCHIVOS_PREDETERMINADOS = (
    RAIZ / "gramaticas" / "gramatica_1.txt",
    RAIZ / "gramaticas" / "gramatica_2.txt",
)


def _escribir_gramatica(gramatica: Gramatica, salida: TextIO) -> None:
    for linea in gramatica.lineas():
        print(f"  {linea}", file=salida)


def _lista_posiciones(posiciones: Sequence[int], cuerpo: Sequence[str]) -> str:
    if not posiciones:
        return "ninguna"
    return ", ".join(f"{posicion + 1}:{cuerpo[posicion]}" for posicion in posiciones)


def mostrar_ejecucion(
    resultado: EliminacionEpsilon,
    salida: TextIO | None = None,
) -> None:
    if salida is None:
        salida = sys.stdout
    gramatica = resultado.original
    analisis = resultado.analisis

    print("=" * 76, file=salida)
    print(f"ARCHIVO: {gramatica.fuente}", file=salida)
    print(f"SIMBOLO INICIAL: {gramatica.simbolo_inicial}", file=salida)
    print("\nGRAMATICA ORIGINAL", file=salida)
    _escribir_gramatica(gramatica, salida)

    print("\nPASO 1 - ENCONTRAR SIMBOLOS Y PRODUCCIONES ANULABLES", file=salida)
    for paso in analisis.pasos:
        if paso.iteracion == 0:
            titulo = "Iteracion 0 (producciones ε directas)"
        else:
            titulo = f"Iteracion {paso.iteracion} (punto fijo)"
        print(f"  {titulo}:", file=salida)
        if not paso.descubrimientos:
            print("    No se encontro ningun simbolo nuevo.", file=salida)
        for izquierda, cuerpo in paso.descubrimientos:
            print(
                f"    {izquierda} es anulable por {izquierda} -> {texto_cuerpo(cuerpo)}",
                file=salida,
            )

    if analisis.simbolos:
        simbolos = ", ".join(sorted(analisis.simbolos))
    else:
        simbolos = "ninguno"
    print(f"  Conjunto anulable final: {{{simbolos}}}", file=salida)
    print("  Producciones anulables:", file=salida)
    if not analisis.producciones_anulables:
        print("    ninguna", file=salida)
    for izquierda, cuerpo in analisis.producciones_anulables:
        print(f"    {izquierda} -> {texto_cuerpo(cuerpo)}", file=salida)

    print("\nPASO 2 - GENERAR LOS 2^m CASOS", file=salida)
    for izquierda, _ in resultado.epsilon_directas_eliminadas:
        print(f"  {izquierda} -> ε: eliminada directamente.", file=salida)

    grupo_anterior: tuple[str, tuple[str, ...]] | None = None
    for caso in resultado.casos:
        grupo = (caso.izquierda, caso.cuerpo_original)
        if grupo != grupo_anterior:
            m = len(caso.posiciones_anulables)
            print(
                f"\n  {caso.izquierda} -> {texto_cuerpo(caso.cuerpo_original)}",
                file=salida,
            )
            print(
                "    Posiciones anulables: "
                + _lista_posiciones(caso.posiciones_anulables, caso.cuerpo_original),
                file=salida,
            )
            print(f"    m = {m}; 2^{m} = {caso.total} caso(s)", file=salida)
            grupo_anterior = grupo

        omitidas = _lista_posiciones(caso.posiciones_omitidas, caso.cuerpo_original)
        estado = "AGREGADA" if caso.aceptado else "DESCARTADA"
        print(
            f"    Caso {caso.numero}/{caso.total}: omitir {omitidas} => "
            f"{texto_cuerpo(caso.cuerpo_generado)} [{estado}: {caso.motivo}]",
            file=salida,
        )

    print("\nPASO 3 - GRAMATICA RESULTANTE", file=salida)
    _escribir_gramatica(resultado.resultado, salida)

    inicio_original = gramatica.simbolo_inicial
    if inicio_original in analisis.simbolos:
        if resultado.nuevo_simbolo_inicial is None:
            print(
                "\n  Nota: el inicio era anulable. Para cumplir 'sin producciones-ε', "
                "la palabra vacia no pertenece al resultado.",
                file=salida,
            )
        else:
            print(
                f"\n  Se introdujo {resultado.nuevo_simbolo_inicial} como inicio para "
                "preservar la palabra vacia; su ε es la excepcion estandar.",
                file=salida,
            )


def ejecutar(
    rutas: Sequence[str | Path],
    *,
    preservar_palabra_vacia: bool = False,
    salida: TextIO | None = None,
    errores: TextIO | None = None,
) -> int:
    """Valida todos los archivos antes de transformar cualquiera de ellos."""

    if salida is None:
        salida = sys.stdout
    if errores is None:
        errores = sys.stderr

    gramaticas: list[Gramatica] = []
    try:
        for ruta in rutas:
            gramaticas.append(cargar_gramatica(ruta))
    except (OSError, UnicodeError) as error:
        print(f"ERROR DE LECTURA: {error}", file=errores)
        print("Ejecucion detenida; no se simplifico ningun archivo.", file=errores)
        return 1
    except ErrorSintaxisGramatica as error:
        print(f"ERROR DE VALIDACION: {error}", file=errores)
        print("Ejecucion detenida; no se simplifico ningun archivo.", file=errores)
        return 1

    print(
        f"Validacion completada: {len(gramaticas)} archivo(s) correcto(s).",
        file=salida,
    )
    try:
        for gramatica in gramaticas:
            resultado = eliminar_epsilon(
                gramatica,
                preservar_palabra_vacia=preservar_palabra_vacia,
            )
            mostrar_ejecucion(resultado, salida)
    except ErrorSemanticoGramatica as error:
        print(f"ERROR SEMANTICO: {error}", file=errores)
        return 1
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Valida gramaticas y muestra paso a paso la eliminacion de "
            "producciones epsilon."
        )
    )
    parser.add_argument(
        "archivos",
        nargs="*",
        type=Path,
        help=(
            "archivos UTF-8 a procesar; si se omiten, se usan las dos "
            "gramaticas incluidas"
        ),
    )
    parser.add_argument(
        "--preservar-epsilon",
        action="store_true",
        help=(
            "si el inicio es anulable, crea un inicio nuevo y conserva una "
            "unica produccion epsilon"
        ),
    )
    return parser


def main(argumentos: Sequence[str] | None = None) -> int:
    parser = construir_parser()
    opciones = parser.parse_args(argumentos)
    rutas = opciones.archivos or ARCHIVOS_PREDETERMINADOS
    return ejecutar(
        rutas,
        preservar_palabra_vacia=opciones.preservar_epsilon,
    )


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
