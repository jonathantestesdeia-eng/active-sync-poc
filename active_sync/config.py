"""Carregamento e validação das configurações do arquivo .env."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from datetime import date, datetime, time as clock_time
from pathlib import Path
import os
from urllib.parse import urlparse

from dotenv import dotenv_values, load_dotenv

from active_sync import __version__

from .exceptions import ConfigError


class AppEnvironment(StrEnum):
    """Ambientes suportados pela aplicaÃ§Ã£o HTTP."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class ProcessingProfile(StrEnum):
    """Perfis de processamento isolados por finalidade de negócio."""

    SUPERTRACK = "supertrack"
    PERFORMANCE = "performance"


def _environment_values(
    project_root: Path,
    env_file: Path | None,
    environ: dict[str, str] | None,
) -> dict[str, str]:
    """Combina .env base, arquivo do ambiente e variÃ¡veis do processo."""
    process_values = dict(os.environ if environ is None else environ)
    base_file = env_file if env_file is not None else project_root / ".env"
    base_values = {
        key: value
        for key, value in dotenv_values(base_file).items()
        if value is not None
    }
    environment_name = process_values.get(
        "APP_ENV", base_values.get("APP_ENV", AppEnvironment.DEVELOPMENT.value)
    ).strip().lower()
    environment_file = project_root / f".env.{environment_name}"
    scoped_values = {
        key: value
        for key, value in dotenv_values(environment_file).items()
        if value is not None
    }
    return {**base_values, **scoped_values, **process_values}


def _config_text(values: dict[str, str], name: str) -> str | None:
    value = str(values.get(name, "")).strip()
    return value or None


def _config_positive_int(values: dict[str, str], name: str, default: int) -> int:
    raw = _config_text(values, name) or str(default)
    try:
        result = int(raw)
    except ValueError as error:
        raise ConfigError(f"{name} deve ser um inteiro positivo.") from error
    if result <= 0:
        raise ConfigError(f"{name} deve ser um inteiro positivo.")
    return result


def _config_date(values: dict[str, str], name: str) -> date | None:
    raw = _config_text(values, name)
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise ConfigError(f"{name} deve estar no formato YYYY-MM-DD.") from error


def _config_schedule(values: dict[str, str]) -> tuple[clock_time, ...]:
    raw = _config_text(values, "ACTIVE_SYNC_SCHEDULE")
    if raw is None:
        return ()
    parsed: list[clock_time] = []
    for item in raw.split(","):
        try:
            parsed.append(datetime.strptime(item.strip(), "%H:%M").time())
        except ValueError as error:
            raise ConfigError(
                "ACTIVE_SYNC_SCHEDULE deve conter horarios HH:MM separados por virgula."
            ) from error
    return tuple(sorted(set(parsed)))


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    """ConfiguraÃ§Ã£o transversal da API, sem segredos hardcoded."""

    environment: AppEnvironment
    api_key: str | None
    allowed_origins: tuple[str, ...]
    database_path: Path | None
    version: str
    build_date: str
    database_engine: str = "sqlite"
    sync_schedule: tuple[clock_time, ...] = ()
    sync_full_start_date: date | None = None
    sync_incremental_lookback_days: int = 1
    sync_work_dir: Path = Path("runtime")
    sync_client_register_path: Path | None = None
    sync_client_register_sheet: str | None = None
    processing_profile: ProcessingProfile = ProcessingProfile.SUPERTRACK

    @property
    def debug(self) -> bool:
        return self.environment is AppEnvironment.DEVELOPMENT

    @property
    def log_level(self) -> str:
        return "DEBUG" if self.debug else "INFO"

    def validate_required(self) -> None:
        """Falha cedo quando uma configuraÃ§Ã£o obrigatÃ³ria estÃ¡ ausente."""
        missing = []
        if not self.api_key:
            missing.append("ACTIVE_SYNC_API_KEY")
        if not self.allowed_origins:
            missing.append("ACTIVE_SYNC_ALLOWED_ORIGINS")
        if self.database_path is None:
            missing.append("ACTIVE_SYNC_DATABASE_PATH")
        if missing:
            raise ConfigError(
                "VariÃ¡veis obrigatÃ³rias ausentes: " + ", ".join(missing) + "."
            )
        if len(self.api_key) < 16:
            raise ConfigError("ACTIVE_SYNC_API_KEY deve possuir ao menos 16 caracteres.")
        if "*" in self.allowed_origins:
            raise ConfigError("ACTIVE_SYNC_ALLOWED_ORIGINS nÃ£o aceita origem curinga.")
        if self.environment is AppEnvironment.PRODUCTION and self.build_date == "local":
            raise ConfigError("ACTIVE_SYNC_BUILD_DATE Ã© obrigatÃ³ria em production.")

    @classmethod
    def from_env(
        cls,
        env_file: Path | None = None,
        *,
        project_root: Path | None = None,
        environ: dict[str, str] | None = None,
        validate_required: bool = True,
    ) -> "ApplicationSettings":
        """Carrega o ambiente com precedÃªncia processo > ambiente > base."""
        root = project_root or Path(__file__).resolve().parent.parent
        values = _environment_values(root, env_file, environ)
        raw_environment = _config_text(values, "APP_ENV") or AppEnvironment.DEVELOPMENT.value
        try:
            environment = AppEnvironment(raw_environment.lower())
        except ValueError as error:
            raise ConfigError("APP_ENV deve ser development, test ou production.") from error

        origins = tuple(
            origin.strip().rstrip("/")
            for origin in (_config_text(values, "ACTIVE_SYNC_ALLOWED_ORIGINS") or "").split(",")
            if origin.strip()
        )
        if "*" in origins:
            raise ConfigError("ACTIVE_SYNC_ALLOWED_ORIGINS nÃ£o aceita origem curinga.")
        for origin in origins:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ConfigError(
                    "ACTIVE_SYNC_ALLOWED_ORIGINS deve conter apenas origens HTTP/HTTPS vÃ¡lidas."
                )

        database_value = _config_text(values, "ACTIVE_SYNC_DATABASE_PATH")
        client_register_value = _config_text(values, "ACTIVE_SYNC_CLIENT_REGISTER_PATH")
        raw_profile = (
            _config_text(values, "ACTIVE_SYNC_PROFILE")
            or ProcessingProfile.SUPERTRACK.value
        )
        try:
            processing_profile = ProcessingProfile(raw_profile.lower())
        except ValueError as error:
            raise ConfigError(
                "ACTIVE_SYNC_PROFILE deve ser supertrack ou performance."
            ) from error
        settings = cls(
            environment=environment,
            api_key=_config_text(values, "ACTIVE_SYNC_API_KEY"),
            allowed_origins=origins,
            database_path=Path(database_value) if database_value else None,
            version=_config_text(values, "ACTIVE_SYNC_VERSION") or __version__,
            build_date=_config_text(values, "ACTIVE_SYNC_BUILD_DATE") or "local",
            sync_schedule=_config_schedule(values),
            sync_full_start_date=_config_date(values, "ACTIVE_SYNC_FULL_START_DATE"),
            sync_incremental_lookback_days=_config_positive_int(
                values, "ACTIVE_SYNC_INCREMENTAL_LOOKBACK_DAYS", 1
            ),
            sync_work_dir=Path(
                _config_text(values, "ACTIVE_SYNC_WORK_DIR") or str(root / "runtime")
            ),
            sync_client_register_path=(
                Path(client_register_value) if client_register_value else None
            ),
            sync_client_register_sheet=_config_text(
                values, "ACTIVE_SYNC_CLIENT_REGISTER_SHEET"
            ),
            processing_profile=processing_profile,
        )
        if validate_required:
            settings.validate_required()
        return settings


def _optional_text(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _required_text(name: str) -> str:
    value = _optional_text(name)
    if value is None:
        raise ConfigError(f"A variável obrigatória {name} não foi preenchida no arquivo .env.")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"A variável {name} deve ser um número inteiro.") from exc
    if value <= 0:
        raise ConfigError(f"A variável {name} deve ser maior que zero.")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    values = {"true": True, "false": False, "1": True, "0": False, "yes": True, "no": False}
    if raw not in values:
        raise ConfigError(f"A variável {name} deve ser true ou false.")
    return values[raw]


@dataclass(frozen=True, slots=True)
class Settings:
    base_url: str
    user: str
    password: str
    user_code: str | None
    company_id: str | None
    branch_id: str | None
    access_type: str
    is_destinatario: bool
    formulario_id: int
    report_code: str
    report_name: str
    report_format: str
    date_from: str | None
    date_to: str | None
    poll_interval_seconds: int
    report_timeout_seconds: int
    http_timeout_seconds: int
    report_time_tolerance_seconds: int

    def validate_context(self) -> None:
        missing = []
        if not self.company_id:
            missing.append("ACTIVE_COMPANY_ID")
        if not self.branch_id:
            missing.append("ACTIVE_BRANCH_ID")
        if missing:
            names = " e ".join(missing)
            raise ConfigError(
                f"Preencha {names} no arquivo .env para selecionar o contexto operacional."
            )

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        project_root = Path(__file__).resolve().parent.parent
        selected_env = env_file if env_file is not None else project_root / ".env"
        load_dotenv(selected_env, override=False)

        base_url = os.getenv("ACTIVE_BASE_URL", "https://activeonsupply.com.br").strip().rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigError("ACTIVE_BASE_URL deve conter uma URL HTTP ou HTTPS válida.")

        return cls(
            base_url=base_url,
            user=_required_text("ACTIVE_USER"),
            password=_required_text("ACTIVE_PASSWORD"),
            user_code=_optional_text("ACTIVE_USER_CODE"),
            company_id=_optional_text("ACTIVE_COMPANY_ID"),
            branch_id=_optional_text("ACTIVE_BRANCH_ID"),
            access_type=os.getenv("ACTIVE_ACCESS_TYPE", "C").strip() or "C",
            is_destinatario=_boolean("ACTIVE_IS_DESTINATARIO", False),
            formulario_id=_positive_int("ACTIVE_FORMULARIO_ID", 118),
            report_code=os.getenv("ACTIVE_REPORT_CODE", "118").strip() or "118",
            report_name=os.getenv("ACTIVE_REPORT_NAME", "Conhecimento - CTe").strip() or "Conhecimento - CTe",
            report_format=os.getenv("ACTIVE_REPORT_FORMAT", "Excel__NotaFiscal").strip() or "Excel__NotaFiscal",
            date_from=_optional_text("ACTIVE_DATE_FROM"),
            date_to=_optional_text("ACTIVE_DATE_TO"),
            poll_interval_seconds=_positive_int("ACTIVE_POLL_INTERVAL_SECONDS", 10),
            report_timeout_seconds=_positive_int("ACTIVE_REPORT_TIMEOUT_SECONDS", 900),
            http_timeout_seconds=_positive_int("ACTIVE_HTTP_TIMEOUT_SECONDS", 60),
            report_time_tolerance_seconds=_positive_int("ACTIVE_REPORT_TIME_TOLERANCE_SECONDS", 120),
        )
