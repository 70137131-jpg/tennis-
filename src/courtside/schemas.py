from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ShotType = Literal["serve", "forehand", "backhand", "volley", "unknown"]


class SchemaModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class Keypoint(SchemaModel):
    x: float
    y: float
    confidence: float = Field(ge=0, le=1)


class PoseFrame(SchemaModel):
    frame: int = Field(ge=0)
    time: float = Field(ge=0)
    player_id: str
    side: Literal["near", "far"]
    keypoints: list[Keypoint] = Field(min_length=17, max_length=17)


class VideoInfo(SchemaModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    frames: int = Field(gt=0)
    duration: float = Field(gt=0)
    warnings: list[str] = []


class Metric(SchemaModel):
    name: str
    label: str
    phase: str
    value: float | None
    unit: str
    confidence: float = Field(ge=0, le=1)
    measurable: bool
    reason: str | None = None
    target: list[float] | None = None

    @model_validator(mode="after")
    def measurement_consistency(self):
        if self.measurable and self.value is None:
            raise ValueError("Measurable metrics require a value")
        if not self.measurable and self.value is not None:
            raise ValueError("Unmeasurable metrics must not expose a value")
        return self


class Tip(SchemaModel):
    id: str
    metric: str
    value: float
    target: list[float] = Field(min_length=2, max_length=2)
    severity: int = Field(ge=1, le=3)
    title: str
    explanation: str
    joints: list[int] = []
    rule_version: str


class TechniqueCheck(SchemaModel):
    metric: str
    label: str
    phase: str
    value: float | None
    unit: str
    target: list[float] | None
    status: Literal["within_target", "below_target", "above_target", "not_measurable", "no_target"]
    reason: str | None = None


class TechniqueAssessment(SchemaModel):
    status: Literal["provisional", "limited", "unavailable", "disabled"]
    score: float | None = Field(default=None, ge=0, le=100)
    measured_checks: int = Field(ge=0)
    expected_checks: int = Field(ge=0)
    checks: list[TechniqueCheck]
    explanation: str
    rule_version: str


class Shot(SchemaModel):
    id: str
    player_id: str
    type: ShotType
    start: float = Field(ge=0)
    contact: float = Field(ge=0)
    end: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    classification_source: Literal["heuristic", "trained"] = "heuristic"
    classification_evidence: list[str] = []
    technique: TechniqueAssessment | None = None
    metrics: list[Metric] = []
    tips: list[Tip] = []
    clip: str | None = None
    court_position: list[float] | None = None

    @model_validator(mode="after")
    def time_order(self):
        if not self.start <= self.contact <= self.end:
            raise ValueError("Shot timestamps must be ordered")
        return self


class Report(SchemaModel):
    schema_version: str = "1.0.0"
    pipeline_version: str = "baseline-1"
    feedback_rules_version: str
    coach_validated: bool = False
    video: VideoInfo
    shots: list[Shot]
    summary_tips: list[Tip] = []
    players: list[dict] = []
    warnings: list[str] = []
    diagnostics: dict = {}
    annotated_video: str = "annotated.mp4"
    is_demo: bool = False
