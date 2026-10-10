from datetime import date, datetime
from pydantic import BaseModel, Field, model_validator

class EngagementCreate(BaseModel):
    organization_id: str
    name: str = Field(min_length=2, max_length=200)
    financial_year: str = Field(min_length=4, max_length=20)
    period_start: date
    period_end: date
    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self

class EngagementPublic(BaseModel):
    id: str
    organization_id: str
    name: str
    financial_year: str
    period_start: date
    period_end: date
    status: str
    is_demo: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class OrganizationPublic(BaseModel):
    id: str
    name: str
    is_demo: bool
    model_config = {"from_attributes": True}
