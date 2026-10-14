"""Core domain enums, value objects, and geographical reference constants."""

from dataclasses import dataclass, field
from enum import StrEnum


class Office(StrEnum):
    """Electoral offices supported by the platform."""

    PRESIDENT = "president"
    GOVERNOR = "governor"
    SENATOR = "senator"
    FEDERAL_DEPUTY = "federal_deputy"
    STATE_DEPUTY = "state_deputy"
    DISTRICT_DEPUTY = "district_deputy"
    STATE_OR_DISTRICT_DEPUTY = "state_or_district_deputy"

    @property
    def label_pt(self) -> str:
        """Returns the display label in Brazilian Portuguese.

        Returns:
            Localized office label.
        """
        labels: dict[Office, str] = {
            Office.PRESIDENT: "Presidente",
            Office.GOVERNOR: "Governador",
            Office.SENATOR: "Senador",
            Office.FEDERAL_DEPUTY: "Deputado Federal",
            Office.STATE_DEPUTY: "Deputado Estadual",
            Office.DISTRICT_DEPUTY: "Deputado Distrital",
            Office.STATE_OR_DISTRICT_DEPUTY: "Deputado Estadual / Distrital",
        }
        return labels[self]

    @property
    def is_majoritarian(self) -> bool:
        """Indicates whether the office uses a majoritarian electoral system.

        Returns:
            True for majoritarian offices, False for proportional offices.
        """
        return self in {Office.PRESIDENT, Office.GOVERNOR, Office.SENATOR}


class Bloc(StrEnum):
    """Discrete ideological blocs derived from Bolognesi et al. (2023)."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"

    @property
    def label_pt(self) -> str:
        """Returns the display label in Brazilian Portuguese.

        Returns:
            Localized ideological bloc name.
        """
        labels: dict[Bloc, str] = {
            Bloc.LEFT: "Esquerda",
            Bloc.CENTER: "Centro",
            Bloc.RIGHT: "Direita",
        }
        return labels[self]


class Theme(StrEnum):
    """Thematic categories for municipal indicators."""

    ECONOMY = "economy"
    TRANSFERS = "transfers"
    SOCIAL = "social"
    EDUCATION = "education"
    HEALTH = "health"
    INFRASTRUCTURE = "infrastructure"
    FISCAL = "fiscal"
    COMPOSITE = "composite"
    ELECTORAL = "electoral"

    @property
    def label_pt(self) -> str:
        """Returns the thematic group display label in Brazilian Portuguese.

        Returns:
            Localized theme label.
        """
        labels: dict[Theme, str] = {
            Theme.ECONOMY: "Economia e renda",
            Theme.TRANSFERS: "Transferências de renda",
            Theme.SOCIAL: "Social e demografia",
            Theme.EDUCATION: "Educação",
            Theme.HEALTH: "Saúde",
            Theme.INFRASTRUCTURE: "Infraestrutura urbana",
            Theme.FISCAL: "Gestão fiscal",
            Theme.COMPOSITE: "Índices compostos",
            Theme.ELECTORAL: "Perfil eleitoral",
        }
        return labels[self]


class ElectoralSystem(StrEnum):
    """Electoral system types."""

    MAJORITARIAN = "majoritarian"
    PROPORTIONAL = "proportional"


class ElectionScope(StrEnum):
    """Geographic scope of an election contest."""

    NATIONAL = "national"
    STATE = "state"
    MUNICIPAL = "municipal"


class ValueType(StrEnum):
    """Statistical measurement scales for municipal indicators."""

    CONTINUOUS = "continuous"
    ORDINAL = "ordinal"
    CATEGORICAL = "categorical"


class HigherIs(StrEnum):
    """Normative direction of an indicator value (used only in text templates)."""

    BETTER = "better"
    WORSE = "worse"
    NEUTRAL = "neutral"


class ScaleHint(StrEnum):
    """Recommended visualization scale for choropleths and scatter axes."""

    LINEAR = "linear"
    LOG = "log"
    QUANTILE = "quantile"
    ORDINAL = "ordinal"
    CATEGORICAL = "categorical"


class IdeologyMethod(StrEnum):
    """Method used to assign a party's ideological score."""

    SURVEY = "survey"
    DERIVED = "derived"
    MANUAL = "manual"


class Severity(StrEnum):
    """Severity level for data quality checks."""

    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


class CorrelationStrength(StrEnum):
    """Qualitative classification of correlation magnitude."""

    NEGLIGIBLE = "negligible"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"

    @property
    def label_pt(self) -> str:
        """Returns the Portuguese adjective for correlation strength.

        Returns:
            Localized strength label.
        """
        labels: dict[CorrelationStrength, str] = {
            CorrelationStrength.NEGLIGIBLE: "desprezível",
            CorrelationStrength.WEAK: "fraca",
            CorrelationStrength.MODERATE: "moderada",
            CorrelationStrength.STRONG: "forte",
            CorrelationStrength.VERY_STRONG: "muito forte",
        }
        return labels[self]


class CorrelationDirection(StrEnum):
    """Direction of bivariate correlation."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"

    @property
    def label_pt(self) -> str:
        """Returns the Portuguese adjective for correlation direction.

        Returns:
            Localized direction label.
        """
        labels: dict[CorrelationDirection, str] = {
            CorrelationDirection.POSITIVE: "positiva",
            CorrelationDirection.NEGATIVE: "negativa",
            CorrelationDirection.NEUTRAL: "neutra",
        }
        return labels[self]


def classify_bloc_from_score(
    score: float,
    *,
    left_max_exclusive: float = 4.00,
    right_min_exclusive: float = 6.00,
) -> Bloc:
    """Maps a continuous ideological score in [0, 10] to a discrete Bloc.

    Args:
        score: Continuous ideological score between 0.0 and 10.0.
        left_max_exclusive: Upper threshold (exclusive) for the Left bloc.
        right_min_exclusive: Lower threshold (exclusive) for the Right bloc.

    Returns:
        Discrete Bloc corresponding to the score.

    Raises:
        ValueError: If score is outside [0.0, 10.0].
    """
    if score < 0.0 or score > 10.0:
        raise ValueError(f"Ideological score must be between 0.0 and 10.0, got {score}")
    if score < left_max_exclusive:
        return Bloc.LEFT
    if score > right_min_exclusive:
        return Bloc.RIGHT
    return Bloc.CENTER


def classify_correlation_strength(rho: float) -> CorrelationStrength:
    """Classifies `|rho|` into a discrete `CorrelationStrength` bucket.

    Args:
        rho: Spearman or Pearson correlation coefficient in `[-1.0, 1.0]`.

    Returns:
        Corresponding `CorrelationStrength` bucket.
    """
    abs_rho = abs(float(rho))
    if abs_rho < 0.10:
        return CorrelationStrength.NEGLIGIBLE
    if abs_rho < 0.30:
        return CorrelationStrength.WEAK
    if abs_rho < 0.50:
        return CorrelationStrength.MODERATE
    if abs_rho < 0.70:
        return CorrelationStrength.STRONG
    return CorrelationStrength.VERY_STRONG


def classify_correlation_direction(rho: float) -> CorrelationDirection:
    """Classifies `rho` into a `CorrelationDirection` (`NEUTRAL` if `|rho| < 0.10`).

    Args:
        rho: Spearman or Pearson correlation coefficient.

    Returns:
        Corresponding `CorrelationDirection`.
    """
    if abs(float(rho)) < 0.10:
        return CorrelationDirection.NEUTRAL
    return CorrelationDirection.POSITIVE if rho > 0.0 else CorrelationDirection.NEGATIVE


@dataclass(frozen=True, slots=True)
class StepResult:
    """Outcome of an ETL pipeline step.

    Attributes:
        step: Step name.
        rows_in: Rows read from the source.
        rows_out: Rows written to the database.
        dropped: Mapping of drop reason to row count.
        warnings_count: Count of non-blocking quality warnings.
        source_url: Optional URL of the primary source.
        source_version: Optional version or generation timestamp from the source.
        sha256: Optional SHA-256 hex digest of the source file.
    """

    step: str
    rows_in: int
    rows_out: int
    dropped: dict[str, int] = field(default_factory=dict)
    warnings_count: int = 0
    source_url: str | None = None
    source_version: str | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class CorrelationStat:
    """Bivariate correlation statistics between an indicator and a bloc vote share.

    Attributes:
        spearman_rho: Spearman rank correlation coefficient.
        spearman_p: Two-sided p-value for Spearman rho.
        pearson_r: Pearson linear correlation coefficient.
        pearson_p: Two-sided p-value for Pearson r.
        strength: Qualitative strength bucket based on |spearman_rho|.
        direction: Direction bucket based on spearman_rho.
        n_valid: Number of valid municipal pairs included.
    """

    spearman_rho: float
    spearman_p: float
    pearson_r: float
    pearson_p: float
    strength: CorrelationStrength
    direction: CorrelationDirection
    n_valid: int


CorrelationStats = CorrelationStat


@dataclass(frozen=True, slots=True)
class DecileStat:
    """Aggregated electoral and indicator metrics for one indicator decile.

    Attributes:
        decile: Decile index from 1 (lowest indicator values) to 10 (highest).
        municipality_count: Number of municipalities in this decile.
        indicator_min: Minimum indicator value in the decile.
        indicator_max: Maximum indicator value in the decile.
        indicator_median: Median indicator value in the decile.
        valid_votes: Sum of valid votes across municipalities in the decile.
        bloc_votes: Total votes for the target ideological bloc in the decile.
        weighted_share: Vote-weighted bloc share (bloc_votes / valid_votes).
        unweighted_mean_share: Simple mean of municipal bloc shares.
    """

    decile: int
    municipality_count: int
    indicator_min: float
    indicator_max: float
    indicator_median: float
    valid_votes: int
    bloc_votes: int
    weighted_share: float
    unweighted_mean_share: float


@dataclass(frozen=True, slots=True)
class QuintileExtremesContrast:
    """Deterministic comparison between bottom 20% and top 20% indicator municipalities.

    Attributes:
        bottom_quintile_share: Vote-weighted bloc share in bottom 20% (D1 + D2).
        top_quintile_share: Vote-weighted bloc share in top 20% (D9 + D10).
        diff_pp: Percentage-point difference (top minus bottom quintile).
        bottom_indicator_range: Tuple (min, max) for bottom 20%.
        top_indicator_range: Tuple (min, max) for top 20%.
        bottom_municipality_count: Number of municipalities in bottom 20%.
        top_municipality_count: Number of municipalities in top 20%.
        tipping_point_decile: Decile index (1-10) where bloc share crosses 50%.
        tipping_point_threshold: Indicator value at tipping point threshold.
    """

    bottom_quintile_share: float
    top_quintile_share: float
    diff_pp: float
    bottom_indicator_range: tuple[float, float]
    top_indicator_range: tuple[float, float]
    bottom_municipality_count: int
    top_municipality_count: int
    tipping_point_decile: int | None
    tipping_point_threshold: float | None


@dataclass(frozen=True, slots=True)
class InsightCard:
    """Deterministic narrative insight produced from computed statistics.

    Attributes:
        template_id: Stable identifier of the template used.
        severity: Visual tone ('headline' | 'finding' | 'caveat').
        title: Short card header in Portuguese.
        text: Rendered Portuguese sentence with formatted numbers.
        params: Raw numeric/string parameters used to render text.
    """

    template_id: str
    severity: str
    title: str
    text: str
    params: dict[str, int | float | str]


@dataclass(frozen=True, slots=True)
class UFMetadata:
    """Static geographical metadata for a Brazilian federative unit (UF).

    Attributes:
        uf: Two-letter uppercase acronym (e.g., 'SP').
        uf_code: Two-digit IBGE UF code (e.g., 35).
        name: Full official state name in Portuguese.
        region: Brazilian macroregion ('Norte', 'Nordeste', etc.).
        capital_cd_ibge: Canonical 7-digit IBGE code of the state capital.
        default_bbox: Fallback bbox [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.
    """

    uf: str
    uf_code: int
    name: str
    region: str
    capital_cd_ibge: int
    default_bbox: tuple[float, float, float, float]


UFS: tuple[UFMetadata, ...] = (
    UFMetadata("RO", 11, "Rondônia", "Norte", 1100205, (-66.81, -13.69, -59.77, -7.97)),
    UFMetadata("AC", 12, "Acre", "Norte", 1200401, (-73.99, -11.14, -66.62, -7.11)),
    UFMetadata("AM", 13, "Amazonas", "Norte", 1302603, (-73.80, -9.82, -56.10, 2.25)),
    UFMetadata("RR", 14, "Roraima", "Norte", 1400100, (-64.82, -1.58, -58.89, 5.27)),
    UFMetadata("PA", 15, "Pará", "Norte", 1501402, (-58.90, -9.84, -46.06, 2.59)),
    UFMetadata("AP", 16, "Amapá", "Norte", 1600303, (-54.88, -1.23, -49.87, 4.44)),
    UFMetadata(
        "TO", 17, "Tocantins", "Norte", 1721000, (-50.74, -13.47, -45.70, -5.17)
    ),
    UFMetadata(
        "MA", 21, "Maranhão", "Nordeste", 2111300, (-48.76, -10.26, -41.79, -1.05)
    ),
    UFMetadata("PI", 22, "Piauí", "Nordeste", 2211001, (-45.99, -10.93, -40.37, -2.74)),
    UFMetadata("CE", 23, "Ceará", "Nordeste", 2304400, (-41.42, -7.86, -37.25, -2.78)),
    UFMetadata(
        "RN",
        24,
        "Rio Grande do Norte",
        "Nordeste",
        2408102,
        (-38.58, -6.98, -34.97, -4.83),
    ),
    UFMetadata(
        "PB", 25, "Paraíba", "Nordeste", 2507507, (-38.77, -8.30, -34.79, -6.02)
    ),
    UFMetadata(
        "PE", 26, "Pernambuco", "Nordeste", 2611606, (-41.36, -9.48, -34.81, -7.15)
    ),
    UFMetadata(
        "AL", 27, "Alagoas", "Nordeste", 2704302, (-38.24, -10.50, -35.15, -8.81)
    ),
    UFMetadata(
        "SE", 28, "Sergipe", "Nordeste", 2800308, (-38.25, -11.57, -36.39, -9.51)
    ),
    UFMetadata("BA", 29, "Bahia", "Nordeste", 2927408, (-46.62, -18.35, -37.34, -8.53)),
    UFMetadata(
        "MG", 31, "Minas Gerais", "Sudeste", 3106200, (-51.05, -22.92, -39.86, -14.23)
    ),
    UFMetadata(
        "ES", 32, "Espírito Santo", "Sudeste", 3205309, (-41.88, -21.30, -39.68, -17.89)
    ),
    UFMetadata(
        "RJ", 33, "Rio de Janeiro", "Sudeste", 3304557, (-44.89, -23.37, -40.96, -20.76)
    ),
    UFMetadata(
        "SP", 35, "São Paulo", "Sudeste", 3550308, (-53.11, -25.31, -44.16, -19.78)
    ),
    UFMetadata("PR", 41, "Paraná", "Sul", 4106902, (-54.62, -26.72, -48.02, -22.52)),
    UFMetadata(
        "SC", 42, "Santa Catarina", "Sul", 4205407, (-53.84, -29.35, -48.55, -25.95)
    ),
    UFMetadata(
        "RS", 43, "Rio Grande do Sul", "Sul", 4314902, (-57.64, -33.75, -49.69, -27.08)
    ),
    UFMetadata(
        "MS",
        50,
        "Mato Grosso do Sul",
        "Centro-Oeste",
        5002704,
        (-58.17, -24.07, -50.92, -17.17),
    ),
    UFMetadata(
        "MT",
        51,
        "Mato Grosso",
        "Centro-Oeste",
        5103403,
        (-61.63, -18.04, -50.22, -7.35),
    ),
    UFMetadata(
        "GO", 52, "Goiás", "Centro-Oeste", 5208707, (-53.25, -19.49, -45.91, -12.39)
    ),
    UFMetadata(
        "DF",
        53,
        "Distrito Federal",
        "Centro-Oeste",
        5300108,
        (-48.29, -16.05, -47.31, -15.50),
    ),
)

UF_BY_SIGLA: dict[str, UFMetadata] = {item.uf: item for item in UFS}
UF_BY_CODE: dict[int, UFMetadata] = {item.uf_code: item for item in UFS}
CAPITAL_CD_IBGE_SET: frozenset[int] = frozenset(item.capital_cd_ibge for item in UFS)
