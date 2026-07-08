import enum


class CoordinateSystem(str, enum.Enum):
    WGS84 = "WGS84"
    GCJ02 = "GCJ02"
    BD09 = "BD09"


class IngestionRunStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
