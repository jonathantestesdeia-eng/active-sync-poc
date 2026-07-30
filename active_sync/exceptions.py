"""Exceções específicas da aplicação."""


class ActiveSyncError(Exception):
    """Erro esperado e seguro para exibição no terminal."""


class ConfigError(ActiveSyncError):
    """Configuração ausente ou inválida."""


class AuthenticationError(ActiveSyncError):
    """Falha no login inicial do Active OnSupply."""


class CompanySelectionError(ActiveSyncError):
    """Falha futura na seleção do contexto operacional."""


class ReportRequestError(ActiveSyncError):
    """Falha futura ao solicitar relatório."""


class ReportTimeoutError(ActiveSyncError):
    """Tempo futuro de processamento do relatório excedido."""


class ReportAmbiguityError(ActiveSyncError):
    """Mais de um relatório futuro corresponde à execução."""


class DownloadError(ActiveSyncError):
    """Falha futura no download."""


class InvalidZipError(ActiveSyncError):
    """Arquivo futuro não é um ZIP válido."""


class ExtractionError(ActiveSyncError):
    """Falha futura na extração segura."""


class ExcelReadError(ActiveSyncError):
    """Falha futura na leitura do Excel."""


class StorageError(ActiveSyncError):
    """Falha segura na infraestrutura de armazenamento externo."""


class StorageConfigurationError(StorageError):
    """Configuração do armazenamento externo ausente ou inválida."""


class StorageDisabledError(StorageError):
    """Tentativa de uso de um armazenamento explicitamente desabilitado."""


class StorageUploadError(StorageError):
    """Falha ao armazenar um arquivo no provedor externo."""


class TransformationError(ActiveSyncError):
    """Falha na transformação do relatório bruto."""


class TransformationValidationError(TransformationError):
    """Estrutura de entrada ou saída incompatível com o contrato."""


class ReconciliationError(TransformationError):
    """Não foi possível reconciliar o universo de registros com segurança."""


class IncompatibleSnapshotError(TransformationError):
    """Os snapshots não permitem uma comparação temporal conclusiva."""
