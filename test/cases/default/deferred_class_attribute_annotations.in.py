from __future__ import annotations

from pydantic import BaseModel


class Session(BaseModel):
    assessments: list[Assessment] | None = None


class Assessment(BaseModel):
    measurements: list[Measurement] | None = None


class Measurement(BaseModel):
    assessment: Assessment | None = None
