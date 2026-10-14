"""Loaders and validators for reference YAML catalogs."""

import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import sqlalchemy as sa
import yaml

from territorio.domain import (
    Bloc,
    ElectionScope,
    ElectoralSystem,
    HigherIs,
    IdeologyMethod,
    Office,
    ScaleHint,
    StepResult,
    Theme,
    ValueType,
    classify_bloc_from_score,
)


class ReferenceCatalogError(ValueError):
    """Raised when a reference YAML catalog violates schema or business rules."""


class UnclassifiedPartyError(ReferenceCatalogError):
    """Raised when an electoral party with votes has no active ideology record."""


@dataclass(frozen=True, slots=True)
class PartyIdeologyEntry:
    """Single party classification record loaded from `party_ideology.yaml`.

    Attributes:
        party_code: Canonical normalized party code (e.g. 'PT', 'UNIAO', 'MISSAO').
        number: Electoral ballot number of the party.
        name: Full official party name.
        score: Continuous ideological score in [0.0, 10.0].
        bloc: Discrete ideological bloc ('left', 'center', 'right').
        valid_from: Start year of validity (inclusive).
        valid_to: End year of validity (inclusive), or None if currently active.
        method: Classification method ('survey', 'derived', 'manual').
        source: Academic or statutory citation string.
        note: Optional methodological note.
    """

    party_code: str
    number: int | None
    name: str
    score: float
    bloc: Bloc
    valid_from: int
    valid_to: int | None
    method: IdeologyMethod
    source: str
    note: str | None


@dataclass(frozen=True, slots=True)
class PartyIdeologyCatalog:
    """Validated ideological classification catalog and alias map.

    Attributes:
        entries: Tuple of all historical and active party ideology entries.
        aliases: Mapping from normalized alternative TSE acronyms to
            canonical `party_code`.
        left_max_exclusive: Score threshold separating Left from Center.
        right_min_exclusive: Score threshold separating Center from Right.
    """

    entries: tuple[PartyIdeologyEntry, ...]
    aliases: dict[str, str]
    left_max_exclusive: float
    right_min_exclusive: float

    def active_parties_for_year(self, year: int) -> dict[str, PartyIdeologyEntry]:
        """Returns a mapping of `party_code -> PartyIdeologyEntry` active in `year`.

        Args:
            year: Election year (e.g. 2026).

        Returns:
            Dictionary of active party entries for the given election year.
        """
        result: dict[str, PartyIdeologyEntry] = {}
        for entry in self.entries:
            if entry.valid_from <= year and (
                entry.valid_to is None or year <= entry.valid_to
            ):
                result[entry.party_code] = entry
        return result


@dataclass(frozen=True, slots=True)
class CoverageExceptionRule:
    """Documented coverage exception for a specific municipality in `indicators.yaml`.

    Attributes:
        cd_ibge: Canonical 7-digit IBGE municipality code.
        name: Municipality name.
        uf: State acronym.
        missing_reason: Standardized reason string stored in
            `indicator_value.missing_reason`.
        applies_to_ref_years_before: Optional year cutoff (e.g. 2025 for
            Boa Esperança do Norte).
        applies_to_adapters: Optional tuple of adapter names (e.g. ('siconfi', 'ckan')).
    """

    cd_ibge: int
    name: str
    uf: str
    missing_reason: str
    applies_to_ref_years_before: int | None = None
    applies_to_adapters: tuple[str, ...] | None = None

    def matches(self, *, adapter: str, ref_year: int) -> bool:
        """Checks whether this exception rule applies to a given adapter and ref_year.

        Args:
            adapter: Source adapter name.
            ref_year: Reference year of the indicator value.

        Returns:
            True if the municipality is exempt from coverage failure for this indicator.
        """
        if (
            self.applies_to_ref_years_before is not None
            and ref_year < self.applies_to_ref_years_before
        ):
            return True
        return bool(
            self.applies_to_adapters is not None and adapter in self.applies_to_adapters
        )


@dataclass(frozen=True, slots=True)
class IndicatorSpec:
    """Specification of a municipal indicator from `data/reference/indicators.yaml`.

    Attributes:
        code: Immutable snake_case identifier.
        label: Short Portuguese display label (<= 32 chars).
        description: Full description in Portuguese.
        theme: Thematic group enum.
        tier: Priority tier (1 or 2).
        unit: Measurement unit label.
        value_type: Measurement scale ('continuous', 'ordinal', 'categorical').
        higher_is: Normative direction ('better', 'worse', 'neutral').
        scale_hint: Visualization scale hint.
        valid_range: Optional `(min_val, max_val)` plausibility bounds.
        adapter: Source adapter name ('sidra', 'ibge_pesquisas', 'transparencia', etc.).
        source_params: Adapter-specific parameters dictionary.
        source_name: Human-readable source institution/survey name.
        source_url: Reference URL for the data source.
        license: Data license description.
        citation: Bibliographic citation.
        transform: Optional declarative post-processing rules dictionary.
        ref_year_policy: Policy for selecting reference year ('latest',
            'fixed:YYYY', etc.).
        min_coverage: Minimum required share of valid municipalities in [0.0, 1.0].
        caveat: Optional methodological caveat displayed in the UI.
        verified: Whether source parameters/hashes are verified for production load.
    """

    code: str
    label: str
    description: str
    theme: Theme
    tier: int
    unit: str
    value_type: ValueType
    higher_is: HigherIs
    scale_hint: ScaleHint
    valid_range: tuple[float, float] | None
    adapter: str
    source_params: dict[str, Any]
    source_name: str
    source_url: str
    license: str | None
    citation: str | None
    transform: dict[str, Any] | None
    ref_year_policy: str
    min_coverage: float
    caveat: str | None
    verified: bool


@dataclass(frozen=True, slots=True)
class IndicatorsCatalog:
    """Complete parsed `indicators.yaml` catalog.

    Attributes:
        indicators: Ordered mapping of `code -> IndicatorSpec`.
        coverage_exceptions: Tuple of documented municipal coverage exceptions.
    """

    indicators: dict[str, IndicatorSpec]
    coverage_exceptions: tuple[CoverageExceptionRule, ...]


CoverageException = CoverageExceptionRule
IndicatorCatalog = IndicatorsCatalog


@dataclass(frozen=True, slots=True)
class OfficeCatalogEntry:
    """Single election contest specification from `data/reference/offices.yaml`.

    Attributes:
        year: Election year (e.g. 2026).
        round: Electoral round (1 or 2).
        office: Canonical office enum.
        system: Electoral system ('majoritarian' or 'proportional').
        scope: Contest scope ('national', 'state', 'municipal').
        votes_per_voter: Number of votes per voter (2 for Senator in 2026, else 1).
        tse_cd_eleicao: Official TSE election code.
        tse_cd_cargo: Official TSE office code.
        election_date: Date of the election round.
    """

    year: int
    round: int
    office: Office
    system: ElectoralSystem
    scope: ElectionScope
    votes_per_voter: int
    tse_cd_eleicao: int
    tse_cd_cargo: int
    election_date: date


def _strip_accents_upper(text: str) -> str:
    """Removes diacritical marks, uppercases, and strips whitespace.

    Args:
        text: Input string.

    Returns:
        Normalized uppercase ASCII string.
    """
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return ascii_only.upper().strip()


def normalize_party_code(
    raw_sg: str,
    aliases: dict[str, str] | None = None,
) -> str:
    """Normalizes a TSE `SG_PARTIDO` value to the canonical `party_code`.

    Args:
        raw_sg: Raw party acronym from a TSE file.
        aliases: Optional normalized alias mapping from `party_ideology.yaml`.

    Returns:
        Canonical `party_code` string.
    """
    cleaned = _strip_accents_upper(raw_sg)
    if aliases and cleaned in aliases:
        return aliases[cleaned]
    return cleaned


def load_party_ideology_catalog(path: Path) -> PartyIdeologyCatalog:
    """Loads and validates `data/reference/party_ideology.yaml`.

    Args:
        path: Path to `party_ideology.yaml`.

    Returns:
        Validated PartyIdeologyCatalog instance.

    Raises:
        ReferenceCatalogError: If any party's score/bloc/thresholds are inconsistent.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    thresholds = raw.get("thresholds", {})
    left_max = float(thresholds.get("left_max_exclusive", 4.00))
    right_min = float(thresholds.get("right_min_exclusive", 6.00))

    raw_aliases: dict[str, str] = raw.get("aliases", {}) or {}
    normalized_aliases = {
        _strip_accents_upper(k): _strip_accents_upper(v) for k, v in raw_aliases.items()
    }

    entries: list[PartyIdeologyEntry] = []
    seen_keys: set[tuple[str, int]] = set()
    for item in raw.get("parties", []):
        party_code = _strip_accents_upper(item["party_code"])
        score = float(item["score"])
        bloc = Bloc(item["bloc"])
        expected_bloc = classify_bloc_from_score(
            score,
            left_max_exclusive=left_max,
            right_min_exclusive=right_min,
        )
        if bloc != expected_bloc:
            raise ReferenceCatalogError(
                f"Party {party_code} has score={score} which maps to "
                f"{expected_bloc}, but YAML declares bloc={bloc}."
            )
        valid_from = int(item["valid_from"])
        key = (party_code, valid_from)
        if key in seen_keys:
            raise ReferenceCatalogError(f"Duplicate party_ideology key: {key}")
        seen_keys.add(key)

        entries.append(
            PartyIdeologyEntry(
                party_code=party_code,
                number=int(item["number"]) if item.get("number") is not None else None,
                name=str(item["name"]).strip(),
                score=score,
                bloc=bloc,
                valid_from=valid_from,
                valid_to=(
                    int(item["valid_to"]) if item.get("valid_to") is not None else None
                ),
                method=IdeologyMethod(item["method"]),
                source=str(item["source"]).strip(),
                note=str(item["note"]).strip() if item.get("note") else None,
            )
        )

    return PartyIdeologyCatalog(
        entries=tuple(entries),
        aliases=normalized_aliases,
        left_max_exclusive=left_max,
        right_min_exclusive=right_min,
    )


def load_indicators_catalog(path: Path) -> IndicatorsCatalog:
    """Loads and validates `data/reference/indicators.yaml`.

    Args:
        path: Path to `indicators.yaml`.

    Returns:
        Validated IndicatorsCatalog instance.

    Raises:
        ReferenceCatalogError: If duplicate codes or labels > 32 characters are found.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    exceptions: list[CoverageExceptionRule] = []
    for exc_item in raw.get("coverage_exceptions", []) or []:
        adapters = exc_item.get("applies_to_adapters")
        exceptions.append(
            CoverageExceptionRule(
                cd_ibge=int(exc_item["cd_ibge"]),
                name=str(exc_item["name"]),
                uf=str(exc_item["uf"]).upper(),
                missing_reason=str(exc_item["missing_reason"]),
                applies_to_ref_years_before=(
                    int(exc_item["applies_to_ref_years_before"])
                    if exc_item.get("applies_to_ref_years_before") is not None
                    else None
                ),
                applies_to_adapters=tuple(adapters) if adapters else None,
            )
        )

    indicators: dict[str, IndicatorSpec] = {}
    for item in raw.get("indicators", []):
        code = str(item["code"]).strip()
        if code in indicators:
            raise ReferenceCatalogError(f"Duplicate indicator code: {code}")
        label = str(item["label"]).strip()
        if len(label) > 32:
            raise ReferenceCatalogError(
                f"Indicator '{code}' label exceeds 32 chars ({len(label)}): {label!r}"
            )
        v_range = item.get("valid_range")
        valid_range = (
            (float(v_range[0]), float(v_range[1]))
            if isinstance(v_range, list) and len(v_range) == 2
            else None
        )
        src = item["source"]
        indicators[code] = IndicatorSpec(
            code=code,
            label=label,
            description=str(item["description"]).strip(),
            theme=Theme(item["theme"]),
            tier=int(item["tier"]),
            unit=str(item["unit"]).strip(),
            value_type=ValueType(item["value_type"]),
            higher_is=HigherIs(item["higher_is"]),
            scale_hint=ScaleHint(item.get("scale_hint", "quantile")),
            valid_range=valid_range,
            adapter=str(src["adapter"]).strip(),
            source_params=dict(src.get("params") or {}),
            source_name=str(src["name"]).strip(),
            source_url=str(src["url"]).strip(),
            license=str(src["license"]).strip() if src.get("license") else None,
            citation=str(src["citation"]).strip() if src.get("citation") else None,
            transform=dict(item["transform"]) if item.get("transform") else None,
            ref_year_policy=str(item.get("ref_year_policy", "latest")).strip(),
            min_coverage=float(item.get("min_coverage", 0.99)),
            caveat=str(item["caveat"]).strip() if item.get("caveat") else None,
            verified=bool(item.get("verified", False)),
        )

    return IndicatorsCatalog(
        indicators=indicators,
        coverage_exceptions=tuple(exceptions),
    )


def load_offices_catalog(path: Path) -> tuple[OfficeCatalogEntry, ...]:
    """Loads and validates `data/reference/offices.yaml`.

    Args:
        path: Path to `offices.yaml`.

    Returns:
        Tuple of OfficeCatalogEntry records.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries: list[OfficeCatalogEntry] = []
    for item in raw:
        raw_date = item["election_date"]
        election_date = (
            raw_date
            if isinstance(raw_date, date)
            else date.fromisoformat(str(raw_date))
        )
        entries.append(
            OfficeCatalogEntry(
                year=int(item["year"]),
                round=int(item["round"]),
                office=Office(item["office"]),
                system=ElectoralSystem(item["system"]),
                scope=ElectionScope(item["scope"]),
                votes_per_voter=int(item.get("votes_per_voter", 1)),
                tse_cd_eleicao=int(item["tse_cd_eleicao"]),
                tse_cd_cargo=int(item["tse_cd_cargo"]),
                election_date=election_date,
            )
        )
    return tuple(entries)


def sync_reference_to_db(
    engine: sa.Engine,
    reference_dir: Path,
) -> StepResult:
    """Idempotently upserts `party`, `party_ideology`, `indicator`, and `election`.

    Args:
        engine: SQLAlchemy Engine connected to PostgreSQL.
        reference_dir: Directory containing `party_ideology.yaml`, `indicators.yaml`,
            and `offices.yaml`.

    Returns:
        StepResult summarizing the loaded reference rows.
    """
    party_cat = load_party_ideology_catalog(reference_dir / "party_ideology.yaml")
    ind_cat = load_indicators_catalog(reference_dir / "indicators.yaml")
    offices_cat = load_offices_catalog(reference_dir / "offices.yaml")

    unique_parties: dict[str, dict[str, Any]] = {}
    for entry in party_cat.entries:
        unique_parties[entry.party_code] = {
            "party_code": entry.party_code,
            "number": entry.number,
            "name": entry.name,
        }

    ideology_rows = [
        {
            "party_code": e.party_code,
            "valid_from": e.valid_from,
            "valid_to": e.valid_to,
            "score": e.score,
            "bloc": str(e.bloc),
            "method": str(e.method),
            "source": e.source,
            "note": e.note,
        }
        for e in party_cat.entries
    ]

    indicator_rows = [
        {
            "code": ind.code,
            "label": ind.label,
            "description": ind.description,
            "theme": str(ind.theme),
            "tier": ind.tier,
            "unit": ind.unit,
            "value_type": str(ind.value_type),
            "higher_is": str(ind.higher_is),
            "scale_hint": str(ind.scale_hint),
            "source_name": ind.source_name,
            "source_url": ind.source_url,
            "license": ind.license,
            "citation": ind.citation,
            "caveat": ind.caveat,
            "ref_year_policy": ind.ref_year_policy,
        }
        for ind in ind_cat.indicators.values()
    ]

    election_rows = [
        {
            "year": o.year,
            "round": o.round,
            "office": str(o.office),
            "system": str(o.system),
            "scope": str(o.scope),
            "votes_per_voter": o.votes_per_voter,
            "election_date": o.election_date,
            "tse_cd_eleicao": o.tse_cd_eleicao,
            "tse_cd_cargo": o.tse_cd_cargo,
        }
        for o in offices_cat
    ]

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO party (party_code, number, name)
                VALUES (:party_code, :number, :name)
                ON CONFLICT (party_code) DO UPDATE SET
                    number = EXCLUDED.number,
                    name = EXCLUDED.name
                """
            ),
            list(unique_parties.values()),
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO party_ideology (
                    party_code, valid_from, valid_to, score, bloc, method, source, note
                )
                VALUES (
                    :party_code, :valid_from, :valid_to, :score,
                    :bloc, :method, :source, :note
                )
                ON CONFLICT (party_code, valid_from) DO UPDATE SET
                    valid_to = EXCLUDED.valid_to,
                    score = EXCLUDED.score,
                    bloc = EXCLUDED.bloc,
                    method = EXCLUDED.method,
                    source = EXCLUDED.source,
                    note = EXCLUDED.note
                """
            ),
            ideology_rows,
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO indicator (
                    code, label, description, theme, tier, unit, value_type,
                    higher_is, scale_hint, source_name, source_url, license,
                    citation, caveat, ref_year_policy
                )
                VALUES (
                    :code, :label, :description, :theme, :tier, :unit, :value_type,
                    :higher_is, :scale_hint, :source_name, :source_url, :license,
                    :citation, :caveat, :ref_year_policy
                )
                ON CONFLICT (code) DO UPDATE SET
                    label = EXCLUDED.label,
                    description = EXCLUDED.description,
                    theme = EXCLUDED.theme,
                    tier = EXCLUDED.tier,
                    unit = EXCLUDED.unit,
                    value_type = EXCLUDED.value_type,
                    higher_is = EXCLUDED.higher_is,
                    scale_hint = EXCLUDED.scale_hint,
                    source_name = EXCLUDED.source_name,
                    source_url = EXCLUDED.source_url,
                    license = EXCLUDED.license,
                    citation = EXCLUDED.citation,
                    caveat = EXCLUDED.caveat,
                    ref_year_policy = EXCLUDED.ref_year_policy
                """
            ),
            indicator_rows,
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO election (
                    year, round, office, system, scope, votes_per_voter,
                    election_date, tse_cd_eleicao, tse_cd_cargo
                )
                VALUES (
                    :year, :round, :office, :system, :scope, :votes_per_voter,
                    :election_date, :tse_cd_eleicao, :tse_cd_cargo
                )
                ON CONFLICT (year, round, office) DO UPDATE SET
                    system = EXCLUDED.system,
                    scope = EXCLUDED.scope,
                    votes_per_voter = EXCLUDED.votes_per_voter,
                    election_date = EXCLUDED.election_date,
                    tse_cd_eleicao = EXCLUDED.tse_cd_eleicao,
                    tse_cd_cargo = EXCLUDED.tse_cd_cargo
                """
            ),
            election_rows,
        )

    total = (
        len(unique_parties)
        + len(ideology_rows)
        + len(indicator_rows)
        + len(election_rows)
    )
    return StepResult(
        step="reference",
        rows_in=total,
        rows_out=total,
        dropped={},
    )
