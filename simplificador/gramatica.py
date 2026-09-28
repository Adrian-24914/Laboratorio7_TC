"""Modelo, validacion y eliminacion de producciones epsilon para CFGs.

El formato del laboratorio usa simbolos de un solo caracter. Las mayusculas
ASCII representan no terminales; las minusculas y los digitos representan
terminales. Internamente, epsilon se representa con una tupla vacia.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence


EPSILON = "ε"
Cuerpo = tuple[str, ...]
Produccion = tuple[str, Cuerpo]

_CUERPO = rf"(?:{EPSILON}|[A-Za-z0-9]+)"
PATRON_PRODUCCION = re.compile(
    rf"^\s*([A-Z])\s*(?:->|→)\s*({_CUERPO}(?:\s*\|\s*{_CUERPO})*)\s*$"
)


class ErrorSintaxisGramatica(ValueError):
    """Indica que una linea no cumple el formato de produccion requerido."""

    def __init__(
        self,
        fuente: str,
        numero_linea: int,
        linea: str,
        detalle: str,
    ) -> None:
        self.fuente = fuente
        self.numero_linea = numero_linea
        self.linea = linea
        self.detalle = detalle
        super().__init__(
            f"{fuente}, linea {numero_linea}: {detalle}. Contenido: {linea!r}"
        )


class ErrorSemanticoGramatica(ValueError):
    """Indica que una transformacion valida no puede representarse."""


@dataclass(frozen=True)
class Gramatica:
    """Una CFG con orden estable para que la demostracion sea reproducible."""

    simbolo_inicial: str
    producciones: Mapping[str, tuple[Cuerpo, ...]]
    fuente: str = "<memoria>"

    def __post_init__(self) -> None:
        copia = {
            izquierda: tuple(cuerpos)
            for izquierda, cuerpos in self.producciones.items()
        }
        object.__setattr__(self, "producciones", MappingProxyType(copia))

    def recorrer_producciones(self) -> Iterable[Produccion]:
        for izquierda, cuerpos in self.producciones.items():
            for cuerpo in cuerpos:
                yield izquierda, cuerpo

    @property
    def simbolos(self) -> frozenset[str]:
        resultado = set(self.producciones)
        for _, cuerpo in self.recorrer_producciones():
            resultado.update(cuerpo)
        return frozenset(resultado)

    def lineas(self) -> tuple[str, ...]:
        lineas: list[str] = []
        for izquierda, cuerpos in self.producciones.items():
            if cuerpos:
                alternativas = " | ".join(texto_cuerpo(cuerpo) for cuerpo in cuerpos)
                lineas.append(f"{izquierda} -> {alternativas}")
            else:
                lineas.append(f"{izquierda} -> (sin producciones)")
        return tuple(lineas)


@dataclass(frozen=True)
class DescubrimientoAnulable:
    iteracion: int
    descubrimientos: tuple[Produccion, ...]


@dataclass(frozen=True)
class AnalisisAnulables:
    simbolos: frozenset[str]
    pasos: tuple[DescubrimientoAnulable, ...]
    producciones_anulables: tuple[Produccion, ...]


@dataclass(frozen=True)
class CasoCombinacion:
    izquierda: str
    cuerpo_original: Cuerpo
    numero: int
    total: int
    posiciones_anulables: tuple[int, ...]
    posiciones_omitidas: tuple[int, ...]
    cuerpo_generado: Cuerpo
    aceptado: bool
    motivo: str


@dataclass(frozen=True)
class EliminacionEpsilon:
    original: Gramatica
    resultado: Gramatica
    analisis: AnalisisAnulables
    casos: tuple[CasoCombinacion, ...]
    epsilon_directas_eliminadas: tuple[Produccion, ...]
    preserva_palabra_vacia: bool
    nuevo_simbolo_inicial: str | None


def es_no_terminal(simbolo: str) -> bool:
    return len(simbolo) == 1 and "A" <= simbolo <= "Z"


def texto_cuerpo(cuerpo: Sequence[str]) -> str:
    return "".join(cuerpo) if cuerpo else EPSILON


def interpretar_gramatica(texto: str, fuente: str = "<memoria>") -> Gramatica:
    """Valida todas las lineas y construye una gramatica.

    Se permiten las flechas ``->`` y ``→``. Una linea vacia tambien es un
    error: el enunciado establece que cada linea representa una produccion.
    """

    lineas = texto.splitlines()
    if not lineas:
        raise ErrorSintaxisGramatica(
            fuente,
            1,
            "",
            "el archivo esta vacio; se esperaba al menos una produccion",
        )

    acumuladas: dict[str, list[Cuerpo]] = {}
    simbolo_inicial: str | None = None

    for numero_linea, linea in enumerate(lineas, start=1):
        if not linea.strip():
            raise ErrorSintaxisGramatica(
                fuente,
                numero_linea,
                linea,
                "una linea vacia no representa una produccion",
            )

        coincidencia = PATRON_PRODUCCION.fullmatch(linea)
        if coincidencia is None:
            raise ErrorSintaxisGramatica(
                fuente,
                numero_linea,
                linea,
                (
                    "formato invalido; use A -> cuerpo | cuerpo, con simbolos "
                    "ASCII alfanumericos individuales o ε"
                ),
            )

        izquierda, texto_derecha = coincidencia.groups()
        if simbolo_inicial is None:
            simbolo_inicial = izquierda

        destinos = acumuladas.setdefault(izquierda, [])
        for alternativa in re.split(r"\s*\|\s*", texto_derecha):
            cuerpo: Cuerpo = () if alternativa == EPSILON else tuple(alternativa)
            if cuerpo not in destinos:
                destinos.append(cuerpo)

    assert simbolo_inicial is not None
    return Gramatica(
        simbolo_inicial=simbolo_inicial,
        producciones={
            izquierda: tuple(cuerpos) for izquierda, cuerpos in acumuladas.items()
        },
        fuente=fuente,
    )


def cargar_gramatica(ruta: str | Path) -> Gramatica:
    ruta_objeto = Path(ruta)
    texto = ruta_objeto.read_text(encoding="utf-8-sig")
    return interpretar_gramatica(texto, str(ruta_objeto))


def analizar_anulables(gramatica: Gramatica) -> AnalisisAnulables:
    """Calcula el menor punto fijo de no terminales anulables."""

    anulables: set[str] = set()
    pasos: list[DescubrimientoAnulable] = []

    directos: list[Produccion] = []
    for izquierda, cuerpos in gramatica.producciones.items():
        if () in cuerpos:
            anulables.add(izquierda)
            directos.append((izquierda, ()))
    pasos.append(DescubrimientoAnulable(0, tuple(directos)))

    iteracion = 1
    while True:
        nuevos: list[Produccion] = []
        ya_programados: set[str] = set()
        for izquierda, cuerpos in gramatica.producciones.items():
            if izquierda in anulables or izquierda in ya_programados:
                continue
            for cuerpo in cuerpos:
                if cuerpo and all(
                    es_no_terminal(simbolo) and simbolo in anulables
                    for simbolo in cuerpo
                ):
                    nuevos.append((izquierda, cuerpo))
                    ya_programados.add(izquierda)
                    break

        if not nuevos:
            break
        anulables.update(izquierda for izquierda, _ in nuevos)
        pasos.append(DescubrimientoAnulable(iteracion, tuple(nuevos)))
        iteracion += 1

    producciones_anulables = tuple(
        (izquierda, cuerpo)
        for izquierda, cuerpo in gramatica.recorrer_producciones()
        if not cuerpo
        or all(
            es_no_terminal(simbolo) and simbolo in anulables for simbolo in cuerpo
        )
    )
    return AnalisisAnulables(
        simbolos=frozenset(anulables),
        pasos=tuple(pasos),
        producciones_anulables=producciones_anulables,
    )


def _nuevo_simbolo_inicial(gramatica: Gramatica) -> str:
    usados = {simbolo for simbolo in gramatica.simbolos if es_no_terminal(simbolo)}
    for candidato in reversed("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        if candidato not in usados:
            return candidato
    raise ErrorSemanticoGramatica(
        "no queda una letra mayuscula disponible para crear un simbolo inicial nuevo"
    )


def eliminar_epsilon(
    gramatica: Gramatica,
    *,
    preservar_palabra_vacia: bool = False,
) -> EliminacionEpsilon:
    """Elimina producciones epsilon enumerando los 2**m subconjuntos.

    De forma predeterminada se produce una gramatica sin ninguna produccion
    epsilon, tal como pide el laboratorio. Si ``preservar_palabra_vacia`` es
    verdadero y el inicio es anulable, se agrega un inicio fresco con la unica
    produccion epsilon permitida por la construccion estandar.
    """

    analisis = analizar_anulables(gramatica)
    nuevas: dict[str, list[Cuerpo]] = {
        izquierda: [] for izquierda in gramatica.producciones
    }
    casos: list[CasoCombinacion] = []
    eliminadas: list[Produccion] = []

    for izquierda, cuerpo in gramatica.recorrer_producciones():
        if not cuerpo:
            eliminadas.append((izquierda, cuerpo))
            continue

        posiciones = tuple(
            indice
            for indice, simbolo in enumerate(cuerpo)
            if es_no_terminal(simbolo) and simbolo in analisis.simbolos
        )
        total = 1 << len(posiciones)

        for mascara in range(total):
            omitidas = tuple(
                posicion
                for bit, posicion in enumerate(posiciones)
                if mascara & (1 << bit)
            )
            conjunto_omitidas = set(omitidas)
            generado = tuple(
                simbolo
                for indice, simbolo in enumerate(cuerpo)
                if indice not in conjunto_omitidas
            )

            if not generado:
                aceptado = False
                motivo = "se descarta para que el resultado no contenga ε"
            elif generado in nuevas[izquierda]:
                aceptado = False
                motivo = "produccion duplicada"
            else:
                nuevas[izquierda].append(generado)
                aceptado = True
                motivo = "produccion agregada"

            casos.append(
                CasoCombinacion(
                    izquierda=izquierda,
                    cuerpo_original=cuerpo,
                    numero=mascara + 1,
                    total=total,
                    posiciones_anulables=posiciones,
                    posiciones_omitidas=omitidas,
                    cuerpo_generado=generado,
                    aceptado=aceptado,
                    motivo=motivo,
                )
            )

    nuevo_inicio: str | None = None
    resultado_producciones: dict[str, tuple[Cuerpo, ...]] = {
        izquierda: tuple(cuerpos) for izquierda, cuerpos in nuevas.items()
    }
    simbolo_inicial = gramatica.simbolo_inicial

    if preservar_palabra_vacia and simbolo_inicial in analisis.simbolos:
        nuevo_inicio = _nuevo_simbolo_inicial(gramatica)
        resultado_producciones = {
            nuevo_inicio: ((simbolo_inicial,), ()),
            **resultado_producciones,
        }
        simbolo_inicial = nuevo_inicio

    resultado = Gramatica(
        simbolo_inicial=simbolo_inicial,
        producciones=resultado_producciones,
        fuente=f"resultado de {gramatica.fuente}",
    )
    return EliminacionEpsilon(
        original=gramatica,
        resultado=resultado,
        analisis=analisis,
        casos=tuple(casos),
        epsilon_directas_eliminadas=tuple(eliminadas),
        preserva_palabra_vacia=preservar_palabra_vacia,
        nuevo_simbolo_inicial=nuevo_inicio,
    )

